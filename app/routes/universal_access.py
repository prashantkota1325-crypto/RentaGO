"""Universal role-aware access and Android context exchange."""

import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse

from ..auth import create_session_token, current_user, module_level
from ..config import settings
from ..db import get_connection
from ..scope import is_internal_user
from ..templating import templates
from ..universal_access import create_access, load_access, consume, challenge
from ..trusted_devices import validate_device

router = APIRouter()
LAB_APK = Path(r"C:\RentaGOWork\rentago_mobile_android\build\app\outputs\flutter-apk\app-release.apk")


@router.get("/access/download/apk")
def download_lab_apk():
    if not LAB_APK.is_file():
        return JSONResponse({"error": "LAB APK is not available"}, status_code=404)
    return FileResponse(LAB_APK, media_type="application/vnd.android.package-archive",
                        filename="RentaGO-LAB.apk")


def _bound_user_is_active(cur, bound_user_id, role):
    if not bound_user_id:
        return False
    cur.execute("SELECT role,status FROM users WHERE UPPER(user_id)=UPPER(:1)", (bound_user_id,))
    row = cur.fetchone()
    return bool(row and str(row[1] or "").lower() == "active"
                and str(row[0] or "").strip().lower() == str(role or "").strip().lower())


def _manual_session_response(request, access):
    conn = get_connection(); cur = conn.cursor()
    if not consume(cur, request.state.universal_raw_token):
        conn.close(); return None
    session_id = str(uuid.uuid4())
    cur.execute("DELETE FROM user_sessions WHERE UPPER(user_id)=UPPER(:1)", (access["user_id"],))
    cur.execute(
        "INSERT INTO user_sessions (session_id,user_id,login_dt,last_activity,ip_address,mobile_booking_id) "
        "VALUES (:1,:2,SYSDATE,SYSDATE,:3,:4)",
        (session_id, access["user_id"], request.client.host if request.client else None, access["booking_id"]),
    )
    conn.commit(); conn.close()
    destination = "/mobile/guest" if access["role"] == "guest" else "/mobile/driver"
    response = RedirectResponse(destination, status_code=303)
    response.set_cookie("rentago_session", create_session_token(access["user_id"], session_id),
                        httponly=True, secure=settings.SESSION_COOKIE_SECURE, samesite="lax",
                        domain=settings.SESSION_COOKIE_DOMAIN)
    return response


@router.get("/access")
def manual_access_page(request: Request, error: str = ""):
    return templates.TemplateResponse("access_login.html", {"request": request, "error": error})


@router.post("/access")
async def manual_access_login(request: Request):
    form = await request.form()
    raw = str(form.get("secure_token") or "").strip()
    conn = get_connection(); cur = conn.cursor()
    access = load_access(cur, raw)
    if (not access or access["role"] not in {"guest", "driver"
            } or not _bound_user_is_active(cur, access["user_id"], access["role"])):
        conn.close()
        return templates.TemplateResponse("access_login.html", {"request": request,
            "error": "Invalid User ID or Secure Token."}, status_code=403)
    if access["role"] == "driver":
        conn.close()
        return templates.TemplateResponse("access_login.html", {"request": request,
            "driver_handoff": "rentago://access/" + quote(raw, safe=""),
            "message": "Continue in the RentaGO app to complete Driver trusted-device validation."})
    request.state.universal_raw_token = raw
    conn.close()
    response = _manual_session_response(request, access)
    if response is None:
        return templates.TemplateResponse("access_login.html", {"request": request,
            "error": "Access could not be verified."}, status_code=403)
    return response


def _public_base(request):
    configured = str(getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    return configured or str(request.base_url).rstrip("/")


@router.get("/access/{token}")
@router.get("/web-access/{token}")
def universal_access_page(request: Request, token: str):
    conn = get_connection(); cur = conn.cursor()
    access = load_access(cur, token)
    if not access:
        conn.close()
        return templates.TemplateResponse("universal_access.html", {
            "request": request, "error": "This RentaGO access link is invalid, expired, revoked, or already used.",
        }, status_code=404)
    # App Links normally prevent this request when the Android app is
    # installed. Browser fallback establishes the existing web/mobile session.
    if ("RentaGOAndroid" not in (request.headers.get("user-agent") or "")
            and not str(access["destination"]).endswith("_gps")):
        if consume(cur, token):
            session_id = access.get("session_id") or str(uuid.uuid4())
            if not access.get("session_id"):
                cur.execute("DELETE FROM user_sessions WHERE UPPER(user_id)=UPPER(:1)", (access["user_id"],))
                cur.execute(
                    "INSERT INTO user_sessions (session_id,user_id,login_dt,last_activity,ip_address,mobile_booking_id) "
                    "VALUES (:1,:2,SYSDATE,SYSDATE,:3,:4)",
                    (session_id, access["user_id"], request.client.host if request.client else None, access["booking_id"]),
                )
            conn.commit(); conn.close()
            destination = {"guest": "/mobile/guest", "driver": "/mobile/driver",
                           "vendor": "/dashboards/vendor", "admin": "/home",
                           "renta_go": "/home", "super admin": "/home"}.get(access["role"], "/home")
            response = RedirectResponse(destination, status_code=303)
            response.set_cookie("rentago_session", create_session_token(access["user_id"], session_id),
                                httponly=True, secure=settings.SESSION_COOKIE_SECURE, samesite="lax",
                                domain=settings.SESSION_COOKIE_DOMAIN)
            return response
        conn.close()
        return templates.TemplateResponse("universal_access.html", {
            "request": request, "error": "This RentaGO access link has already been used.",
        }, status_code=410)
    conn.close()
    app_uri = "rentago://access/" + quote(token, safe="")
    return templates.TemplateResponse("universal_access.html", {
        "request": request, "access": access,
        "app_uri": app_uri,
        "download_url": f"/access/download/{quote(token, safe='')}",
    })


@router.get("/access/download/{token}")
def universal_access_download(request: Request, token: str):
    conn = get_connection(); cur = conn.cursor()
    access = load_access(cur, token)
    conn.close()
    if not access:
        return templates.TemplateResponse("universal_access.html", {
            "request": request, "error": "This RentaGO access link is invalid, expired, revoked, or already used.",
        }, status_code=404)
    return templates.TemplateResponse("universal_access.html", {
        "request": request, "access": access,
        "app_uri": "rentago://access/" + quote(token, safe=""),
        "download_url": "",
        "download_page": True,
    })


@router.post("/access/exchange")
async def universal_access_exchange(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    raw = str(body.get("token") or "").strip()
    if not raw:
        return JSONResponse({"ok": False, "error": "access-token-required"}, status_code=400)
    conn = get_connection(); cur = conn.cursor()
    access = load_access(cur, raw)
    if not access:
        conn.close(); return JSONResponse({"ok": False, "error": "access-token-invalid"}, status_code=403)
    if access["role"] not in {"guest", "driver", "admin", "vendor", "renta_go", "super admin"}:
        conn.close(); return JSONResponse({"ok": False, "error": "role-not-supported"}, status_code=403)
    if access["role"] not in {"guest", "driver"}:
        conn.close()
        return JSONResponse({"ok": True, "role": access["role"],
                             "web_url": f"{_public_base(request)}/web-access/{raw}"})
    if access["role"] == "driver":
        device_id = str(body.get("device_id") or "")
        payload = str(body.get("payload") or "")
        signature = str(body.get("signature") or "")
        if not device_id or not payload or not signature:
            raw_challenge, digest = challenge()
            cur.execute(
                "UPDATE universal_access_tokens SET exchange_challenge_hash=:1, "
                "exchange_challenge_expires_at=SYSTIMESTAMP + INTERVAL '5' MINUTE "
                "WHERE access_id=:2 AND status='ACTIVE'",
                (digest, access["access_id"]),
            )
            conn.commit(); conn.close()
            return JSONResponse({"ok": False, "error": "trusted-device-required",
                                 "access_id": access["access_id"], "challenge": raw_challenge}, status_code=403)
        expected_payload = f"{access['access_id']}|"
        if not payload.startswith(expected_payload):
            conn.close(); return JSONResponse({"ok": False, "error": "challenge-invalid"}, status_code=403)
        cur.execute("SELECT exchange_challenge_hash,exchange_challenge_expires_at FROM universal_access_tokens WHERE access_id=:1", (access["access_id"],))
        challenge_row = cur.fetchone()
        import hashlib
        if not challenge_row or not challenge_row[0] or hashlib.sha256(payload.split("|", 1)[1].encode()).hexdigest() != challenge_row[0] or (challenge_row[1] and challenge_row[1] <= __import__("datetime").datetime.now()):
            conn.close(); return JSONResponse({"ok": False, "error": "challenge-invalid"}, status_code=403)
        device_state = validate_device(cur, device_id, access["driver_id"], access["tenant_id"], None, device_id, payload, signature)
        if device_state != "OFFLINE_AUTHORIZED":
            conn.close(); return JSONResponse({"ok": False, "error": device_state}, status_code=403)
    if not consume(cur, raw):
        conn.rollback(); conn.close()
        return JSONResponse({"ok": False, "error": "access-token-replayed"}, status_code=403)
    session_id = str(uuid.uuid4())
    cur.execute("DELETE FROM user_sessions WHERE UPPER(user_id)=UPPER(:1)", (access["user_id"],))
    cur.execute(
        "INSERT INTO user_sessions (session_id,user_id,login_dt,last_activity,ip_address,mobile_booking_id) "
        "VALUES (:1,:2,SYSDATE,SYSDATE,:3,:4)",
        (session_id, access["user_id"], request.client.host if request.client else None, access["booking_id"]),
    )
    driver_web_url = None
    if access["role"] in {"guest", "driver"}:
        _, driver_web_token, _ = create_access(
            conn, role=access["role"], user_id=access["user_id"], driver_id=access["driver_id"],
            tenant_id=access["tenant_id"], booking_id=access["booking_id"],
            created_by="universal-portal-handoff", destination=f"{access['role']}_web", session_id=session_id,
        )
        driver_web_url = f"{_public_base(request)}/web-access/{driver_web_token}"
    conn.commit(); conn.close()
    response = JSONResponse({"ok": True, "role": access["role"], "user_id": access["user_id"],
                             "booking_id": access["booking_id"], "destination": access["destination"],
                             "web_url": driver_web_url})
    response.set_cookie("rentago_session", create_session_token(access["user_id"], session_id),
                        httponly=True, secure=settings.SESSION_COOKIE_SECURE, samesite="lax",
                        domain=settings.SESSION_COOKIE_DOMAIN)
    return response


@router.post("/bookings/{booking_id}/universal-access")
async def issue_universal_access(request: Request, booking_id: str):
    user = current_user(request)
    if not user or not is_internal_user(user) or module_level(user, "Bookings") != "F":
        return JSONResponse({"error": "not authorized"}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    role = str(body.get("role") or "guest").strip().lower()
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT * FROM bookings WHERE booking_id=:1", (booking_id,))
    row = cur.fetchone()
    if not row:
        conn.close(); return JSONResponse({"error": "booking not found"}, status_code=404)
    booking = dict(zip([d[0].lower() for d in cur.description], row))
    if role == "guest":
        cur.execute("SELECT user_id FROM users WHERE UPPER(emp_id)=UPPER(:1) AND LOWER(role)='guest' FETCH FIRST 1 ROWS ONLY", (booking.get("emp_guest_id"),))
        guest_row = cur.fetchone()
        user_id = str(guest_row[0] if guest_row else (booking.get("emp_guest_id") or "")).strip()
        destination = "guest"
    elif role == "driver":
        user_id = str(body.get("user_id") or "").strip()
        cur.execute("SELECT driver_id FROM drivers WHERE tenant_id=:1 AND (UPPER(TRIM(driver_name))=UPPER(TRIM(:2)) OR mobile=:3) FETCH FIRST 1 ROWS ONLY", (booking.get("tenant_id"), booking.get("driver_name"), booking.get("driver_contact")))
        driver_row = cur.fetchone()
        driver_id = str(driver_row[0]) if driver_row else user_id
        destination = "driver"
    else:
        user_id = str(body.get("user_id") or "").strip()
        destination = "dashboard"
    if not user_id:
        conn.close(); return JSONResponse({"error": "role identity required"}, status_code=422)
    access_id, raw, expires = create_access(
        conn, role=role, user_id=user_id, tenant_id=booking.get("tenant_id"),
        booking_id=booking_id, driver_id=(driver_id if role == "driver" else None),
        created_by=user.get("user_id"), destination=destination,
    )
    conn.commit(); conn.close()
    return JSONResponse({"access_id": access_id, "token": raw, "expires_at": expires,
                         "url": f"{_public_base(request)}/access/{raw}"})


@router.post("/access/issue")
async def issue_role_access(request: Request):
    """Issue a non-booking universal dashboard link for an authorized operator."""
    user = current_user(request)
    if not user or not is_internal_user(user):
        return JSONResponse({"error": "not authorized"}, status_code=403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    role = str(body.get("role") or "").strip().lower()
    allowed = {"admin", "vendor", "renta_go", "super admin"}
    if role not in allowed:
        return JSONResponse({"error": "dashboard role required"}, status_code=422)
    subject = str(body.get("user_id") or "").strip()
    if not subject:
        return JSONResponse({"error": "user_id required"}, status_code=422)
    conn = get_connection()
    access_id, raw, expires = create_access(
        conn, role=role, user_id=subject, tenant_id=user.get("tenant_id"),
        created_by=user.get("user_id"), destination="dashboard",
    )
    conn.commit(); conn.close()
    return JSONResponse({"access_id": access_id, "token": raw, "expires_at": expires,
                         "url": f"{_public_base(request)}/access/{raw}"})
