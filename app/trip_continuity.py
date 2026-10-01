"""Trip Continuity identity and idempotent event helpers."""

import secrets
import uuid
from datetime import datetime


def _reference():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "RTT-" + "".join(secrets.choice(alphabet) for _ in range(6))


def create_trip_continuity(conn, tenant_id, mode, status="CREATED", booking_id=None,
                           driver_id=None, vehicle_id=None, guest_id=None,
                           source="BACKEND", offline_created="N", actual_pickup=None):
    cur = conn.cursor()
    continuity_id = str(uuid.uuid4())
    reference = _reference()
    cur.execute(
        "INSERT INTO trip_continuity (trip_continuity_id,trip_reference,booking_id,tenant_id,"
        "driver_id,vehicle_id,guest_id,trip_mode,status,actual_pickup_datetime,"
        "created_source,offline_created,sync_status) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,'SYNCED')",
        (continuity_id, reference, booking_id, tenant_id, driver_id, vehicle_id,
         guest_id, mode, status, actual_pickup, source, offline_created),
    )
    append_event(conn, continuity_id, "TRIP_CREATED", {"mode": mode}, "BACKEND")
    return continuity_id, reference


def append_event(conn, continuity_id, event_type, payload=None, actor_type="SYSTEM",
                 actor_id=None, device_id=None, event_timestamp=None,
                 idempotency_key=None):
    cur = conn.cursor()
    key = idempotency_key or f"{continuity_id}:{event_type}:{uuid.uuid4()}"
    cur.execute("SELECT event_id FROM trip_events WHERE trip_continuity_id=:1 AND idempotency_key=:2",
                (continuity_id, key))
    existing = cur.fetchone()
    if existing:
        return existing[0], False
    cur.execute("SELECT NVL(MAX(event_sequence),0)+1 FROM trip_events WHERE trip_continuity_id=:1",
                (continuity_id,))
    sequence = int(cur.fetchone()[0] or 1)
    event_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO trip_events (event_id,trip_continuity_id,event_type,event_sequence,"
        "event_timestamp,actor_type,actor_id,device_id,payload,idempotency_key,sync_status) "
        "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,'SYNCED')",
        (event_id, continuity_id, event_type, sequence, event_timestamp or datetime.now(),
         actor_type, actor_id, device_id, _payload(payload), key),
    )
    return event_id, True


def link_booking(conn, continuity_id, booking_id, user_id):
    cur = conn.cursor()
    cur.execute(
        "UPDATE trip_continuity SET booking_id=:1, status='BOOKING_LINKED', "
        "booking_linked_at=SYSTIMESTAMP, booking_linked_by=:2, updated_at=SYSTIMESTAMP "
        "WHERE trip_continuity_id=:3 AND booking_id IS NULL",
        (booking_id, user_id, continuity_id),
    )
    if cur.rowcount:
        cur.execute("UPDATE bookings SET trip_continuity_id=:1 WHERE booking_id=:2",
                    (continuity_id, booking_id))
        cur.execute("UPDATE trips SET trip_continuity_id=:1 WHERE booking_id=:2",
                    (continuity_id, booking_id))
        append_event(conn, continuity_id, "BOOKING_LINKED", {"booking_id": booking_id},
                     "USER", user_id)
        return True
    return False


def update_status(conn, continuity_id, status, event_type, actor_id=None, payload=None):
    cur = conn.cursor()
    cur.execute("UPDATE trip_continuity SET status=:1, updated_at=SYSTIMESTAMP WHERE trip_continuity_id=:2",
                (status, continuity_id))
    append_event(conn, continuity_id, event_type, payload, "USER", actor_id)


def _payload(value):
    if value is None:
        return None
    import json
    return json.dumps(value, separators=(",", ":"), default=str)
