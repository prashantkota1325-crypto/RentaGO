"""Portal-level filtering for the shared notification outbox."""

CORPORATE_ROLES = {
    "corporate admin", "corporate booking user", "corporate manager", "corporate viewer",
}
VENDOR_ROLES = {"vendor", "vendor admin", "vendor operations", "vendor viewer"}


def can_see_notification(user, event):
    """Limit external portals to notifications addressed to their audience."""
    role = (user.get("role") or "").strip().lower()
    event_l = (event or "").strip().lower()
    if role in CORPORATE_ROLES:
        return event_l.endswith("-guest") or event_l.endswith("-admin")
    if role in VENDOR_ROLES:
        return event_l.endswith("-vendor")
    if role == "guest":
        return event_l.endswith("-guest") or event_l.endswith("-admin")
    if role == "driver":
        return event_l.endswith("-driver")
    return True
