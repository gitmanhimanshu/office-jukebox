"""Comprehensive automated test suite for Office Jukebox.

Covers:
- IP auto-joining and room code fallback
- Session-based employee identity
- Mocked YouTube search & missing API key handling
- Queue additions, duplicate prevention, active song limits, and cooldowns
- Vote uniqueness, vote toggling, score calculation
- Fair-turn and FIFO queue priority
- Track advancement and player state
- Authorization & moderation security
"""

import json
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from django.urls import reverse
from django.core.cache import cache
from django.core.exceptions import ValidationError

from .models import Room, RoomSettings, Participant, QueueItem, Vote, PlayerState, AuditLog
from .services import YouTubeService, QueueService, YouTubeAPIError
from .utils import mask_ip, parse_youtube_duration, format_duration


class OfficeJukeboxTestCase(TestCase):
    """Base setup for Jukebox tests."""

    def setUp(self):
        cache.clear()
        self.room = Room.objects.create(name="Engineering Room", office_ip="198.51.100.25")
        self.settings_obj = self.room.settings
        self.settings_obj.max_active_songs_per_user = 3
        self.settings_obj.user_song_cooldown_seconds = 30
        self.settings_obj.fair_turn_mode = True
        self.settings_obj.save()

        self.client1 = Client()
        self.client2 = Client()


class RoomIdentityAndJoiningTests(OfficeJukeboxTestCase):
    """Test public IP auto-resolution and session management."""

    def test_auto_join_by_office_ip(self):
        """Two employees browsing from the same office IP join the same room automatically."""
        # Employee A joins from office IP
        resp_a = self.client1.post(
            reverse("welcome"),
            {"display_name": "Employee A", "room_code": ""},
            HTTP_X_FORWARDED_FOR="198.51.100.25",
        )
        self.assertEqual(resp_a.status_code, 302)
        self.assertIn(self.room.code, resp_a.url)

        # Employee B joins from same office IP
        resp_b = self.client2.post(
            reverse("welcome"),
            {"display_name": "Employee B", "room_code": ""},
            HTTP_X_FORWARDED_FOR="198.51.100.25",
        )
        self.assertEqual(resp_b.status_code, 302)
        self.assertIn(self.room.code, resp_b.url)

        # Verify both are registered participants in the same room
        participants = self.room.participants.values_list("display_name", flat=True)
        self.assertIn("Employee A", participants)
        self.assertIn("Employee B", participants)

    def test_manual_room_code_fallback(self):
        """Employee with different IP can join using room code."""
        resp = self.client1.post(
            reverse("welcome"),
            {"display_name": "Remote Colleague", "room_code": self.room.code},
            HTTP_X_FORWARDED_FOR="203.0.113.99",
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(self.room.code, resp.url)

    def test_ip_masking(self):
        """Ensure full office IPs are never leaked raw in display."""
        masked_v4 = mask_ip("198.51.100.25")
        self.assertEqual(masked_v4, "198.51.*.*")
        masked_local = mask_ip("127.0.0.1")
        self.assertIn("Local Network", masked_local)


class YouTubeSearchServiceTests(OfficeJukeboxTestCase):
    """Test YouTube service logic, error handling, and mock API integration."""

    @override_settings(YOUTUBE_API_KEY="")
    def test_missing_api_key_error(self):
        """Friendly error is raised if YOUTUBE_API_KEY is missing."""
        with self.assertRaises(YouTubeAPIError) as cm:
            YouTubeService.search("Queen Bohemian Rhapsody")
        self.assertIn("missing", str(cm.exception).lower())

    @override_settings(YOUTUBE_API_KEY="test_fake_api_key")
    @patch("requests.get")
    def test_mocked_youtube_search_success(self, mock_get):
        """Test search query parsing and detail fetching with mocked requests."""
        # Mock search response
        search_json = {
            "items": [
                {
                    "id": {"videoId": "fJ9rUzIMcZQ"},
                    "snippet": {"title": "Bohemian Rhapsody", "channelTitle": "Queen Official"},
                }
            ]
        }
        # Mock videos detail response
        videos_json = {
            "items": [
                {
                    "id": "fJ9rUzIMcZQ",
                    "snippet": {
                        "title": "Bohemian Rhapsody",
                        "channelTitle": "Queen Official",
                        "thumbnails": {"medium": {"url": "https://example.com/thumb.jpg"}},
                    },
                    "contentDetails": {"duration": "PT5M55S"},
                    "status": {"embeddable": True, "privacyStatus": "public"},
                }
            ]
        }

        mock_search_resp = MagicMock(status_code=200)
        mock_search_resp.json.return_value = search_json
        mock_videos_resp = MagicMock(status_code=200)
        mock_videos_resp.json.return_value = videos_json

        mock_get.side_effect = [mock_search_resp, mock_videos_resp]

        results = YouTubeService.search("Queen")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["video_id"], "fJ9rUzIMcZQ")
        self.assertEqual(results[0]["duration_seconds"], 355)
        self.assertEqual(results[0]["duration_formatted"], "5:55")

    def test_duration_parsing(self):
        """Test ISO 8601 duration parser and formatter."""
        self.assertEqual(parse_youtube_duration("PT3M45S"), 225)
        self.assertEqual(parse_youtube_duration("PT1H2M10S"), 3730)
        self.assertEqual(format_duration(225), "3:45")
        self.assertEqual(format_duration(3730), "1:02:10")


class QueueFairPlayAndVotingTests(OfficeJukeboxTestCase):
    """Test shared queue, duplicate prevention, cooldowns, and fair-turn voting."""

    def setUp(self):
        super().setUp()
        self.user1_id = "user-uuid-1"
        self.user2_id = "user-uuid-2"

        self.video_data_1 = {
            "video_id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "channel_title": "Rick Astley",
            "thumbnail_url": "https://example.com/rick.jpg",
            "duration_seconds": 212,
        }
        self.video_data_2 = {
            "video_id": "9bZkp7q19f0",
            "title": "Gangnam Style",
            "channel_title": "Psy",
            "thumbnail_url": "https://example.com/psy.jpg",
            "duration_seconds": 253,
        }

    def test_add_song_initial_vote(self):
        """Adding a song automatically gives it an initial 1 vote from author."""
        item = QueueService.add_song(
            room=self.room,
            participant_id=self.user1_id,
            display_name="User 1",
            video_data=self.video_data_1,
        )
        self.assertEqual(item.vote_count, 1)
        self.assertEqual(item.status, QueueItem.Status.QUEUED)
        self.assertTrue(Vote.objects.filter(queue_item=item, participant_id=self.user1_id).exists())

    def test_duplicate_prevention(self):
        """Adding a song that is already active in queue raises ValidationError."""
        QueueService.add_song(
            room=self.room,
            participant_id=self.user1_id,
            display_name="User 1",
            video_data=self.video_data_1,
        )
        with self.assertRaises(ValidationError) as cm:
            QueueService.add_song(
                room=self.room,
                participant_id=self.user2_id,
                display_name="User 2",
                video_data=self.video_data_1,
            )
        self.assertIn("already in the queue", str(cm.exception))

    def test_user_active_songs_limit(self):
        """User cannot exceed max_active_songs_per_user."""
        self.settings_obj.user_song_cooldown_seconds = 0
        self.settings_obj.save()

        for i in range(3):
            QueueService.add_song(
                room=self.room,
                participant_id=self.user1_id,
                display_name="User 1",
                video_data={
                    "video_id": f"vid000000{i:02d}",
                    "title": f"Song {i}",
                },
            )

        # 4th song should fail
        with self.assertRaises(ValidationError) as cm:
            QueueService.add_song(
                room=self.room,
                participant_id=self.user1_id,
                display_name="User 1",
                video_data={"video_id": "vid00000099", "title": "Song 4"},
            )
        self.assertIn("limit", str(cm.exception).lower())

    def test_cooldown_enforcement(self):
        """User must wait cooldown interval before adding another song."""
        self.settings_obj.user_song_cooldown_seconds = 60
        self.settings_obj.save()

        QueueService.add_song(
            room=self.room,
            participant_id=self.user1_id,
            display_name="User 1",
            video_data=self.video_data_1,
        )

        with self.assertRaises(ValidationError) as cm:
            QueueService.add_song(
                room=self.room,
                participant_id=self.user1_id,
                display_name="User 1",
                video_data=self.video_data_2,
            )
        self.assertIn("cooldown", str(cm.exception).lower())

    def test_vote_toggling(self):
        """Voting once increments; voting again by same user retracts vote."""
        self.settings_obj.user_song_cooldown_seconds = 0
        self.settings_obj.save()

        item = QueueService.add_song(
            room=self.room,
            participant_id=self.user1_id,
            display_name="User 1",
            video_data=self.video_data_1,
        )
        self.assertEqual(item.vote_count, 1)

        # User 2 votes -> count becomes 2
        item, voted = QueueService.vote_song(item, self.user2_id)
        self.assertTrue(voted)
        self.assertEqual(item.vote_count, 2)

        # User 2 votes again -> toggle unvote, count back to 1
        item, voted = QueueService.vote_song(item, self.user2_id)
        self.assertFalse(voted)
        self.assertEqual(item.vote_count, 1)

    def test_queue_priority_and_fifo_tie_breaking(self):
        """Higher voted song takes priority; tied votes break by earlier creation date."""
        self.settings_obj.fair_turn_mode = False
        self.settings_obj.user_song_cooldown_seconds = 0
        self.settings_obj.save()

        item1 = QueueService.add_song(
            room=self.room,
            participant_id=self.user1_id,
            display_name="User 1",
            video_data={"video_id": "vid00000001", "title": "First Song"},
        )
        item2 = QueueService.add_song(
            room=self.room,
            participant_id=self.user2_id,
            display_name="User 2",
            video_data={"video_id": "vid00000002", "title": "Second Song"},
        )

        # Both have 1 vote. item1 was added first, so FIFO puts item1 first
        effective = self.room.get_effective_queue()
        self.assertEqual(effective[0].id, item1.id)

        # Vote for item2
        QueueService.vote_song(item2, "another-voter-id")
        item2.refresh_from_db()
        self.assertEqual(item2.vote_count, 2)

        # Now item2 has 2 votes vs item1 with 1 vote -> item2 must be #1
        effective = self.room.get_effective_queue()
        self.assertEqual(effective[0].id, item2.id)

    def test_fair_turn_mode_prioritization(self):
        """In fair-turn mode, tied votes prioritize users who had fewer recent plays."""
        self.settings_obj.fair_turn_mode = True
        self.settings_obj.user_song_cooldown_seconds = 0
        self.settings_obj.save()

        # Simulate user 1 having 2 songs played recently
        now = timezone.now()
        QueueItem.objects.create(
            room=self.room,
            video_id="playedvid01",
            title="Old 1",
            added_by_id=self.user1_id,
            status=QueueItem.Status.PLAYED,
            played_at=now - timedelta(minutes=10),
        )
        QueueItem.objects.create(
            room=self.room,
            video_id="playedvid02",
            title="Old 2",
            added_by_id=self.user1_id,
            status=QueueItem.Status.PLAYED,
            played_at=now - timedelta(minutes=5),
        )

        # Both users add a song now
        item1 = QueueService.add_song(
            room=self.room,
            participant_id=self.user1_id,
            display_name="User 1",
            video_data={"video_id": "vid00000010", "title": "User 1 Song"},
        )
        item2 = QueueService.add_song(
            room=self.room,
            participant_id=self.user2_id,
            display_name="User 2",
            video_data={"video_id": "vid00000020", "title": "User 2 Song"},
        )

        # Even though item1 was added slightly earlier, User 2 has 0 recent plays vs User 1's 2 plays.
        # Fair-turn mode should give item2 priority!
        effective = self.room.get_effective_queue()
        self.assertEqual(effective[0].id, item2.id)


class TrackAdvancementAndModerationTests(OfficeJukeboxTestCase):
    """Test player track advancement, skipping, and authorization."""

    def test_advance_next_song(self):
        """Advancing transitions current track to PLAYED and activates next song."""
        self.settings_obj.user_song_cooldown_seconds = 0
        self.settings_obj.save()

        item1 = QueueService.add_song(
            room=self.room,
            participant_id="user1",
            display_name="User 1",
            video_data={"video_id": "vid00000001", "title": "Song 1"},
        )
        item2 = QueueService.add_song(
            room=self.room,
            participant_id="user2",
            display_name="User 2",
            video_data={"video_id": "vid00000002", "title": "Song 2"},
        )

        # Initial advance sets item1 to PLAYING
        playing = QueueService.advance_next_song(self.room)
        self.assertEqual(playing.id, item1.id)
        self.assertEqual(playing.status, QueueItem.Status.PLAYING)

        # Next advance transitions item1 to PLAYED, and item2 becomes PLAYING
        next_playing = QueueService.advance_next_song(self.room)
        self.assertEqual(next_playing.id, item2.id)
        self.assertEqual(next_playing.status, QueueItem.Status.PLAYING)

        item1.refresh_from_db()
        self.assertEqual(item1.status, QueueItem.Status.PLAYED)

    def test_remove_song_permissions(self):
        """Author can remove song; unauthorized user cannot."""
        self.settings_obj.user_song_cooldown_seconds = 0
        self.settings_obj.save()

        item = QueueService.add_song(
            room=self.room,
            participant_id="author-id",
            display_name="Author",
            video_data={"video_id": "vid00000001", "title": "Song 1"},
        )

        # Unauthorized removal attempt
        with self.assertRaises(ValidationError):
            QueueService.remove_song(item, participant_id="other-user", is_moderator=False)

        # Authorized author removal
        removed = QueueService.remove_song(item, participant_id="author-id", is_moderator=False)
        self.assertEqual(removed.status, QueueItem.Status.REMOVED)


class APIEndpointsIntegrationTests(OfficeJukeboxTestCase):
    """Integration tests for JSON API endpoints."""

    def test_api_room_state(self):
        """GET /api/rooms/<room_code>/state/ returns valid JSON schema and queue."""
        resp = self.client1.get(reverse("api_room_state", args=[self.room.code]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("hash", data)
        self.assertIn("queue", data)
        self.assertEqual(data["room"]["code"], self.room.code)

    def test_api_queue_add_endpoint(self):
        """POST /api/rooms/<room_code>/queue/add/ successfully queues song."""
        payload = {
            "video_id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "channel_title": "Rick Astley",
            "thumbnail_url": "https://example.com/rick.jpg",
            "duration_seconds": 212,
        }
        resp = self.client1.post(
            reverse("api_queue_add", args=[self.room.code]),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertTrue(QueueItem.objects.filter(room=self.room, video_id="dQw4w9WgXcQ").exists())
