"""Views and API endpoints for Office Jukebox."""

import hashlib
import json
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib import messages

from .models import Room, RoomSettings, Participant, QueueItem, Vote, PlayerState, AuditLog
from .services import YouTubeService, QueueService, YouTubeAPIError
from .forms import JoinRoomForm, CreateRoomForm, RoomSettingsForm, ModeratorLoginForm
from .utils import get_client_ip, mask_ip, get_participant_id, get_display_name, format_duration


# ==========================================
# Template Views
# ==========================================

@ensure_csrf_cookie
def welcome_view(request):
    """Entry page: handles first-time display name entry and auto-joins office room by public IP."""
    client_ip = get_client_ip(request)
    participant_id = get_participant_id(request)
    session_display_name = get_display_name(request)
    current_room_code = request.session.get("current_room_code")

    # If employee already has display name and an active room, direct them to dashboard
    if session_display_name and current_room_code:
        room = Room.objects.filter(code=current_room_code).first()
        if room:
            return redirect("dashboard", room_code=room.code)

    # Detect if an existing room matches this office network IP
    detected_room = Room.objects.filter(office_ip=client_ip).first()

    if request.method == "POST":
        form = JoinRoomForm(request.POST)
        if form.is_valid():
            display_name = form.cleaned_data["display_name"]
            room_code = form.cleaned_data["room_code"]

            request.session["display_name"] = display_name

            if room_code:
                room = Room.objects.filter(code=room_code).first()
                if not room:
                    form.add_error("room_code", f"Room with code '{room_code}' was not found.")
                    return render(
                        request,
                        "welcome.html",
                        {
                            "form": form,
                            "detected_room": detected_room,
                            "client_ip_masked": mask_ip(client_ip),
                        },
                    )
            elif detected_room:
                room = detected_room
            else:
                # Create a default office room for this network
                room = Room.objects.create(
                    name=f"Office Jukebox ({mask_ip(client_ip)})",
                    office_ip=client_ip,
                )

            # Record or update participant
            Participant.objects.update_or_create(
                room=room,
                participant_id=participant_id,
                defaults={"display_name": display_name, "client_ip": client_ip},
            )

            request.session["current_room_code"] = room.code
            request.session.modified = True
            return redirect("dashboard", room_code=room.code)
    else:
        initial = {
            "display_name": session_display_name,
            "room_code": detected_room.code if detected_room else "",
        }
        form = JoinRoomForm(initial=initial)

    return render(
        request,
        "welcome.html",
        {
            "form": form,
            "detected_room": detected_room,
            "client_ip_masked": mask_ip(client_ip),
        },
    )


@ensure_csrf_cookie
def create_room_view(request):
    """Explicitly create a new room with custom name, optional PIN, and IP binding."""
    participant_id = get_participant_id(request)
    display_name = get_display_name(request)
    client_ip = get_client_ip(request)

    if not display_name:
        return redirect("welcome")

    if request.method == "POST":
        form = CreateRoomForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data["name"].strip()
            pin = form.cleaned_data["moderator_pin"].strip()
            bind_ip = form.cleaned_data["bind_to_my_ip"]

            room = Room.objects.create(
                name=name,
                moderator_pin=pin,
                office_ip=client_ip if bind_ip else None,
            )

            # The creator becomes moderator in their session
            request.session["is_moderator"] = True
            request.session["current_room_code"] = room.code

            Participant.objects.create(
                room=room,
                participant_id=participant_id,
                display_name=display_name,
                is_moderator=True,
                client_ip=client_ip,
            )

            AuditLog.objects.create(
                room=room,
                actor_name=display_name,
                action="CREATE_ROOM",
                details=f"Created room '{name}' [{room.code}]",
            )

            messages.success(request, f"Room '{room.name}' created! Share code: {room.code}")
            return redirect("dashboard", room_code=room.code)
    else:
        form = CreateRoomForm()

    return render(
        request,
        "create_room.html",
        {"form": form, "client_ip_masked": mask_ip(client_ip)},
    )


@ensure_csrf_cookie
def dashboard_view(request, room_code):
    """Main dashboard: search songs, view current track and shared queue, and vote."""
    room = get_object_or_404(Room, code=room_code.upper())
    participant_id = get_participant_id(request)
    display_name = get_display_name(request)
    client_ip = get_client_ip(request)

    if not display_name:
        request.session["pending_room_code"] = room.code
        return redirect("welcome")

    # Update participant activity
    Participant.objects.update_or_create(
        room=room,
        participant_id=participant_id,
        defaults={"display_name": display_name, "client_ip": client_ip},
    )

    request.session["current_room_code"] = room.code

    player_state, _ = PlayerState.objects.get_or_create(room=room)
    room_settings, _ = RoomSettings.objects.get_or_create(room=room)

    return render(
        request,
        "dashboard.html",
        {
            "room": room,
            "settings": room_settings,
            "player_state": player_state,
            "participant_id": participant_id,
            "display_name": display_name,
            "is_moderator": request.session.get("is_moderator", False),
        },
    )


@ensure_csrf_cookie
def player_view(request, room_code):
    """Dedicated player mode view for the office speaker computer."""
    room = get_object_or_404(Room, code=room_code.upper())
    player_state, _ = PlayerState.objects.get_or_create(room=room)

    return render(
        request,
        "player.html",
        {
            "room": room,
            "player_state": player_state,
        },
    )


@ensure_csrf_cookie
def moderator_view(request, room_code):
    """Moderator management panel for settings, skip controls, and audit logs."""
    room = get_object_or_404(Room, code=room_code.upper())
    display_name = get_display_name(request) or "Anonymous"
    is_moderator = request.session.get("is_moderator", False)

    pin_form = None
    settings_form = None

    # Check if room has PIN protection and session is not yet authorized
    if room.moderator_pin and not is_moderator:
        if request.method == "POST" and "claim_moderator" in request.POST:
            pin_form = ModeratorLoginForm(request.POST)
            if pin_form.is_valid():
                entered_pin = pin_form.cleaned_data["pin"].strip()
                if entered_pin == room.moderator_pin:
                    request.session["is_moderator"] = True
                    request.session.modified = True
                    is_moderator = True
                    messages.success(request, "Moderator access granted.")
                else:
                    pin_form.add_error("pin", "Incorrect moderator PIN.")
        else:
            pin_form = ModeratorLoginForm()

    if is_moderator or not room.moderator_pin:
        settings_obj, _ = RoomSettings.objects.get_or_create(room=room)
        if request.method == "POST" and "update_settings" in request.POST:
            settings_form = RoomSettingsForm(request.POST, instance=settings_obj)
            if settings_form.is_valid():
                settings_form.save()
                AuditLog.objects.create(
                    room=room,
                    actor_name=display_name,
                    action="SETTINGS_UPDATE",
                    details="Updated room settings and fairness parameters",
                )
                messages.success(request, "Room settings updated successfully.")
        else:
            settings_form = RoomSettingsForm(instance=settings_obj)

    audit_logs = room.audit_logs.all()[:30]
    participants = room.participants.filter(last_seen__gte=timezone.now() - timedelta(minutes=15))

    return render(
        request,
        "moderator.html",
        {
            "room": room,
            "is_moderator": is_moderator or not room.moderator_pin,
            "pin_form": pin_form,
            "settings_form": settings_form,
            "audit_logs": audit_logs,
            "active_participants": participants,
        },
    )


def leave_room_view(request):
    """Leave current room and return to welcome screen."""
    request.session.pop("current_room_code", None)
    request.session.pop("is_moderator", None)
    request.session.modified = True
    return redirect("welcome")


def change_name_view(request):
    """Quickly update employee display name."""
    if request.method == "POST":
        new_name = request.POST.get("display_name", "").strip()
        if len(new_name) >= 2:
            request.session["display_name"] = new_name
            participant_id = get_participant_id(request)
            Participant.objects.filter(participant_id=participant_id).update(display_name=new_name)
            messages.success(request, f"Display name updated to {new_name}")

    current_room_code = request.session.get("current_room_code")
    if current_room_code:
        return redirect("dashboard", room_code=current_room_code)
    return redirect("welcome")


# ==========================================
# REST / JSON API Endpoints
# ==========================================

@require_GET
def api_room_state(request, room_code):
    """Retrieve full room state, current track, active queue, and online count.

    Includes state hash for client-side diffing and minimal DOM churn.
    """
    room = get_object_or_404(Room, code=room_code.upper())
    participant_id = get_participant_id(request)

    # Touch participant last_seen timestamp
    Participant.objects.filter(room=room, participant_id=participant_id).update(last_seen=timezone.now())

    player_state, _ = PlayerState.objects.get_or_create(room=room)
    settings_obj, _ = RoomSettings.objects.get_or_create(room=room)

    # Get active participants (seen within last 2 minutes)
    online_cutoff = timezone.now() - timedelta(minutes=2)
    online_count = room.participants.filter(last_seen__gte=online_cutoff).count()

    # Current track info
    current_track = None
    if player_state.current_item and player_state.current_item.status == QueueItem.Status.PLAYING:
        item = player_state.current_item
        current_track = {
            "id": str(item.id),
            "video_id": item.video_id,
            "title": item.title,
            "channel_title": item.channel_title,
            "thumbnail_url": item.thumbnail_url,
            "duration_seconds": item.duration_seconds,
            "duration_formatted": format_duration(item.duration_seconds),
            "added_by_name": item.added_by_name,
            "is_playing": player_state.is_playing,
            "position_seconds": player_state.position_seconds,
        }

    # Effective prioritized queue
    effective_queue = room.get_effective_queue()
    voted_item_ids = set(
        Vote.objects.filter(
            queue_item__in=effective_queue,
            participant_id=participant_id,
        ).values_list("queue_item_id", flat=True)
    )

    is_moderator = request.session.get("is_moderator", False) or not room.moderator_pin

    queue_data = []
    for rank, item in enumerate(effective_queue, start=1):
        queue_data.append({
            "id": str(item.id),
            "rank": rank,
            "video_id": item.video_id,
            "title": item.title,
            "channel_title": item.channel_title,
            "thumbnail_url": item.thumbnail_url,
            "duration_seconds": item.duration_seconds,
            "duration_formatted": format_duration(item.duration_seconds),
            "added_by_name": item.added_by_name,
            "vote_count": item.vote_count,
            "has_voted": item.id in voted_item_ids,
            "can_remove": (item.added_by_id == participant_id) or is_moderator,
            "created_at": item.created_at.isoformat(),
        })

    # Generate lightweight hash of state to allow client to skip DOM re-renders if unchanged
    state_payload = {
        "cur": current_track["id"] if current_track else None,
        "playing": player_state.is_playing,
        "q": [f"{q['id']}:{q['vote_count']}:{q['has_voted']}" for q in queue_data],
        "online": online_count,
        "player_online": player_state.is_player_online(),
    }
    state_hash = hashlib.md5(json.dumps(state_payload, sort_keys=True).encode()).hexdigest()

    return JsonResponse({
        "success": True,
        "hash": state_hash,
        "room": {
            "name": room.name,
            "code": room.code,
            "online_count": max(online_count, 1),
            "player_online": player_state.is_player_online(),
        },
        "settings": {
            "poll_interval_ms": settings_obj.poll_interval_ms,
            "max_active_songs_per_user": settings_obj.max_active_songs_per_user,
            "cooldown_seconds": settings_obj.user_song_cooldown_seconds,
            "fair_turn_mode": settings_obj.fair_turn_mode,
        },
        "current_track": current_track,
        "queue": queue_data,
        "user": {
            "participant_id": participant_id,
            "display_name": get_display_name(request),
            "is_moderator": is_moderator,
        },
    })


@require_GET
def api_youtube_search(request):
    """Search YouTube videos by query or URL with caching and rate-limiting."""
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse({"results": []})

    participant_id = get_participant_id(request)
    if not YouTubeService.check_search_rate_limit(participant_id):
        return JsonResponse(
            {"error": "Search rate limit reached. Please wait a moment before searching again."},
            status=429,
        )

    try:
        results = YouTubeService.search(query, max_results=12)
        return JsonResponse({"results": results})
    except YouTubeAPIError as e:
        return JsonResponse({"error": str(e)}, status=400)


@require_POST
def api_queue_add(request, room_code):
    """Add a selected video to the common room queue."""
    room = get_object_or_404(Room, code=room_code.upper())
    participant_id = get_participant_id(request)
    display_name = get_display_name(request) or "Colleague"

    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponseBadRequest("Invalid JSON body.")

    video_id = data.get("video_id", "").strip()
    if not video_id:
        return JsonResponse({"error": "Missing video ID."}, status=400)

    try:
        item = QueueService.add_song(
            room=room,
            participant_id=participant_id,
            display_name=display_name,
            video_data=data,
        )
        return JsonResponse({
            "success": True,
            "message": f"Added '{item.title}' to the queue!",
            "item_id": str(item.id),
        })
    except ValidationError as e:
        return JsonResponse({"error": e.message if hasattr(e, "message") else str(e)}, status=400)


@require_POST
def api_queue_vote(request, room_code, item_id):
    """Toggle upvote for a queue item."""
    room = get_object_or_404(Room, code=room_code.upper())
    participant_id = get_participant_id(request)
    queue_item = get_object_or_404(QueueItem, id=item_id, room=room)

    try:
        item, voted = QueueService.vote_song(queue_item, participant_id)
        return JsonResponse({
            "success": True,
            "vote_count": item.vote_count,
            "has_voted": voted,
        })
    except ValidationError as e:
        return JsonResponse({"error": str(e)}, status=400)


@require_POST
def api_queue_remove(request, room_code, item_id):
    """Remove a song from the queue (author or moderator only)."""
    room = get_object_or_404(Room, code=room_code.upper())
    participant_id = get_participant_id(request)
    display_name = get_display_name(request) or "User"
    is_moderator = request.session.get("is_moderator", False) or not room.moderator_pin
    queue_item = get_object_or_404(QueueItem, id=item_id, room=room)

    try:
        QueueService.remove_song(
            queue_item,
            participant_id=participant_id,
            is_moderator=is_moderator,
            actor_name=display_name,
        )
        return JsonResponse({"success": True, "message": "Song removed from queue."})
    except ValidationError as e:
        return JsonResponse({"error": str(e)}, status=403)


# ==========================================
# Player API Endpoints
# ==========================================

@require_POST
def api_player_heartbeat(request, room_code):
    """Report playback position and keep player online status alive."""
    room = get_object_or_404(Room, code=room_code.upper())
    player_state, _ = PlayerState.objects.get_or_create(room=room)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        data = {}

    position = float(data.get("position_seconds", 0.0))
    is_playing = bool(data.get("is_playing", False))

    player_state.position_seconds = position
    player_state.is_playing = is_playing
    player_state.last_heartbeat = timezone.now()
    player_state.save(update_fields=["position_seconds", "is_playing", "last_heartbeat", "updated_at"])

    return JsonResponse({"success": True})


@require_POST
def api_player_next(request, room_code):
    """Transition current track to played and advance to the next song."""
    room = get_object_or_404(Room, code=room_code.upper())
    next_song = QueueService.advance_next_song(room, mark_status=QueueItem.Status.PLAYED, actor_name="Office Speaker")

    if next_song:
        return JsonResponse({
            "success": True,
            "has_next": True,
            "track": {
                "id": str(next_song.id),
                "video_id": next_song.video_id,
                "title": next_song.title,
                "channel_title": next_song.channel_title,
                "thumbnail_url": next_song.thumbnail_url,
                "duration_seconds": next_song.duration_seconds,
            },
        })
    return JsonResponse({"success": True, "has_next": False, "track": None})


@require_POST
def api_player_skip(request, room_code):
    """Force skip the currently playing song (moderator or speaker control)."""
    room = get_object_or_404(Room, code=room_code.upper())
    is_moderator = request.session.get("is_moderator", False) or not room.moderator_pin
    display_name = get_display_name(request) or "Moderator"

    if not is_moderator:
        return JsonResponse({"error": "Only room moderators can skip the active track."}, status=403)

    next_song = QueueService.advance_next_song(room, mark_status=QueueItem.Status.SKIPPED, actor_name=display_name)

    if next_song:
        return JsonResponse({
            "success": True,
            "has_next": True,
            "track": {
                "id": str(next_song.id),
                "video_id": next_song.video_id,
                "title": next_song.title,
            },
        })
    return JsonResponse({"success": True, "has_next": False, "track": None})
