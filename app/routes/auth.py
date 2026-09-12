"""Authentication routes: login, logout, password change, registration, approval."""

from datetime import datetime
from urllib.parse import quote
import logging
import secrets
import re

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from ..auth import create_session_token, current_user, invalidate_user_cache, module_level
from ..templating import templates
from ..db import get_connection
from ..security import verify_password, hash_password, random_salt_hex, sha256_hex
from ..audit import audit, record_login, record_logout
from ..config import settings
from ..device import is_mobile_request
from ..ids import next_individual_id
from ..mobile_pin import pin_hash, valid_pin
from ..auth_rate_limit import login_allowed, record_login_attempt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

router = APIRouter(prefix="/auth")
logger = logging.getLogger(__name__)


def _valid_new_user_id(value):
    return bool(re.fullmatch(r"[A-Za-z0-9]+", (value or "").strip()))


def _mfa_serializer():
    return URLSafeTimedSerializer(settings.SECRET_KEY)


def _needs_email_mfa(role):
    return (role or "").strip().lower() != "driver"


def _complete_login(request, user, uid, portal_l):
    import uuid
    session_id = str(uuid.uuid4())
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_sessions WHERE UPPER(user_id)=UPPER(:1)", (uid,))
    cur.execute(
            "INSERT INTO user_sessions (session_id, user_id, login_dt, last_activity, ip_address) "
        "VALUES (:1, :2, SYSDATE, SYSDATE, :3)",
        (session_id, uid, request.client.host if request.client else None),
    )
    record_login(conn, user)
    audit(conn, user, "Login", uid, "")
    conn.commit()
    conn.close()
    token = create_session_token(uid, session_id)
    destination = {"corporate": "/dashboards/customer360", "vendor": "/dashboards/vendor",
                   "guest": "/mobile/guest", "driver": "/mobile/driver"}.get(portal_l, "/home")
    resp = RedirectResponse(url=destination, status_code=303)
    resp.set_cookie(key="rentago_session", value=token, httponly=True,
                    secure=settings.SESSION_COOKIE_SECURE, samesite="lax",
                    domain=settings.SESSION_COOKIE_DOMAIN)
    return resp


def _start_email_mfa(request, user, uid, portal_l):
    login_path = {"corporate": "corporate-login", "vendor": "vendor-login",
                  "guest": "guest-login"}.get(portal_l, "login")
    email = (user.get("email") or "").strip()
    if not email:
        return RedirectResponse(url=f"/auth/{login_path}?msg=mfa-email-missing", status_code=303)
    code = f"{secrets.randbelow(900000) + 100000}"
    challenge = _mfa_serializer().dumps({
        "user_id": uid, "portal": portal_l, "code_hash": sha256_hex(code),
    })
    try:
        from ..emailer import send_email
        send_email(email, "RentaGO login verification code",
                   f"Your RentaGO verification code is {code}. It expires in 5 minutes.")
    except Exception:
        logger.exception("Email MFA delivery failed for user id %s", uid)
        return RedirectResponse(url=f"/auth/{login_path}?msg=mfa-delivery-failed", status_code=303)
    resp = RedirectResponse(url="/auth/verify-otp", status_code=303)
    resp.set_cookie("rentago_mfa", challenge, httponly=True,
                    secure=settings.SESSION_COOKIE_SECURE, samesite="lax", max_age=300)
    return resp

REGISTRATION_ROLES = [
    "Sales", "Operations", "Finance", "Vendor Manager", "HR",
    "Customer Service", "Compliance", "Corporate Admin", "Vendor", "Driver", "Investor",
]


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html", {"request": request, "app_name": settings.APP_NAME,
                        "portal": "internal"}
    )


def _portal_login_page(request: Request, portal: str):
    if portal in ("guest", "driver") and not is_mobile_request(request):
        return HTMLResponse(
            "Guest and Driver access is available only from a mobile phone or tablet.",
            status_code=403,
        )
    return templates.TemplateResponse(
        "login.html", {"request": request, "app_name": settings.APP_NAME,
                        "portal": portal}
    )


@router.get("/corporate-login")
def corporate_login_page(request: Request):
    return _portal_login_page(request, "corporate")


@router.get("/vendor-login")
def vendor_login_page(request: Request):
    return _portal_login_page(request, "vendor")


@router.get("/guest-login")
def guest_login_page(request: Request):
    return _portal_login_page(request, "guest")


@router.get("/driver-login")
def driver_login_page(request: Request):
    return _portal_login_page(request, "driver")


@router.post("/login")
def login(request: Request, user_id: str = Form(...), password: str = Form(...),
          portal: str = Form("internal")):
    import uuid
    if portal.strip().lower() in ("guest", "driver") and not is_mobile_request(request):
        return HTMLResponse(
            "Guest and Driver access is available only from a mobile phone or tablet.",
            status_code=403,
        )
    try:
        rate_conn = get_connection(); rate_key = f"login:{request.client.host if request.client else 'unknown'}:{user_id.strip().lower()}"
        if not login_allowed(rate_conn, rate_key):
            rate_conn.close(); return RedirectResponse(url="/auth/login?msg=login-rate-limited", status_code=303)
        rate_conn.close()
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, password_hash, status, name, email, company_name, role, "
            "emp_id, mobile FROM users WHERE UPPER(user_id)=UPPER(:1) AND ROWNUM=1",
            (user_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            rc = get_connection(); record_login_attempt(rc, rate_key, False); rc.commit(); rc.close()
            return RedirectResponse(url="/auth/login?msg=unknown-user", status_code=303)
        uid, pw_hash, status = row[0], row[1], row[2]
        user = {
            "user_id": row[0], "name": row[3], "email": row[4], "company": row[5],
            "company_name": row[5], "role": row[6], "emp_id": row[7], "mobile": row[8],
        }
        role_l = (user.get("role") or "").strip().lower()
        portal_l = (portal or "internal").strip().lower()
        if portal_l == "corporate" and not role_l.startswith("corporate"):
            return RedirectResponse(url="/auth/corporate-login?msg=portal-invalid", status_code=303)
        if portal_l == "vendor" and role_l not in {
            "vendor", "vendor admin", "vendor operations", "vendor manager", "vendor viewer",
        }:
            return RedirectResponse(url="/auth/vendor-login?msg=portal-invalid", status_code=303)
        if portal_l == "guest" and role_l != "guest":
            return RedirectResponse(url="/auth/guest-login?msg=portal-invalid", status_code=303)
        if portal_l == "driver" and role_l != "driver":
            return RedirectResponse(url="/auth/driver-login?msg=portal-invalid", status_code=303)
        if not verify_password(password, pw_hash):
            rc = get_connection(); record_login_attempt(rc, rate_key, False); rc.commit(); rc.close()
            return RedirectResponse(url="/auth/login?msg=invalid-password", status_code=303)
        if status and status.lower() != "active":
            if status.lower() == "rejected":
                return RedirectResponse(url="/auth/login?msg=rejected", status_code=303)
            return RedirectResponse(url="/auth/login?msg=pending", status_code=303)

        rc = get_connection(); record_login_attempt(rc, rate_key, True); rc.commit(); rc.close()

        if _needs_email_mfa(role_l):
            return _start_email_mfa(request, user, uid, portal_l)
        return _complete_login(request, user, uid, portal_l)
    except Exception:
        logger.exception("Login failed for user id %s", user_id)
        return RedirectResponse(url="/auth/login?msg=error", status_code=303)


@router.post("/corporate-login")
def corporate_login(request: Request, user_id: str = Form(...), password: str = Form(...)):
    return login(request, user_id, password, "corporate")


@router.post("/vendor-login")
def vendor_login(request: Request, user_id: str = Form(...), password: str = Form(...)):
    return login(request, user_id, password, "vendor")


@router.post("/guest-login")
def guest_login(request: Request, user_id: str = Form(...), password: str = Form(...)):
    return login(request, user_id, password, "guest")


@router.post("/driver-login")
def driver_login(request: Request, user_id: str = Form(...), password: str = Form(...)):
    return login(request, user_id, password, "driver")


@router.get("/verify-otp")
def verify_otp_page(request: Request):
    return templates.TemplateResponse(
        "verify_otp.html", {"request": request, "app_name": settings.APP_NAME}
    )


@router.post("/verify-otp")
def verify_otp(request: Request, code: str = Form(...)):
    challenge = request.cookies.get("rentago_mfa")
    try:
        data = _mfa_serializer().loads(challenge or "", max_age=300)
    except (BadSignature, SignatureExpired):
        return RedirectResponse(url="/auth/login?msg=mfa-expired", status_code=303)
    if not secrets.compare_digest(sha256_hex(code.strip()), data.get("code_hash", "")):
        return RedirectResponse(url="/auth/verify-otp?msg=mfa-invalid", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, name, email, company_name, role, emp_id, mobile "
        "FROM users WHERE UPPER(user_id)=UPPER(:1) AND status='Active' AND ROWNUM=1",
        (data.get("user_id"),),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return RedirectResponse(url="/auth/login?msg=unknown-user", status_code=303)
    user = {"user_id": row[0], "name": row[1], "email": row[2],
            "company": row[3], "company_name": row[3], "role": row[4],
            "emp_id": row[5], "mobile": row[6]}
    try:
        resp = _complete_login(request, user, row[0], data.get("portal", "internal"))
    except Exception:
        logger.exception("MFA session finalization failed for user id %s", row[0])
        return RedirectResponse(url="/auth/login?msg=mfa-session-failed", status_code=303)
    resp.delete_cookie("rentago_mfa", samesite="lax")
    return resp


@router.get("/logout")
def logout(request: Request):
    from ..auth import read_session_token, invalidate_session_cache

    user = current_user(request)
    parsed = read_session_token(request)
    sid = parsed[1] if parsed else ""
    if user:
        if (user.get("role") or "").strip().lower() == "guest":
            conn = get_connection()
            cur = conn.cursor()
            from ..scope import visible_booking_ids
            visible = visible_booking_ids(user, cur)
            if visible:
                marks = ",".join(f":{i + 1}" for i in range(len(visible)))
                cur.execute(
                    f"SELECT COUNT(*) FROM bookings WHERE booking_id IN ({marks}) "
                    "AND NVL(status_reason,'') NOT IN ('Guest Trip Ended - Awaiting Driver Confirmation','Trip Completed') "
                    "AND NOT booking_status LIKE '3-%'", list(visible))
                active = int(cur.fetchone()[0] or 0)
                conn.close()
                if active:
                    return RedirectResponse(url="/mobile/guest?msg=logout-after-end", status_code=303)
            else:
                conn.close()
        try:
            conn = get_connection()
            cur = conn.cursor()
            if sid:
                cur.execute(
                    "DELETE FROM user_sessions WHERE session_id=:1",
                    (sid,),
                )
            record_logout(conn, user)
            audit(conn, user, "Logout", user.get("user_id"), "")
            conn.commit()
            conn.close()
        except Exception:
            pass
    invalidate_session_cache(sid)
    resp = RedirectResponse(url="/auth/login?msg=logged-out", status_code=303)
    resp.delete_cookie("rentago_session", domain=settings.SESSION_COOKIE_DOMAIN, samesite="lax")
    return resp


@router.post("/change-password")
def change_password(request: Request, old: str = Form(...), new: str = Form(...)):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT password_hash FROM users WHERE UPPER(user_id)=UPPER(:1) AND ROWNUM=1", (user["user_id"],))
    row = cur.fetchone()
    if not row or not verify_password(old, row[0]):
        conn.close()
        return RedirectResponse(url="/home?msg=wrong-old", status_code=303)
    salt = random_salt_hex()
    new_hash = f"{salt}:{sha256_hex(salt + new)}"
    cur.execute("UPDATE users SET password_hash=:1, password_vault=NULL WHERE UPPER(user_id)=UPPER(:2)", (new_hash, user["user_id"]))
    audit(conn, user, "Password Changed", user["user_id"], "")
    conn.commit()
    conn.close()
    return RedirectResponse(url="/home?msg=pwd-changed", status_code=303)


@router.get("/change-password")
def change_password_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    return templates.TemplateResponse(
        "change_password.html",
        {"request": request, "user": user, "app_name": settings.APP_NAME,
         "msg": request.query_params.get("msg", "")},
    )


@router.get("/profile")
def profile_page(request: Request):
    """Show the signed-in user's account details without exposing credentials."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    return templates.TemplateResponse(
        "profile.html", {"request": request, "user": user,
                          "app_name": settings.APP_NAME},
    )


@router.get("/register")
def register_page(request: Request):
    msg = request.query_params.get("msg", "")
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "app_name": settings.APP_NAME,
         "roles": REGISTRATION_ROLES, "msg": msg},
    )


@router.post("/register")
def register(
    request: Request,
    user_id: str = Form(...),
    name: str = Form(...),
    email: str = Form(...),
    mobile: str = Form(""),
    company_name: str = Form(""),
    role: str = Form("Operations"),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    user_id = user_id.strip()
    name = name.strip()
    email = email.strip()
    if not user_id or not name or not email:
        return RedirectResponse(url="/auth/register?msg=missing", status_code=303)
    if not _valid_new_user_id(user_id):
        return RedirectResponse(url="/auth/register?msg=invalid-user-id", status_code=303)
    if password != confirm_password:
        return RedirectResponse(url="/auth/register?msg=password-mismatch", status_code=303)
    if len(password) < 6:
        return RedirectResponse(url="/auth/register?msg=password-short", status_code=303)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE UPPER(user_id)=UPPER(:1)", (user_id,))
    if int(cur.fetchone()[0]) > 0:
        conn.close()
        return RedirectResponse(url="/auth/register?msg=exists", status_code=303)

    new_hash = hash_password(password)
    cur.execute("SELECT NVL(MAX(user_no),0)+1 FROM users")
    next_no = int(cur.fetchone()[0])
    cur.execute(
        """INSERT INTO users (
            user_no, user_id, name, email, company_name, mobile, role,
            requested_role, status, password_hash, password_vault, created_dt
        ) VALUES (
            :1,:2,:3,:4,:5,:6,:7,:8,'Pending',:9,:10,:11
        )""",
        (
            next_no, user_id, name, email, company_name, mobile, role,
            role, new_hash, password, datetime.now(),
        ),
    )
    audit(conn, {"user_id": user_id, "name": name},
          "Registration Submitted", user_id, f"requested role {role}")
    conn.commit()
    conn.close()
    return RedirectResponse(url="/auth/register?msg=submitted", status_code=303)


@router.get("/pending-users")
def pending_users(request: Request):
    user = current_user(request)
    if not _can_approve(user):
        return RedirectResponse(url="/home", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, name, email, mobile, company_name, role, requested_role, "
        "created_dt, status FROM users WHERE status IN ('Pending','Rejected') "
        "ORDER BY created_dt NULLS LAST, user_id"
    )
    rows = cur.fetchall()
    cur.execute(
        "SELECT user_id, name, email, mobile, company_name, role, status "
        "FROM users WHERE status='Active' ORDER BY user_id"
    )
    active = cur.fetchall()
    conn.close()
    pending = []
    for r in rows:
        pending.append({
            "user_id": r[0], "name": r[1], "email": r[2], "mobile": r[3],
            "company": r[4], "role": r[5], "requested_role": r[6],
            "created_dt": r[7], "status": r[8],
        })
    active_users = [{
        "user_id": r[0], "name": r[1], "email": r[2], "mobile": r[3],
        "company": r[4], "role": r[5], "status": r[6],
    } for r in active]
    return templates.TemplateResponse(
        "pending_users.html",
        {"request": request, "user": user, "pending": pending,
         "active_users": active_users},
    )


@router.post("/approve/{user_id}")
def approve_user(request: Request, user_id: str, role: str = Form(...)):
    user = current_user(request)
    if not _can_approve(user):
        return RedirectResponse(url="/home", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET status='Active', role=:1, approved_by=:2, approved_dt=:3, "
        "reject_reason=NULL WHERE UPPER(user_id)=UPPER(:4)",
        (role, user["user_id"], datetime.now(), user_id),
    )
    audit(conn, user, "Registration Approved", user_id, f"role {role}")
    conn.commit()
    conn.close()
    return RedirectResponse(url="/auth/pending-users?approved=1", status_code=303)


@router.post("/reject/{user_id}")
def reject_user(request: Request, user_id: str, reason: str = Form("")):
    user = current_user(request)
    if not _can_approve(user):
        return RedirectResponse(url="/home", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET status='Rejected', reject_reason=:1, approved_by=:2, "
        "approved_dt=:3 WHERE UPPER(user_id)=UPPER(:4)",
        (reason, user["user_id"], datetime.now(), user_id),
    )
    audit(conn, user, "Registration Rejected", user_id, reason)
    conn.commit()
    conn.close()
    return RedirectResponse(url="/auth/pending-users?rejected=1", status_code=303)


# ---------------------------------------------------------------------------
# OTP password reset (SOP 3.3): Super Admin generates the OTP and relays it
# (email delivery follows the same tenant SMTP prerequisite as notifications);
# the user then sets a new password on the public reset page.
# ---------------------------------------------------------------------------
def _generate_otp():
    import random

    return f"{random.randint(100000, 999999)}"


def _next_otp_id(cur):
    cur.execute("SELECT otp_id FROM otp_log")
    max_num = 0
    for (oid,) in cur.fetchall():
        s = str(oid or "").strip()
        if s.upper().startswith("OTP-"):
            try:
                n = int(s[4:])
                if n > max_num:
                    max_num = n
            except Exception:
                pass
    return "OTP-%06d" % (max_num + 1)


@router.post("/generate-otp/{user_id}")
def generate_otp(request: Request, user_id: str):
    """Super Admin: generate a 15-minute password-reset OTP for a user.

    The OTP is shown once to the Super Admin (for relay until SMTP is enabled)
    and logged in otp_log.
    """
    user = current_user(request)
    if not _can_approve(user):
        return RedirectResponse(url="/home", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE UPPER(user_id)=UPPER(:1)",
                (user_id,))
    if not cur.fetchone():
        conn.close()
        return RedirectResponse(url="/auth/pending-users", status_code=303)
    code = _generate_otp()
    now = datetime.now()
    from datetime import timedelta

    expires = now + timedelta(minutes=15)
    cur.execute(
        "UPDATE otp_log SET status='Expired' WHERE UPPER(user_id)=UPPER(:1) "
        "AND status='Active'",
        (user_id,),
    )
    cur.execute(
        "INSERT INTO otp_log (otp_id, user_id, otp_code, purpose, generated_by, "
        "generated_dt, expires_dt, status) VALUES (:1,:2,:3,'Password Reset',:4,:5,:6,'Active')",
        (_next_otp_id(cur), user_id, code, user["user_id"], now, expires),
    )
    audit(conn, user, "Reset OTP Generated", user_id, "")
    conn.commit()
    conn.close()
    return RedirectResponse(
        url=f"/auth/pending-users?otp={code}&for={quote(user_id)}", status_code=303
    )


@router.get("/reset")
def reset_page(request: Request):
    msg = request.query_params.get("msg", "")
    return templates.TemplateResponse(
        "reset.html", {"request": request, "app_name": settings.APP_NAME, "msg": msg}
    )


@router.post("/reset")
def reset_password(
    request: Request,
    user_id: str = Form(...),
    otp: str = Form(...),
    new: str = Form(...),
    confirm: str = Form(...),
):
    """Public: set a new password using an OTP relayed by the Super Admin."""
    if new != confirm:
        return RedirectResponse(url="/auth/reset?msg=password-mismatch", status_code=303)
    if len(new) < 6:
        return RedirectResponse(url="/auth/reset?msg=password-short", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT otp_code, status, TO_CHAR(expires_dt, 'YYYY-MM-DD HH24:MI:SS') "
        "FROM otp_log WHERE UPPER(user_id)=UPPER(:1) AND status='Active' "
        "ORDER BY generated_dt DESC FETCH FIRST 1 ROWS ONLY",
        (user_id.strip(),),
    )
    row = cur.fetchone()
    if not row or str(row[0]).strip() != str(otp).strip():
        conn.close()
        return RedirectResponse(url="/auth/reset?msg=otp-invalid", status_code=303)
    if row[1] != "Active":
        conn.close()
        return RedirectResponse(url="/auth/reset?msg=otp-invalid", status_code=303)
    try:
        if datetime.now() > datetime.strptime(str(row[2]), "%Y-%m-%d %H:%M:%S"):
            cur.execute(
                "UPDATE otp_log SET status='Expired' WHERE UPPER(user_id)=UPPER(:1) "
                "AND status='Active'",
                (user_id.strip(),),
            )
            conn.commit()
            conn.close()
            return RedirectResponse(url="/auth/reset?msg=otp-expired", status_code=303)
    except Exception:
        pass

    salt = random_salt_hex()
    new_hash = f"{salt}:{sha256_hex(salt + new)}"
    cur.execute(
        "UPDATE users SET password_hash=:1, password_vault=NULL WHERE UPPER(user_id)=UPPER(:2)",
        (new_hash, user_id.strip()),
    )
    cur.execute(
        "UPDATE otp_log SET status='Used', used_dt=:1 WHERE UPPER(user_id)=UPPER(:2) "
        "AND status='Active'",
        (datetime.now(), user_id.strip()),
    )
    audit(conn, {"user_id": user_id.strip(), "name": ""},
          "Password Reset via OTP", user_id.strip(), "")
    conn.commit()
    conn.close()
    return RedirectResponse(url="/auth/login?msg=password-reset", status_code=303)


# ---------------------------------------------------------------------------
# User management (Super Admin): create users, edit details/role/status and
# reset passwords directly. Mirrors the Users sheet maintenance in the VBA
# workbook, with the same salted-hash password scheme.
# ---------------------------------------------------------------------------
USER_ROLES = [
    "Super Admin", "HQ", "CEO", "Operations", "Vendor Manager", "Sales",
    "Finance", "HR", "Customer Service", "Compliance", "Corporate Admin",
    "Investor", "Vendor", "Driver", "Guest",
]
USER_STATUSES = ["Active", "Pending", "Rejected", "Inactive"]


def _is_super_admin(user):
    return bool(user) and (user.get("role") or "").strip().lower() in ("super admin", "hq")


def _can_approve(user):
    return _is_super_admin(user) or module_level(user, "Approvals") == "F"


def _can_manage_users(user):
    return _is_super_admin(user) or module_level(user, "Users") == "F"


def _user_organizations():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT company_id, company_name FROM companies WHERE company_name IS NOT NULL AND (status IS NULL OR UPPER(status)='ACTIVE') ORDER BY company_name")
    companies = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    cur.execute("SELECT vendor_id, vendor_name FROM vendors WHERE vendor_name IS NOT NULL AND (status IS NULL OR UPPER(status)='ACTIVE') ORDER BY vendor_name")
    vendors = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    cur.execute("SELECT individual_id, guest_name, guest_email, guest_contact FROM individuals WHERE guest_name IS NOT NULL AND (status IS NULL OR UPPER(status)='ACTIVE') ORDER BY guest_name")
    individuals = [{"id": r[0], "name": r[1], "email": r[2], "mobile": r[3]} for r in cur.fetchall()]
    conn.close()
    return companies, vendors, individuals


@router.get("/user-directory")
def user_directory(request: Request, company_id: str = "", company_name: str = "",
                   kind: str = "corporate"):
    """Return people eligible for a selected company/vendor in User Management."""
    user = current_user(request)
    if not _can_manage_users(user):
        return JSONResponse({"error": "not allowed"}, status_code=403)
    conn = get_connection()
    cur = conn.cursor()
    if kind.strip().lower() == "vendor":
        cur.execute("SELECT vendor_name, email, mobile FROM vendors WHERE vendor_id=:1",
                    (company_id.strip(),))
        rows = cur.fetchall()
        cur.execute(
            "SELECT driver_name, NULL, mobile FROM drivers WHERE vendor_id=:1 "
            "AND (status IS NULL OR UPPER(status) NOT IN ('INACTIVE','TERMINATED')) "
            "ORDER BY driver_name", (company_id.strip(),))
        rows.extend(cur.fetchall())
    elif kind.strip().lower() == "individual":
        cur.execute("SELECT guest_name, guest_email, guest_contact FROM individuals WHERE individual_id=:1 AND (status IS NULL OR UPPER(status)='ACTIVE')", (company_id.strip(),))
        rows = cur.fetchall()
    else:
        rows = []
        if company_id.strip():
            cur.execute(
                "SELECT guest_name, guest_email, guest_mobile FROM employees "
                "WHERE company_id=:1 AND (status IS NULL OR UPPER(status)='ACTIVE') ORDER BY guest_name", (company_id.strip(),))
            rows.extend(cur.fetchall())
            cur.execute(
                "SELECT c.contact_name, c.email, c.mobile FROM contacts c "
                "WHERE c.company_id=:1 AND (c.status IS NULL OR UPPER(c.status)='ACTIVE') ORDER BY c.contact_name", (company_id.strip(),))
            rows.extend(cur.fetchall())
        elif company_name.strip():
            cur.execute(
                "SELECT guest_name, guest_email, guest_mobile FROM employees "
                "WHERE UPPER(TRIM(company_name))=UPPER(TRIM(:1)) AND (status IS NULL OR UPPER(status)='ACTIVE') ORDER BY guest_name",
                (company_name.strip(),))
            rows = cur.fetchall()
    conn.close()
    out, seen = [], set()
    for name, email, mobile in rows:
        key = (str(name or "").strip().lower(), str(email or "").strip().lower())
        if not key[0] or key in seen:
            continue
        seen.add(key)
        out.append({"name": str(name).strip(), "email": str(email or "").strip(),
                    "mobile": str(mobile or "").strip()})
    return JSONResponse(out)


@router.get("/users")
def users_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_manage_users(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    if _is_super_admin(user):
        cur.execute(
            "SELECT user_id, name, email, mobile, company_name, role, status, user_no "
            "FROM users ORDER BY user_no"
        )
    else:
        cur.execute(
            "SELECT user_id, name, email, mobile, company_name, role, status, user_no "
            "FROM users WHERE UPPER(TRIM(company_name))=UPPER(TRIM(:1)) ORDER BY user_no",
            (user.get("company_name") or user.get("company") or "",),
        )
    headers = [d[0].lower() for d in cur.description]
    users = [dict(zip(headers, r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse(
        "users.html",
        {"request": request, "user": user, "users": users,
         "msg": request.query_params.get("msg", "")},
    )


@router.get("/users/new")
def user_new_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_manage_users(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    companies, vendors, individuals = _user_organizations()
    return templates.TemplateResponse(
        "user_form.html",
        {"request": request, "user": user, "rec": {}, "rec_id": None,
          "roles": USER_ROLES, "statuses": USER_STATUSES,
          "companies": companies, "vendors": vendors, "individuals": individuals,
          "msg": request.query_params.get("msg", "")},
    )


@router.post("/users/new")
async def user_create(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_manage_users(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    form = dict((await request.form()).multi_items())
    uid = str(form.get("user_id") or "").strip()
    name = str(form.get("name") or "").strip()
    if name == "__manual__":
        name = str(form.get("manual_name") or "").strip()
    email = str(form.get("email") or "").strip()
    password = str(form.get("password") or "")
    confirm = str(form.get("confirm_password") or "")
    company_name = str(form.get("company_name") or "").strip()
    mobile_pin = str(form.get("mobile_pin") or "").strip()
    if not uid or not name or not email:
        return RedirectResponse(url="/auth/users/new?msg=missing", status_code=303)
    if not _valid_new_user_id(uid):
        return RedirectResponse(url="/auth/users/new?msg=invalid-user-id", status_code=303)
    if password != confirm:
        return RedirectResponse(url="/auth/users/new?msg=password-mismatch", status_code=303)
    if len(password) < 6:
        return RedirectResponse(url="/auth/users/new?msg=password-short", status_code=303)

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM users WHERE UPPER(user_id)=UPPER(:1)", (uid,))
        if int(cur.fetchone()[0]) > 0:
            conn.close()
            return RedirectResponse(url="/auth/users/new?msg=exists", status_code=303)
        cur.execute("SELECT NVL(MAX(user_no),0)+1 FROM users")
        next_no = int(cur.fetchone()[0])
        new_hash = hash_password(password)
        pin_value = pin_hash(mobile_pin) if mobile_pin else None
        if company_name == "__new_individual__":
            individual_id = next_individual_id(cur)
            company_name = "Individual Guest"
            cur.execute(
                "INSERT INTO individuals (individual_id,company_name,guest_name,guest_contact,guest_email,status) "
                "VALUES (:1,:2,:3,:4,:5,'Active')",
                (individual_id, company_name, name, str(form.get("mobile") or "").strip() or None, email),
            )
        cur.execute(
            "INSERT INTO users (user_no, user_id, name, email, company_name, mobile, "
            "role, requested_role, status, password_hash, password_vault, mobile_pin_hash, created_dt) "
            "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13)",
            (next_no, uid, name, email,
             str(form.get("company_name") or "").strip() or None,
             str(form.get("mobile") or "").strip() or None,
             str(form.get("role") or "Operations").strip(),
             str(form.get("role") or "Operations").strip(),
             str(form.get("status") or "Active").strip(),
              new_hash, None, pin_value, datetime.now()),
        )
        audit(conn, user, "User Created", uid, f"role {form.get('role')}")
        conn.commit()
    except Exception:
        conn.close()
        return RedirectResponse(url="/auth/users/new?msg=error", status_code=303)
    conn.close()
    return RedirectResponse(url="/auth/users?msg=created", status_code=303)


@router.get("/users/{user_id}/edit")
def user_edit_page(request: Request, user_id: str):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_manage_users(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, name, email, mobile, company_name, role, status, emp_id "
        "FROM users WHERE UPPER(user_id)=UPPER(:1) AND ROWNUM=1", (user_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return RedirectResponse(url="/auth/users?msg=not-found", status_code=303)
    rec = {"user_id": row[0], "name": row[1], "email": row[2], "mobile": row[3],
           "company_name": row[4], "role": row[5], "status": row[6], "emp_id": row[7]}
    companies, vendors, individuals = _user_organizations()
    return templates.TemplateResponse(
        "user_form.html",
        {"request": request, "user": user, "rec": rec, "rec_id": row[0],
         "roles": USER_ROLES, "statuses": USER_STATUSES,
           "companies": companies, "vendors": vendors, "individuals": individuals,
          "msg": request.query_params.get("msg", "")},
    )


@router.post("/users/{user_id}/edit")
async def user_update(request: Request, user_id: str):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_manage_users(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    form = dict((await request.form()).multi_items())
    name = str(form.get("name") or "").strip()
    if name == "__manual__":
        name = str(form.get("manual_name") or "").strip()
    email = str(form.get("email") or "").strip()
    if not name or not email:
        return RedirectResponse(
            url=f"/auth/users/{user_id}/edit?msg=missing", status_code=303)
    new_password = str(form.get("new_password") or "")
    if new_password and len(new_password) < 6:
        return RedirectResponse(
            url=f"/auth/users/{user_id}/edit?msg=password-short", status_code=303)

    conn = get_connection()
    cur = conn.cursor()
    try:
        sets = ["name=:1", "email=:2", "mobile=:3", "company_name=:4",
                "role=:5", "status=:6"]
        params = [name, email,
                  str(form.get("mobile") or "").strip() or None,
                  str(form.get("company_name") or "").strip() or None,
                  str(form.get("role") or "Operations").strip(),
                  str(form.get("status") or "Active").strip()]
        if new_password:
            salt = random_salt_hex()
            new_hash = f"{salt}:{sha256_hex(salt + new_password)}"
            sets.append("password_hash=:7")
            params.append(new_hash)
        params.append(user_id)
        cur.execute(
            f"UPDATE users SET {', '.join(sets)} WHERE UPPER(user_id)=UPPER(:{len(params)})",
            params,
        )
        audit(conn, user, "User Updated", user_id,
              f"role {form.get('role')}; password reset" if new_password
              else f"role {form.get('role')}")
        conn.commit()
        invalidate_user_cache(user_id)
    except Exception:
        conn.close()
        return RedirectResponse(
            url=f"/auth/users/{user_id}/edit?msg=error", status_code=303)
    conn.close()
    return RedirectResponse(url="/auth/users?msg=updated", status_code=303)
