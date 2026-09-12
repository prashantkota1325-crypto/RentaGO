"""
Session + RBAC helpers. Uses a signed cookie via itsdangerous to avoid a
server-side session store.

The cookie payload is {"user_id": <login username>}. RBAC is evaluated per
request by reading the user's role from the users table and the roles matrix.

Multi-login policy:
- Different users can login simultaneously (from PCs, mobiles, laptops, tablets
  at different locations).
- The same user cannot login on multiple devices at once: logging in from a new
  device automatically invalidates the previous session for that user.
"""

from datetime import datetime, timedelta
from fastapi import Request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

import threading
import time

from .config import settings
from .db import get_connection
from .audit import _parse_oracle_dt


def _serializer():
    return URLSafeTimedSerializer(settings.SECRET_KEY)


def create_session_token(user_id: str, sid: str = "") -> str:
    """Sign a session cookie carrying the user id and the session id (sid).

    The sid is validated against the user_sessions table on every request,
    which is what enforces the same-user single-session policy: logging in
    on a new device deletes the previous rows, so the old cookie's sid stops
    resolving and that device is logged out.
    """
    return _serializer().dumps({"user_id": user_id, "sid": sid})


def read_session_token(request: Request):
    """Return (user_id, sid) for the request's cookie, or None."""
    token = request.cookies.get("rentago_session")
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=settings.SESSION_TTL_MINUTES * 60)
        return (data.get("user_id"), (data.get("sid") or ""))
    except (BadSignature, SignatureExpired):
        return None


# ---------------------------------------------------------------------------
# Small TTL caches. Every cache hit avoids a sqlplus subprocess spawn (the
# fallback DB driver pays ~0.5-1s per query), which dominates page latency.
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_cache = {}


def _cache_get(key, ttl):
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] <= ttl:
            return hit[1]
        if hit:
            _cache.pop(key, None)
    return None


def _cache_put(key, value):
    with _cache_lock:
        if len(_cache) > 512:
            _cache.clear()
        _cache[key] = (time.monotonic(), value)


def _refresh_cached_tenant(user, conn):
    """Copy cached user data and refresh its current unambiguous tenant."""
    refreshed = dict(user)
    refreshed.pop("tenant_id", None)
    cur = conn.cursor()
    cur.execute(
        "SELECT tenant_id FROM tenant_memberships "
        "WHERE UPPER(user_id)=UPPER(:1) AND status='ACTIVE'",
        (refreshed.get("user_id"),),
    )
    memberships = [r[0] for r in cur.fetchall()]
    if len(memberships) == 1:
        refreshed["tenant_id"] = memberships[0]
    return refreshed


def current_user(request: Request):
    """Return a user dict (or None) for the current session.

    Same-user single-session enforcement: when the cookie carries a sid, it
    must still exist in user_sessions (rows are deleted when the user logs
    in elsewhere or logs out). The check is cached for 30s per sid to avoid
    a sqlplus spawn on every request. Cookies without a sid (issued before
    this policy existed) are honoured until their natural expiry.
    """
    parsed = read_session_token(request)
    if not parsed:
        return None
    uid, sid = parsed
    if not uid:
        return None
    session_mobile_booking_id = None
    session_mobile_expires_at = None
    if sid:
        ok = _cache_get(("sess", sid), 30)
        if ok is None:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM user_sessions "
                "WHERE session_id=:1 AND UPPER(user_id)=UPPER(:2)",
                (sid, uid),
            )
            row = cur.fetchone()
            conn.close()
            ok = bool(row and int(row[0] or 0) > 0)
            _cache_put(("sess", sid), ok)
        if not ok:
            return None  # session was invalidated by a newer login or logout
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT s.last_activity, u.role, s.mobile_booking_id, s.mobile_expires_at FROM user_sessions s JOIN users u "
            "ON UPPER(u.user_id)=UPPER(s.user_id) WHERE s.session_id=:1 AND UPPER(s.user_id)=UPPER(:2)",
            (sid, uid),
        )
        activity = cur.fetchone()
        if activity:
            role = (activity[1] or "").strip().lower()
            mobile_booking_id = activity[2]
            mobile_expires_at = _parse_oracle_dt(activity[3]) if activity[3] else None
            session_mobile_booking_id = mobile_booking_id
            session_mobile_expires_at = mobile_expires_at
            if mobile_booking_id and not mobile_expires_at:
                cur.execute("SELECT status_reason FROM bookings WHERE booking_id=:1", (mobile_booking_id,))
                booking_state = cur.fetchone()
                if booking_state and str(booking_state[0] or "").strip() == "Trip Completed":
                    cur.execute("UPDATE user_sessions SET mobile_expires_at=SYSDATE+(10/1440) WHERE session_id=:1", (sid,))
                    conn.commit()
                    mobile_expires_at = datetime.now() + timedelta(minutes=10)
                    session_mobile_expires_at = mobile_expires_at
            if mobile_expires_at and datetime.now() >= mobile_expires_at:
                cur.execute("DELETE FROM user_sessions WHERE session_id=:1", (sid,))
                conn.commit(); conn.close(); invalidate_session_cache(sid); return None
            external = {"super admin", "corporate admin", "corporate booking user", "corporate manager",
                        "corporate viewer", "vendor", "vendor admin", "vendor operations",
                        "vendor viewer", "guest", "driver"}
            last = _parse_oracle_dt(activity[0])
            if role not in external and last and (datetime.now() - last).total_seconds() > settings.INTERNAL_IDLE_TIMEOUT_MINUTES * 60:
                cur.execute("DELETE FROM user_sessions WHERE session_id=:1", (sid,))
                conn.commit()
                conn.close()
                invalidate_session_cache(sid)
                return None
            if role not in external:
                cur.execute("UPDATE user_sessions SET last_activity=SYSDATE WHERE session_id=:1", (sid,))
                conn.commit()
        conn.close()
    cached = _cache_get(("user", uid), 60)
    if cached is not None:
        conn = get_connection()
        try:
            user = _refresh_cached_tenant(cached, conn)
        finally:
            conn.close()
    else:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, user_id, name, email, company_name, role, emp_id, mobile, "
            "organization_id, organization_type, platform_owner "
            "FROM users WHERE UPPER(user_id)=UPPER(:1) AND status='Active'",
            (uid,),
        )
        row = cur.fetchone()
        if not row:
            return None
        user = {
            "user_no": row[0],
            "user_id": row[1],
            "name": row[2],
            "email": row[3],
            "company": row[4],
            "company_name": row[4],
            "role": row[5],
            "emp_id": row[6],
            "mobile": row[7],
            "organization_id": row[8],
            "organization_type": row[9],
            "platform_owner": row[10],
        }
        tcur = conn.cursor()
        tcur.execute("SELECT tenant_id FROM tenant_memberships WHERE UPPER(user_id)=UPPER(:1) AND status='ACTIVE'", (uid,))
        memberships = [r[0] for r in tcur.fetchall()]
        if len(memberships) == 1:
            user["tenant_id"] = memberships[0]
        conn.close()
        _cache_put(("user", uid), dict(user))
    # Session-specific booking context must not be stored in the per-user cache.
    user["mobile_booking_id"] = session_mobile_booking_id
    user["mobile_expires_at"] = session_mobile_expires_at
    return user


def has_access(user, sheet: str) -> str | None:
    """
    Determine access to a 'sheet' (module) for the current user.
    Returns 'F' (full), 'V' (view), or None (no access).
    Super Admin bypasses the matrix entirely -> Full.
    """
    if user is None:
        return None
    if user.get("role", "").lower() in ("super admin", "hq"):
        return "F"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT access_level FROM roles WHERE UPPER(sheet)=UPPER(:1) "
        "AND UPPER(role_code)=UPPER(:2) AND ROWNUM=1",
        (sheet, user.get("role")),
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


# Roles that always keep at least view access to the core record modules so
# they can see their OWN bookings/trips/invoices (data scoping in scope.py
# already restricts what rows they see).
ACCOUNT_ROLES = {
    "guest", "vendor", "vendor admin", "vendor operations", "vendor viewer", "driver",
    "corporate admin", "corporate booking user", "corporate manager", "corporate viewer",
}
REPORT_PORTAL_ROLES = {
    "corporate admin", "corporate booking user", "corporate manager", "corporate viewer",
    "vendor", "vendor admin", "vendor operations", "vendor viewer",
}
FEEDBACK_EXTERNAL_ROLES = {
    "corporate admin", "corporate booking user", "corporate manager", "corporate viewer",
    "vendor", "vendor admin", "vendor operations", "vendor viewer", "guest", "driver",
}
TRACKING_PORTAL_ROLES = {
    "corporate admin", "corporate booking user", "corporate manager", "corporate viewer",
}

# Modules an entirely unknown role (no matrix rows at all, e.g. a legacy role
# name imported from the workbook) may still view, to avoid lockouts.
CORE_MODULES = {"bookings", "trips", "invoices", "payments"}


def module_access(user) -> dict:
    """Return {sheet_name: 'F' | 'V' | None} for the user's role (one query,
    5-minute TTL cache — the matrix rarely changes and every hit saves a
    sqlplus subprocess spawn).

    Super Admin / HQ bypass with Full everywhere. Roles absent from the matrix
    get an empty dict (treated by module_level() with a lenient fallback).
    """
    if not user:
        return {}
    role = (user.get("role") or "").strip()
    if role.lower() in ("super admin", "hq"):
        return {"*": "F"}
    cached = _cache_get(("roles", role.lower()), 300)
    if cached is not None:
        return cached
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT sheet, access_level FROM roles WHERE UPPER(role_code)=UPPER(:1)",
        (role,),
    )
    rows = cur.fetchall()
    conn.close()
    out = {}
    for sheet, level in rows:
        key = str(sheet or "").strip()
        val = str(level or "").strip().upper()
        out[key] = val if val in ("F", "V") else None
    _cache_put(("roles", role.lower()), out)
    return out


def module_level(user, module: str) -> str | None:
    """Access level for a module, with the account-model fallbacks applied.

    Returns 'F' (full/edit), 'V' (view-only), or None (no access).
    """
    if not user:
        return None
    acc = module_access(user)
    if "*" in acc:
        return "F"
    module_l = (module or "").strip().lower()
    role_l = (user.get("role") or "").strip().lower()
    for sheet, level in acc.items():
        if sheet.lower() == module_l:
            return level
    # Account-model roles keep personal view access to core modules even when
    # the matrix has no row (their row visibility is identity-scoped).
    if role_l in ACCOUNT_ROLES and module_l in ("bookings", "trips", "invoices"):
        return "V"
    if role_l in REPORT_PORTAL_ROLES and module_l == "reports":
        return "V"
    if role_l in TRACKING_PORTAL_ROLES and module_l == "tracking dashboard":
        return "V"
    if module_l == "feedback" and role_l not in FEEDBACK_EXTERNAL_ROLES and role_l != "":
        return "V"
    if module_l == "sla dashboard" and role_l not in FEEDBACK_EXTERNAL_ROLES and role_l != "":
        return "V"
    if module_l == "policies" and role_l not in FEEDBACK_EXTERNAL_ROLES and role_l != "":
        return "V"
    # A role the matrix has never heard of: lenient view on core modules only.
    if not acc and module_l in CORE_MODULES:
        return "V"
    return None


def is_platform_owner(user):
    return bool(user) and str(user.get("platform_owner") or "N").upper() == "Y"


# Role -> dashboard sheet used for the navbar Dashboard link.
ROLE_DASHBOARD_SHEET = {
    "vendor": "Vendor Dashboard",
    "corporate admin": "Customer 360",
    "sales": "Sales Dashboard",
    "finance": "Finance Dashboard",
    "investor": "Investor MIS",
    "compliance": "Compliance",
    "operations": "Ops Dashboard",
    "vendor manager": "Ops Dashboard",
    "ceo": "CEO Dashboard",
}

# Roles that see the notifications outbox link in the navbar.
NOTIFICATION_ROLES = {
    "super admin", "hq", "ceo", "operations", "vendor manager",
    "finance", "compliance", "corporate admin",
}


def nav_levels(user) -> dict:
    """Nav visibility levels computed with a single matrix query.

    Returns {'bookings': 'F'|'V'|None, 'trips': ..., 'invoices': ...,
    'payments': ..., 'dashboards': ..., 'notifications': ...}.
    """
    if not user:
        return {}
    from .scope import OPERATOR_ROLES

    role = (user.get("role") or "").strip().lower()
    if role in ("guest", "driver"):
        return {"bookings": "V"}
    if role in ("super admin", "hq"):
        return {"bookings": "F", "trips": "F", "invoices": "F",
                "payments": "F", "dashboards": "F", "notifications": "F",
                "masters": "F", "reports": "F", "tracking": "F", "feedback": "F"}
    acc = module_access(user)

    def lookup(sheet):
        for s, v in acc.items():
            if s.lower() == sheet.lower():
                return v
        return None

    out = {}
    for key, sheet in (("bookings", "Bookings"), ("trips", "Trips"),
                       ("invoices", "Invoices"), ("payments", "Payments")):
        lvl = lookup(sheet)
        if lvl is None and role in ACCOUNT_ROLES and key != "payments":
            lvl = "V"
        if lvl is None and not acc and key in CORE_MODULES:
            lvl = "V"
        out[key] = lvl

    dash_sheet = ROLE_DASHBOARD_SHEET.get(role)
    dash = lookup(dash_sheet) if dash_sheet else None
    if dash is None and role in OPERATOR_ROLES:
        dash = "V"
    if dash is None and dash_sheet and not acc:
        dash = "V"
    out["dashboards"] = dash
    out["notifications"] = "V" if role in NOTIFICATION_ROLES else None

    reports = lookup("Reports")
    if reports is None and (role in ("super admin", "hq") or role in REPORT_PORTAL_ROLES):
        reports = "F"
    out["reports"] = reports

    tracking = lookup("Tracking Dashboard")
    if tracking is None and role in TRACKING_PORTAL_ROLES:
        tracking = "V"
    out["tracking"] = tracking
    out["feedback"] = "V" if role not in FEEDBACK_EXTERNAL_ROLES else None
    out["sla"] = "V" if role not in FEEDBACK_EXTERNAL_ROLES else None
    out["policies"] = "V" if role not in FEEDBACK_EXTERNAL_ROLES else None

    master_sheets = ("Companies", "Employees", "Vendors", "Vehicles", "Drivers",
                      "Ratecards", "Leads", "Contracts", "Contacts", "Individuals",
                      "Settings")
    masters = None
    for sheet in master_sheets:
        if lookup(sheet):
            masters = "V"
            break
    if masters is None and role in ("super admin", "hq"):
        masters = "F"
    out["masters"] = masters
    return out


def clear_roles_cache():
    """Drop cached roles-matrix lookups (call after the matrix is edited)."""
    with _cache_lock:
        stale = [k for k in _cache
                 if isinstance(k, tuple) and k and k[0] == "roles"]
        for k in stale:
            _cache.pop(k, None)


def invalidate_user_cache(uid):
    """Drop the cached user row (call after her profile/role is edited)."""
    if not uid:
        return
    target = str(uid).strip().lower()
    with _cache_lock:
        stale = [k for k in _cache
                 if isinstance(k, tuple) and len(k) == 2
                 and k[0] == "user" and str(k[1]).strip().lower() == target]
        for k in stale:
            _cache.pop(k, None)


def invalidate_session_cache(sid):
    """Drop the cached validity of a session id (call on logout so the
    cookie dies immediately instead of after the 30s TTL)."""
    if not sid:
        return
    with _cache_lock:
        _cache.pop(("sess", sid), None)


def get_user_session_count(cur, user_id: str) -> int:
    """Return the number of active sessions for this user."""
    cur.execute(
        "SELECT COUNT(*) FROM user_sessions WHERE UPPER(user_id)=UPPER(:1)",
        (user_id,),
    )
    row = cur.fetchone()
    return row[0] if row else 0


def cleanup_old_sessions(cur, user_id: str, keep_session: str = None) -> str:
    """Invalidate all sessions for a user except keep_session.
    Returns the session_id that was kept (or None if all were invalidated)."""
    if keep_session:
        cur.execute(
            "DELETE FROM user_sessions WHERE UPPER(session_id)=UPPER(:1) AND UPPER(user_id)=UPPER(:2)",
            (keep_session, user_id),
        )
        # Return the session that was kept if it still exists
        cur.execute(
            "SELECT session_id FROM user_sessions WHERE UPPER(session_id)=UPPER(:1) AND UPPER(user_id)=UPPER(:2)",
            (keep_session, user_id),
        )
        row = cur.fetchone()
        return row[0] if row else None
    else:
        # Invalidate all sessions for this user
        cur.execute(
            "DELETE FROM user_sessions WHERE UPPER(user_id)=UPPER(:1)",
            (user_id,),
        )
        return None


def mark_session_active(cur, session_id: str, user_id: str, ip_address: str = None):
    """Mark a session as active (upsert)."""
    cur.execute(
        "MERGE INTO user_sessions s USING dual ON (s.session_id = :1) "
        "WHEN MATCHED THEN UPDATE SET s.login_dt = SYSDATE, s.ip_address = :3 "
        "WHEN NOT MATCHED THEN INSERT (session_id, user_id, login_dt, ip_address) "
        "VALUES (:1, :2, SYSDATE, :3)",
        (session_id, user_id, ip_address),
    )
