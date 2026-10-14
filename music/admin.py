"""Django admin integration for Office Jukebox models."""

from django.contrib import admin
from .models import Room, RoomSettings, Participant, QueueItem, Vote, PlayerState, AuditLog


class RoomSettingsInline(admin.StackedInline):
    model = RoomSettings
    can_delete = False


class PlayerStateInline(admin.StackedInline):
    model = PlayerState
    can_delete = False


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "office_ip", "created_at")
    search_fields = ("name", "code", "office_ip")
    inlines = [RoomSettingsInline, PlayerStateInline]


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ("display_name", "room", "is_moderator", "client_ip", "last_seen")
    list_filter = ("room", "is_moderator")
    search_fields = ("display_name", "client_ip")


@admin.register(QueueItem)
class QueueItemAdmin(admin.ModelAdmin):
    list_display = ("title", "room", "status", "vote_count", "added_by_name", "created_at")
    list_filter = ("room", "status")
    search_fields = ("title", "video_id", "added_by_name")


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("queue_item", "participant_id", "value", "created_at")
    search_fields = ("participant_id",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("actor_name", "action", "room", "created_at")
    list_filter = ("room", "action")
    search_fields = ("actor_name", "details")
