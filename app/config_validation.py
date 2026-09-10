"""Validation helpers for administrator-authored JSON configuration."""

import json


def json_object(value, field_name):
    raw = (value or "{}").strip()
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return json.dumps(parsed, separators=(",", ":"))
