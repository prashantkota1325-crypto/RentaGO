"""Audit trail + login/logout logging (AuditLog / LoginLogout Log ports).

Writes are best-effort: a logging failure must never break the business
action that triggered it.
"""

from datetime import datetime

from .db import get_connection


def _next_log_id(cur):
    """Next login_log id, continuing the LOG-000001 convention."""
    cur.execute("SELECT log_id FROM login_log")
    max_num = 0
    for (lid,) in cur.fetchall():
        s = str(lid or "").strip()
        if s.upper().startswith("LOG-"):
            try:
                n = int(s[4:])
                if n > max_num:
                    max_num = n
            except Exception:
                pass
    return "LOG-%06d" % (max_num + 1)


def record_login(conn, user):
    """Insert a login_log row (mirrors VBA LogLoginEvent). Best-effort."""
    try:
        cur = conn.cursor()
        now = datetime.now()
        cur.execute(
            "INSERT INTO login_log (log_id, user_id, emp_id, user_name, role, "
            "login_dt, log_date) VALUES (:1,:2,:3,:4,:5,:6,:7)",
            (_next_log_id(cur), user.get("user_id"), user.get("emp_id"),
             user.get("name"), user.get("role"), now, now.date()),
        )
    except Exception:
        pass


def _parse_oracle_dt(v):
    """Parse a DATE/TIMESTAMP value as returned by either driver.

    The sqlplus fallback renders timestamps like '31-AUG-26 12.23.47.000000 PM'
    and plain dates like '05-SEP-26'. Also accepts ISO datetime-local
    ('2026-08-31T14:30') and DD-MM-YYYY forms. Returns a datetime or None.
    """
    if not v:
        return None
    s = str(v).strip()
    if isinstance(v, datetime):
        return v
    import re
    s = re.sub(r"\.\d{3,}", "", s)  # drop fractional seconds only (keep HH.MM.SS)
    for fmt in ("%d-%b-%y %I.%M.%S %p", "%d-%b-%y %H.%M.%S",
                "%d-%b-%Y %I.%M.%S %p", "%d-%b-%Y %H.%M.%S",
                "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M:%S",
                "%d-%m-%Y %H:%M", "%Y-%m-%dT%H:%M",
                "%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def record_logout(conn, user):
    """Close the latest open login_log row for the user (mirrors VBA logout)."""
    try:
        cur = conn.cursor()
        # Only rows with a real login_dt: imported workbook rows have NULL
        # login_dt and must never receive a logout stamp (they would steal
        # the logout of the genuine session - Oracle sorts NULLS FIRST on
        # DESC, so a bare ORDER BY login_dt DESC picks them up).
        cur.execute(
            "SELECT log_id, login_dt FROM login_log WHERE UPPER(user_id)=UPPER(:1) "
            "AND logout_dt IS NULL AND login_dt IS NOT NULL "
            "ORDER BY login_dt DESC FETCH FIRST 1 ROWS ONLY",
            (user.get("user_id"),),
        )
        row = cur.fetchone()
        if not row:
            return
        now = datetime.now()
        login_dt = _parse_oracle_dt(row[1])
        if login_dt is not None:
            hours = round((now - login_dt).total_seconds() / 3600.0, 2)
        else:
            hours = None
        cur.execute(
            "UPDATE login_log SET logout_dt=:1, hours_worked=:2 WHERE log_id=:3",
            (now, hours, row[0]),
        )
    except Exception:
        pass


def audit(conn, user, action, record, notes=""):
    """Insert an audit_log row (mirrors VBA AuditLog writes). Best-effort."""
    try:
        cur = conn.cursor()
        now = datetime.now()
        cur.execute(
            "INSERT INTO audit_log (audit_date, audit_time, user_id, audit_user, "
            "action, record, notes, tenant_id) VALUES (:1,:2,:3,:4,:5,:6,:7,:8)",
            (now.date(), now.strftime("%H:%M:%S"),
             (user or {}).get("user_id"), (user or {}).get("name"),
             str(action)[:200], str(record)[:200], str(notes)[:500], (user or {}).get("tenant_id")),
        )
    except Exception:
        pass
