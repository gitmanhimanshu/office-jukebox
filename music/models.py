"""Database models for Office Jukebox.

Defines Room, RoomSettings, Participant, QueueItem, Vote, PlayerState, and AuditLog.
Fully supports PostgreSQL (Neon/Supabase) and SQLite with transaction-safe queue operations.
"""

import uuid
import secrets
import string
from datetime import timedelta
from django.db import models, transaction
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


def generate_unique_room_code(length=6):
    """Generate a clean, unambiguous uppercase room code."""
    # Exclude characters like 0, O, 1, I to avoid human transcription errors
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Room(models.Model):
    """An office room where music is shared and voted upon."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, default="Office Jukebox")
    code = models.CharField(max_length=12, unique=True, db_index=True)
    office_ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    moderator_pin = models.CharField(max_length=128, blank=True, help_text="PIN for room moderation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.code:
            for _ in range(10):
                new_code = generate_unique_room_code()
                if not Room.objects.filter(code=new_code).exists():
                    self.code = new_code
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} [{self.code}]"

    def get_effective_queue(self):
        """Return the prioritized active queue items respecting fair-play rules.

        Queue Ordering Rules:
        1. Higher net vote score takes priority (-vote_count).
        2. In fair-turn mode: if votes are equal, prioritize participants who have had
           fewer songs played recently (in the last 2 hours).
        3. Strict FIFO: if votes and fairness are tied, first added plays first (created_at ASC).
        """
        items = list(self.queue_items.filter(status=QueueItem.Status.QUEUED))
        if not items:
            return []

        if not self.settings.fair_turn_mode:
            # Simple voting priority + FIFO tie-breaker
            items.sort(key=lambda item: (-item.vote_count, item.created_at))
            return items

        # Fair-turn calculation: count songs played by each participant recently
        two_hours_ago = timezone.now() - timedelta(hours=2)
        recent_played_counts = {}
        recent_items = self.queue_items.filter(
            status=QueueItem.Status.PLAYED,
            played_at__gte=two_hours_ago,
        ).values("added_by_id").annotate(count=models.Count("id"))

        for entry in recent_items:
            recent_played_counts[entry["added_by_id"]] = entry["count"]

        # Sort key:
        # 1. -vote_count (higher votes first)
        # 2. recent_played_count (fewer plays first)
        # 3. created_at (earlier added first)
        items.sort(
            key=lambda item: (
                -item.vote_count,
                recent_played_counts.get(item.added_by_id, 0),
                item.created_at,
            )
        )
        return items


class RoomSettings(models.Model):
    """Configurable room rules and fair-play settings."""

    room = models.OneToOneField(Room, on_delete=models.CASCADE, related_name="settings")
    max_active_songs_per_user = models.PositiveIntegerField(
        default=3,
        help_text="Maximum queued songs a single employee can have active at once.",
    )
    user_song_cooldown_seconds = models.PositiveIntegerField(
        default=60,
        help_text="Cooldown in seconds required before an employee can queue another song.",
    )
    fair_turn_mode = models.BooleanField(
        default=True,
        help_text="If enabled, gives priority to employees with fewer recently played songs on vote ties.",
    )
    auto_advance = models.BooleanField(
        default=True,
        help_text="Automatically load and start the next song when current track ends.",
    )
    poll_interval_ms = models.PositiveIntegerField(
        default=3000,
        help_text="Client poll interval in milliseconds (default 3000ms = 3 seconds).",
    )

    def __str__(self):
        return f"Settings for {self.room.code}"


class Participant(models.Model):
    """An employee or session participant in a room."""

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="participants")
    participant_id = models.CharField(max_length=64, db_index=True)
    display_name = models.CharField(max_length=50)
    is_moderator = models.BooleanField(default=False)
    client_ip = models.GenericIPAddressField(null=True, blank=True)
    last_seen = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("room", "participant_id")
        ordering = ["-last_seen"]

    def __str__(self):
        return f"{self.display_name} in {self.room.code}"


class QueueItem(models.Model):
    """A song in the room's shared queue."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PLAYING = "playing", "Playing"
        PLAYED = "played", "Played"
        SKIPPED = "skipped", "Skipped"
        REMOVED = "removed", "Removed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="queue_items")
    video_id = models.CharField(max_length=20, db_index=True)
    title = models.CharField(max_length=255)
    channel_title = models.CharField(max_length=255, blank=True)
    thumbnail_url = models.URLField(max_length=500, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    added_by_name = models.CharField(max_length=50)
    added_by_id = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    vote_count = models.IntegerField(default=1, db_index=True)
    played_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-vote_count", "created_at"]
        indexes = [
            models.Index(fields=["room", "status"]),
            models.Index(fields=["room", "video_id", "status"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.status}) [{self.vote_count} votes]"

    def recalculate_votes(self):
        """Update cached vote_count from Vote records atomically."""
        total = self.votes.aggregate(total=models.Sum("value"))["total"] or 0
        self.vote_count = total
        self.save(update_fields=["vote_count", "updated_at"])
        return total


class Vote(models.Model):
    """A vote cast by a participant on a queued song."""

    queue_item = models.ForeignKey(QueueItem, on_delete=models.CASCADE, related_name="votes")
    participant_id = models.CharField(max_length=64, db_index=True)
    value = models.IntegerField(default=1)  # 1 for upvote
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("queue_item", "participant_id")

    def __str__(self):
        return f"Vote {self.value} on {self.queue_item_id} by {self.participant_id}"


class PlayerState(models.Model):
    """Persistent playback state for the room's designated player."""

    room = models.OneToOneField(Room, on_delete=models.CASCADE, related_name="player_state")
    current_item = models.ForeignKey(
        QueueItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    is_playing = models.BooleanField(default=False)
    position_seconds = models.FloatField(default=0.0)
    active_player_token = models.CharField(max_length=64, blank=True)
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_player_online(self):
        """Returns True if the designated player sent a heartbeat in the last 20 seconds."""
        if not self.last_heartbeat:
            return False
        return (timezone.now() - self.last_heartbeat).total_seconds() < 20

    def __str__(self):
        playing_title = self.current_item.title if self.current_item else "Idle"
        return f"Player for {self.room.code}: {playing_title}"


class AuditLog(models.Model):
    """Audit log of moderation and queue events for accountability."""

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="audit_logs")
    actor_name = models.CharField(max_length=50)
    action = models.CharField(max_length=50)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.actor_name}: {self.action}"


@receiver(post_save, sender=Room)
def create_room_defaults(sender, instance, created, **kwargs):
    """Automatically create default RoomSettings and PlayerState when a Room is created."""
    if created:
        RoomSettings.objects.get_or_create(room=instance)
        PlayerState.objects.get_or_create(room=instance)
