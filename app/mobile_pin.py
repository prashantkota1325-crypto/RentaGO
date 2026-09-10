"""Internal RentaGO Guest/Driver PIN authentication helpers."""

import re
from datetime import datetime, timedelta

from .security import hash_password, verify_password


def valid_pin(pin):
    return bool(re.fullmatch(r"\d{4}", (pin or "").strip()))


def pin_hash(pin):
    if not valid_pin(pin):
        raise ValueError("Mobile PIN must be exactly four digits")
    return hash_password(pin.strip())


def pin_matches(pin, stored_hash):
    return valid_pin(pin) and verify_password(pin.strip(), stored_hash)


def find_mobile_user(cur, identity, role):
    cur.execute(
        "SELECT user_id,name,email,mobile,role,mobile_pin_hash,status FROM users "
        "WHERE status='Active' AND LOWER(role)=LOWER(:1) "
        "AND (UPPER(user_id)=UPPER(:2) OR REPLACE(mobile,' ','')=REPLACE(:2,' ',''))",
        (role, identity.strip()),
    )
    return cur.fetchone()


def attempt_key(identity, role, booking_id):
    return f"{role.lower()}:{identity.strip().lower()}:{booking_id.strip().upper()}"


def attempt_allowed(cur, key):
    cur.execute("SELECT attempts,locked_until FROM mobile_login_attempts WHERE attempt_key=:1", (key,))
    row = cur.fetchone()
    if not row or not row[1]:
        return True
    locked = row[1]
    if isinstance(locked, str):
        from .audit import _parse_oracle_dt
        locked = _parse_oracle_dt(locked)
    return not locked or datetime.now() >= locked


def record_attempt(cur, key, success):
    cur.execute("SELECT attempts FROM mobile_login_attempts WHERE attempt_key=:1", (key,))
    row = cur.fetchone()
    attempts = 0 if success else int(row[0] or 0) + 1 if row else 1
    locked = None if success or attempts < 5 else datetime.now() + timedelta(minutes=15)
    cur.execute(
        "MERGE INTO mobile_login_attempts a USING (SELECT :1 k FROM dual) s ON (a.attempt_key=s.k) "
        "WHEN MATCHED THEN UPDATE SET attempts=:2,locked_until=:3,updated_at=SYSTIMESTAMP "
        "WHEN NOT MATCHED THEN INSERT (attempt_key,attempts,locked_until) VALUES (:4,:5,:6)",
        (key, attempts, locked, key, attempts, locked),
    )
