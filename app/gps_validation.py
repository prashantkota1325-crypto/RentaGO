"""Pure validation helpers for the authenticated GPS batch gateway."""

from datetime import datetime, timezone
from math import isfinite


def parse_captured_at(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing captured_at")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("invalid captured_at") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def validate_point(event):
    if not isinstance(event, dict):
        raise ValueError("invalid event")
    event_id = str(event.get("gps_event_id") or "").strip()
    sequence = event.get("sequence_number")
    try:
        sequence = int(sequence)
        lat = float(event["lat"])
        lon = float(event["lon"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid coordinates or sequence") from exc
    if not event_id or sequence < 1 or not isfinite(lat) or not isfinite(lon):
        raise ValueError("invalid event identity")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("coordinates out of range")
    accuracy = event.get("accuracy_m")
    if accuracy is not None and (not isfinite(float(accuracy)) or float(accuracy) < 0):
        raise ValueError("invalid accuracy")
    speed = event.get("speed_mps")
    if speed is not None and (not isfinite(float(speed)) or float(speed) < 0):
        raise ValueError("invalid speed")
    captured_at = parse_captured_at(event.get("captured_at"))
    return {"gps_event_id": event_id, "sequence_number": sequence,
            "lat": lat, "lon": lon, "accuracy_m": accuracy,
            "speed_mps": speed, "heading_deg": event.get("heading_deg"),
            "captured_at": captured_at}
