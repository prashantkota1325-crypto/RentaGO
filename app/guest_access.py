"""Hashed, expiring Guest Trip Access credentials and sessions."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta


ACCESS_TTL = timedelta(hours=24)
SESSION_TTL = timedelta(hours=12)


def new_token():
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_access(conn, booking, created_by):
    raw, token_hash = new_token()
    access_id = "GTA-" + uuid.uuid4().hex
    now = datetime.now()
    expires = now + ACCESS_TTL
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO guest_trip_access (guest_trip_access_id,trip_continuity_id,booking_id,"
        "tenant_id,guest_id,token_hash,token_created_at,token_expires_at,status,created_by) "
        "VALUES (:1,:2,:3,:4,:5,:6,SYSTIMESTAMP,:7,'ACTIVE',:8)",
        (access_id, booking.get("trip_continuity_id"), booking.get("booking_id"),
         booking.get("tenant_id"), booking.get("emp_guest_id"), token_hash, expires, created_by),
    )
    return access_id, raw, expires


def validate_token(cur, raw_token):
    token_hash = hashlib.sha256(str(raw_token or "").encode("utf-8")).hexdigest()
    cur.execute(
        "SELECT guest_trip_access_id,trip_continuity_id,booking_id,tenant_id,guest_id,"
        "status,token_expires_at,revoked_at FROM guest_trip_access WHERE token_hash=:1",
        (token_hash,),
    )
    row = cur.fetchone()
    if not row or row[5] != "ACTIVE" or row[7] is not None:
        return None
    expires = row[6]
    if expires and hasattr(expires, "replace") and datetime.now() >= expires:
        return None
    return {"access_id": row[0], "trip_continuity_id": row[1], "booking_id": row[2],
            "tenant_id": row[3], "guest_id": row[4], "token_hash": token_hash,
            "expires_at": expires}


def create_session(conn, access):
    raw, session_hash = new_token()
    session_id = "GTS-" + uuid.uuid4().hex
    now = datetime.now()
    expires = min(access["expires_at"], now + SESSION_TTL) if access.get("expires_at") else now + SESSION_TTL
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO guest_trip_sessions (guest_session_id,guest_trip_access_id,"
        "trip_continuity_id,booking_id,tenant_id,session_hash,created_at,expires_at,last_used_at) "
        "VALUES (:1,:2,:3,:4,:5,:6,SYSTIMESTAMP,:7,SYSTIMESTAMP)",
        (session_id, access["access_id"], access.get("trip_continuity_id"),
         access.get("booking_id"), access["tenant_id"], session_hash, expires),
    )
    cur.execute("UPDATE guest_trip_access SET first_used_at=NVL(first_used_at,SYSTIMESTAMP), "
                "last_used_at=SYSTIMESTAMP WHERE guest_trip_access_id=:1", (access["access_id"],))
    return raw, expires


def session_access(cur, raw_session):
    session_hash = hashlib.sha256(str(raw_session or "").encode("utf-8")).hexdigest()
    cur.execute(
        "SELECT s.guest_trip_access_id,s.trip_continuity_id,s.booking_id,s.tenant_id,"
        "s.expires_at,a.status,a.revoked_at FROM guest_trip_sessions s "
        "JOIN guest_trip_access a ON a.guest_trip_access_id=s.guest_trip_access_id "
        "WHERE s.session_hash=:1",
        (session_hash,),
    )
    row = cur.fetchone()
    if not row or row[5] != "ACTIVE" or row[6] is not None:
        return None
    if row[4] and datetime.now() >= row[4]:
        return None
    cur.execute("UPDATE guest_trip_sessions SET last_used_at=SYSTIMESTAMP WHERE session_hash=:1",
                (session_hash,))
    return {"access_id": row[0], "trip_continuity_id": row[1], "booking_id": row[2],
            "tenant_id": row[3], "expires_at": row[4]}
