"""Opaque, expiring Universal RentaGO Access tokens."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta


TOKEN_TTL = timedelta(hours=24)


def new_token():
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def token_hash(raw):
    return hashlib.sha256(str(raw or "").encode("utf-8")).hexdigest()


def create_access(conn, *, role, user_id, tenant_id=None, booking_id=None,
                  driver_id=None, created_by=None, destination="mobile", session_id=None):
    raw, digest = new_token()
    access_id = "RUA-" + uuid.uuid4().hex
    expires = datetime.now() + TOKEN_TTL
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO universal_access_tokens "
        "(access_id,token_hash,role,user_id,driver_id,tenant_id,booking_id,destination," 
        "expires_at,status,created_by,created_at,session_id) "
        "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,'ACTIVE',:10,SYSTIMESTAMP,:11)",
        (access_id, digest, role.lower(), user_id, driver_id, tenant_id,
         booking_id, destination, expires, created_by, session_id),
    )
    return access_id, raw, expires


def load_access(cur, raw):
    cur.execute(
        "SELECT access_id,role,user_id,driver_id,tenant_id,booking_id,destination,"
        "expires_at,status,exchanged_at,session_id FROM universal_access_tokens WHERE token_hash=:1",
        (token_hash(raw),),
    )
    row = cur.fetchone()
    if not row:
        return None
    if row[8] != "ACTIVE" or (row[9] is not None):
        return None
    if row[7] and datetime.now() >= row[7]:
        return None
    return {
        "access_id": row[0], "role": str(row[1]).lower(), "user_id": row[2],
        "driver_id": row[3], "tenant_id": row[4], "booking_id": row[5],
        "destination": row[6], "expires_at": row[7],
        "session_id": row[10],
    }


def consume(cur, raw):
    cur.execute(
        "UPDATE universal_access_tokens SET exchanged_at=SYSTIMESTAMP,status='USED' "
        "WHERE token_hash=:1 AND status='ACTIVE' AND exchanged_at IS NULL",
        (token_hash(raw),),
    )
    return cur.rowcount == 1


def challenge():
    raw = secrets.token_urlsafe(24)
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()
