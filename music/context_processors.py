"""Template context processor to provide session identity and room status across views."""

from .utils import get_client_ip, mask_ip


def jukebox_context(request):
    """Inject common session variables and detected network details into templates."""
    client_ip = get_client_ip(request)
    display_name = request.session.get("display_name", "")
    current_room_code = request.session.get("current_room_code", "")
    is_moderator = request.session.get("is_moderator", False)

    return {
        "user_display_name": display_name,
        "current_room_code": current_room_code,
        "client_ip_detected": client_ip,
        "client_ip_masked": mask_ip(client_ip),
        "is_moderator_session": is_moderator,
    }
