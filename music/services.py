"""Business logic and services for YouTube search, queue management, and playback."""

import re
import requests
from datetime import timedelta
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import Room, QueueItem, Vote, PlayerState, AuditLog
from .utils import parse_youtube_duration, format_duration


class YouTubeAPIError(Exception):
    """Custom exception for YouTube API failures."""
    pass


class YouTubeService:
    """Service for interacting with YouTube Data API v3 safely and efficiently."""

    SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
    VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
    VIDEO_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{11}$")

    @classmethod
    def get_api_key(cls):
        api_key = getattr(settings, "YOUTUBE_API_KEY", "").strip()
        return api_key

    @classmethod
    def validate_video_id(cls, video_id):
        """Ensure video ID is a valid 11-character YouTube video ID."""
        if not video_id or not cls.VIDEO_ID_REGEX.match(video_id):
            return False
        return True

    @classmethod
    def check_search_rate_limit(cls, participant_id, max_requests=15, window_seconds=60):
        """Enforce rate limits per participant to prevent YouTube API quota exhaustion."""
        rate_key = f"rate_search:{participant_id}"
        current = cache.get(rate_key, 0)
        if current >= max_requests:
            return False
        cache.set(rate_key, current + 1, timeout=window_seconds)
        return True

    @classmethod
    def search(cls, query, max_results=10):
        """Search YouTube videos by keyword or URL, caching results for 15 minutes."""
        api_key = cls.get_api_key()
        if not api_key:
            raise YouTubeAPIError(
                "YouTube Data API key is missing. Set YOUTUBE_API_KEY in your .env file."
            )

        query = query.strip()
        if not query:
            return []

        # If user pasted a full YouTube URL, extract video ID
        yt_url_match = re.search(
            r"(?:v=|\/embed\/|\/watch\?v=|\/youtu\.be\/|\/v\/|shorts\/)([a-zA-Z0-9_-]{11})",
            query,
        )
        if yt_url_match:
            video_id = yt_url_match.group(1)
            return cls.get_video_details([video_id])

        cache_key = f"yt_search:{query.lower()[:80]}:{max_results}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # Step 1: Search for embeddable videos
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "videoEmbeddable": "true",
            "videoSyndicated": "true",
            "maxResults": min(max_results, 25),
            "key": api_key,
        }

        try:
            resp = requests.get(cls.SEARCH_URL, params=params, timeout=6)
        except requests.RequestException as e:
            raise YouTubeAPIError(f"Network error contacting YouTube: {e}")

        if resp.status_code == 403:
            raise YouTubeAPIError(
                "YouTube API daily quota exceeded or API key restricted. Please verify in Google Cloud Console."
            )
        elif resp.status_code != 200:
            raise YouTubeAPIError(
                f"YouTube API returned error {resp.status_code}: {resp.text}"
            )

        data = resp.json()
        items = data.get("items", [])
        if not items:
            cache.set(cache_key, [], timeout=600)
            return []

        video_ids = [
            item["id"]["videoId"] for item in items if "videoId" in item.get("id", {})
        ]

        # Step 2: Fetch video details to retrieve exact duration & embedding status
        results = cls.get_video_details(video_ids)
        cache.set(cache_key, results, timeout=900)
        return results

    @classmethod
    def get_video_details(cls, video_ids):
        """Fetch details (duration, embeddability, status) for a list of video IDs."""
        api_key = cls.get_api_key()
        if not api_key or not video_ids:
            return []

        clean_ids = [vid for vid in video_ids if cls.validate_video_id(vid)]
        if not clean_ids:
            return []

        params = {
            "part": "snippet,contentDetails,status",
            "id": ",".join(clean_ids[:50]),
            "key": api_key,
        }

        try:
            resp = requests.get(cls.VIDEOS_URL, params=params, timeout=6)
        except requests.RequestException as e:
            raise YouTubeAPIError(f"Network error contacting YouTube: {e}")

        if resp.status_code != 200:
            return []

        data = resp.json()
        results = []
        for item in data.get("items", []):
            vid = item.get("id")
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            status = item.get("status", {})

            # Filter out videos not allowed to embed or private
            if not status.get("embeddable", True):
                continue
            if status.get("privacyStatus") == "private":
                continue

            duration_iso = content.get("duration", "PT0S")
            duration_secs = parse_youtube_duration(duration_iso)

            # Extract highest quality thumbnail available
            thumbnails = snippet.get("thumbnails", {})
            thumb_url = (
                thumbnails.get("medium", {}).get("url")
                or thumbnails.get("default", {}).get("url")
                or f"https://img.youtube.com/vi/{vid}/mqdefault.jpg"
            )

            results.append({
                "video_id": vid,
                "title": snippet.get("title", "Unknown Title"),
                "channel_title": snippet.get("channelTitle", "Unknown Channel"),
                "thumbnail_url": thumb_url,
                "duration_seconds": duration_secs,
                "duration_formatted": format_duration(duration_secs),
            })

        return results


class QueueService:
    """Manages transaction-safe shared queue operations and fair-play enforcement."""

    @classmethod
    def add_song(cls, room, participant_id, display_name, video_data):
        """Add a song to the queue enforcing active limit, duplicate check, and cooldown."""
        video_id = video_data.get("video_id")
        if not YouTubeService.validate_video_id(video_id):
            raise ValidationError("Invalid YouTube video ID format.")

        title = video_data.get("title", "").strip()[:255]
        channel_title = video_data.get("channel_title", "").strip()[:255]
        thumbnail_url = video_data.get("thumbnail_url", "").strip()[:500]
        duration_seconds = int(video_data.get("duration_seconds", 0))

        settings_obj = room.settings

        with transaction.atomic():
            # 1. Duplicate check: video already queued or playing in this room
            is_duplicate = QueueItem.objects.filter(
                room=room,
                video_id=video_id,
                status__in=[QueueItem.Status.QUEUED, QueueItem.Status.PLAYING],
            ).exists()
            if is_duplicate:
                raise ValidationError("This song is already in the queue or currently playing!")

            # 2. Max active songs per employee check
            user_active_count = QueueItem.objects.filter(
                room=room,
                added_by_id=participant_id,
                status=QueueItem.Status.QUEUED,
            ).count()
            if user_active_count >= settings_obj.max_active_songs_per_user:
                raise ValidationError(
                    f"You have reached your limit of {settings_obj.max_active_songs_per_user} active queued songs. "
                    "Wait for your songs to play or remove one."
                )

            # 3. Cooldown check
            if settings_obj.user_song_cooldown_seconds > 0:
                last_added = (
                    QueueItem.objects.filter(room=room, added_by_id=participant_id)
                    .order_by("-created_at")
                    .first()
                )
                if last_added:
                    elapsed = (timezone.now() - last_added.created_at).total_seconds()
                    remaining = int(settings_obj.user_song_cooldown_seconds - elapsed)
                    if remaining > 0:
                        raise ValidationError(
                            f"Fair-play cooldown: Please wait {remaining} seconds before adding another song."
                        )

            # Create queue item with initial 1 vote from author
            item = QueueItem.objects.create(
                room=room,
                video_id=video_id,
                title=title or "Untitled Song",
                channel_title=channel_title,
                thumbnail_url=thumbnail_url,
                duration_seconds=duration_seconds,
                added_by_name=display_name,
                added_by_id=participant_id,
                status=QueueItem.Status.QUEUED,
                vote_count=1,
            )

            # Record initial vote
            Vote.objects.create(
                queue_item=item,
                participant_id=participant_id,
                value=1,
            )

            AuditLog.objects.create(
                room=room,
                actor_name=display_name,
                action="ADD_SONG",
                details=f"Added '{title}' ({video_id})",
            )

            return item


    @classmethod
    def vote_song(cls, queue_item, participant_id):
        """Toggle an upvote for a participant on a queue item.

        Returns tuple (queue_item, voted_boolean).
        """
        if queue_item.status != QueueItem.Status.QUEUED:
            raise ValidationError("You can only vote for songs currently waiting in the queue.")

        with transaction.atomic():
            existing_vote = Vote.objects.filter(
                queue_item=queue_item,
                participant_id=participant_id,
            ).first()

            if existing_vote:
                # User already voted: remove the vote (toggle unvote)
                existing_vote.delete()
                voted = False
            else:
                # Add new upvote
                Vote.objects.create(
                    queue_item=queue_item,
                    participant_id=participant_id,
                    value=1,
                )
                voted = True

            queue_item.recalculate_votes()
            return queue_item, voted

    @classmethod
    def remove_song(cls, queue_item, participant_id, is_moderator=False, actor_name="User"):
        """Remove a song from the queue. Only allowed by original author or room moderator."""
        if queue_item.status != QueueItem.Status.QUEUED:
            raise ValidationError("Only waiting queued songs can be removed.")

        if queue_item.added_by_id != participant_id and not is_moderator:
            raise ValidationError("You do not have permission to remove this song.")

        with transaction.atomic():
            queue_item.status = QueueItem.Status.REMOVED
            queue_item.save(update_fields=["status", "updated_at"])

            AuditLog.objects.create(
                room=queue_item.room,
                actor_name=actor_name,
                action="REMOVE_SONG",
                details=f"Removed '{queue_item.title}'",
            )
            return queue_item

    @classmethod
    def advance_next_song(cls, room, mark_status=QueueItem.Status.PLAYED, actor_name="Player"):
        """Atomically advance the room's player to the next highest-priority song.

        Returns the new playing QueueItem or None if queue is empty.
        """
        with transaction.atomic():
            # Lock the player state row for update to prevent concurrent advancement races
            player_state = PlayerState.objects.select_for_update().get(room=room)

            current_item = player_state.current_item
            if current_item and current_item.status == QueueItem.Status.PLAYING:
                current_item.status = mark_status
                current_item.played_at = timezone.now()
                current_item.save(update_fields=["status", "played_at", "updated_at"])

            # Retrieve ordered queue respecting fair-play
            effective_queue = room.get_effective_queue()
            if effective_queue:
                next_song = effective_queue[0]
                next_song.status = QueueItem.Status.PLAYING
                next_song.played_at = timezone.now()
                next_song.save(update_fields=["status", "played_at", "updated_at"])

                player_state.current_item = next_song
                player_state.is_playing = True
                player_state.position_seconds = 0.0
                player_state.save()

                action_name = "SKIP_SONG" if mark_status == QueueItem.Status.SKIPPED else "ADVANCE_SONG"
                AuditLog.objects.create(
                    room=room,
                    actor_name=actor_name,
                    action=action_name,
                    details=f"Now playing '{next_song.title}'",
                )
                return next_song
            else:
                # No more songs in queue
                player_state.current_item = None
                player_state.is_playing = False
                player_state.position_seconds = 0.0
                player_state.save()
                return None
