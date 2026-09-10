"""Database-backed login throttling for Year-1 production security."""

from datetime import datetime, timedelta


def login_allowed(conn, key):
    cur = conn.cursor(); cur.execute("SELECT locked_until FROM auth_login_attempts WHERE attempt_key=:1", (key,))
    row = cur.fetchone()
    if not row or not row[0]: return True
    locked = row[0]
    if isinstance(locked, str):
        from .audit import _parse_oracle_dt
        locked = _parse_oracle_dt(locked)
    return not locked or datetime.now() >= locked


def record_login_attempt(conn, key, success):
    cur = conn.cursor(); cur.execute("SELECT attempts FROM auth_login_attempts WHERE attempt_key=:1", (key,)); row = cur.fetchone()
    attempts = 0 if success else (int(row[0] or 0) + 1 if row else 1)
    locked = None if success or attempts < 5 else datetime.now() + timedelta(minutes=15)
    cur.execute("MERGE INTO auth_login_attempts a USING (SELECT :1 k FROM dual) s ON (a.attempt_key=s.k) WHEN MATCHED THEN UPDATE SET attempts=:2,locked_until=:3,updated_at=SYSTIMESTAMP WHEN NOT MATCHED THEN INSERT (attempt_key,attempts,locked_until) VALUES (:4,:5,:6)", (key, attempts, locked, key, attempts, locked))
