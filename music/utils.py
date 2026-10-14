"""Utility functions for IP resolution, session identity, and data parsing."""

import ipaddress
import re
import uuid
from django.conf import settings


def get_client_ip(request):
    """Safely extract client IP address respecting trusted reverse proxy settings.

    Never trust raw client-provided headers indiscriminately.
    If behind N trusted reverse proxies (e.g. Render, Cloudflare),
    the genuine client IP is located N hops from the end of X-Forwarded-For.
    """
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    remote_addr = request.META.get("REMOTE_ADDR", "127.0.0.1")

    if xff:
        # Split and clean the IP chain
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            num_proxies = getattr(settings, "NUM_PROXIES", 1)
            # Pick the IP immediately preceding the trusted reverse proxies
            if len(parts) > num_proxies:
                candidate = parts[-1 - num_proxies]
            else:
                candidate = parts[0]

            try:
                # Validate that candidate is a valid IP
                parsed = ipaddress.ip_address(candidate)
                return str(parsed)
            except ValueError:
                pass

    try:
        parsed = ipaddress.ip_address(remote_addr)
        return str(parsed)
    except ValueError:
        return "127.0.0.1"


def mask_ip(ip_str):
    """Mask an IP address to preserve office network privacy when displayed in UI."""
    if not ip_str:
        return "Unknown"
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        if ip_obj.is_loopback:
            return "Local Network (127.0.0.1)"
        if ip_obj.version == 4:
            octets = ip_str.split(".")
            if len(octets) == 4:
                return f"{octets[0]}.{octets[1]}.*.*"
        elif ip_obj.version == 6:
            parts = ip_str.split(":")
            if len(parts) >= 4:
                return f"{parts[0]}:{parts[1]}:****:****"
    except ValueError:
        pass
    return "Private Network"


def get_participant_id(request):
    """Retrieve or create a unique participant session identifier."""
    participant_id = request.session.get("participant_id")
    if not participant_id:
        participant_id = uuid.uuid4().hex
        request.session["participant_id"] = participant_id
        request.session.modified = True
    return participant_id


def get_display_name(request):
    """Get the employee's display name from their active session."""
    return request.session.get("display_name", "").strip()


def parse_youtube_duration(duration_iso):
    """Parse ISO 8601 duration string (e.g. 'PT3M45S', 'PT1H20M5S') to seconds."""
    if not duration_iso:
        return 0
    pattern = re.compile(
        r"P(?:(?P<days>\d+)D)?"
        r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?"
    )
    match = pattern.match(duration_iso)
    if not match:
        return 0
    parts = match.groupdict()
    days = int(parts.get("days") or 0)
    hours = int(parts.get("hours") or 0)
    minutes = int(parts.get("minutes") or 0)
    seconds = int(parts.get("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def format_duration(seconds):
    """Format duration seconds into MM:SS or H:MM:SS string."""
    seconds = int(seconds or 0)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
