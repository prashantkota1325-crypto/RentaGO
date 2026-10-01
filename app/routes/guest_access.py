"""Secure Guest Trip Access without Driver QR pairing."""

from datetime import datetime

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse

from ..auth import current_user, module_level
from ..config import settings
from ..audit import audit
from ..db import get_connection
from ..guest_access import create_access, create_session, session_access, validate_token
from ..notify import queue
from ..scope import authorization_tenant, is_internal_user
from ..templating import templates

router = APIRouter()


def _can_create_access(user):
    return bool(user and is_internal_user(user) and module_level(user, "Bookings") == "F")


@router.post("/bookings/{booking_id}/guest-access")
def issue_guest_access(request: Request, booking_id: str):
    user = current_user(request)
    if not _can_create_access(user):
        return JSONResponse({"error": "not authorized"}, status_code=403)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT * FROM bookings WHERE booking_id=:1", (booking_id,))
    row = cur.fetchone()
    if not row:
        conn.close(); return JSONResponse({"error": "booking not found"}, status_code=404)
    booking = dict(zip([d[0].lower() for d in cur.description], row))
    tenant_id = authorization_tenant(user) or user.get("tenant_id") or "TEN-RENTA-GO"
    if booking.get("tenant_id") and str(booking["tenant_id"]) != str(tenant_id):
        conn.close(); return JSONResponse({"error": "tenant mismatch"}, status_code=403)
    if not booking.get("guest_email") and not booking.get("guest_contact"):
        conn.close(); return JSONResponse({"error": "guest contact unavailable"}, status_code=422)
    access_id, raw, expires = create_access(conn, booking, user.get("user_id"))
    host = request.headers.get("host") or request.url.netloc
    link = f"https://{host}/guest/access/{raw}"
    body = (f"Your RentaGO Trip Access\n\nTrip Reference: {access_id}\n\n"
            f"Use the secure link below to access your trip:\n{link}\n\n"
            "This link is private and expires.")
    recipients = [{"name": booking.get("guest_name_1"), "email": booking.get("guest_email"),
                   "phone": booking.get("guest_contact"), "role": "Guest"}]
    notification_user = dict(user, tenant_id=booking.get("tenant_id") or tenant_id)
    ids = queue(conn, notification_user, "guest-trip-access", booking_id, recipients,
                "Your RentaGO Trip Access", body, formatted_body=True,
                guest_trip_access_id=access_id)
    cur.execute("UPDATE guest_trip_access SET delivery_reference=:1 WHERE guest_trip_access_id=:2",
                (",".join(ids)[:200], access_id))
    audit(conn, user, "Guest Trip Access Created", booking_id,
          f"guest_trip_access_id={access_id}; channels=outbox")
    conn.commit(); conn.close()
    return JSONResponse({"guest_trip_access_id": access_id, "expires_at": expires,
                         "notification_ids": ids, "delivery": "QUEUED"})


@router.get("/guest/access/{token}")
def guest_access(token: str, request: Request):
    conn = get_connection(); cur = conn.cursor()
    access = validate_token(cur, token)
    if not access:
        conn.close(); return templates.TemplateResponse("mobile/guest_access.html",
            {"request": request, "error": "This Guest access link is invalid, expired, or revoked."}, status_code=404)
    raw_session, expires = create_session(conn, access)
    conn.commit(); conn.close()
    response = RedirectResponse("/guest/trip", status_code=303)
    response.set_cookie("rentago_guest_trip", raw_session, httponly=True,
                        secure=settings.SESSION_COOKIE_SECURE,
                        samesite="lax", max_age=max(1, int((expires - datetime.now()).total_seconds())))
    return response


@router.get("/guest/trip")
def guest_trip(request: Request):
    raw = request.cookies.get("rentago_guest_trip")
    conn = get_connection(); cur = conn.cursor()
    access = session_access(cur, raw)
    if not access:
        conn.close(); return RedirectResponse("/mobile/guest-login?msg=guest-access-required", status_code=303)
    cur.execute("SELECT * FROM bookings WHERE booking_id=:1 AND tenant_id=:2",
                (access.get("booking_id"), access.get("tenant_id")))
    row = cur.fetchone()
    if not row:
        conn.close(); return JSONResponse({"error": "trip not found"}, status_code=404)
    booking = dict(zip([d[0].lower() for d in cur.description], row))
    conn.close()
    return templates.TemplateResponse("mobile/guest_access.html",
        {"request": request, "booking": booking, "access": access, "error": None})


@router.post("/guest/trip/signature")
def guest_signature(request: Request):
    conn = get_connection(); cur = conn.cursor()
    access = session_access(cur, request.cookies.get("rentago_guest_trip"))
    if not access:
        conn.close(); return JSONResponse({"error": "guest session required"}, status_code=401)
    booking_id = access.get("booking_id")
    cur.execute("SELECT tenant_id FROM bookings WHERE booking_id=:1", (booking_id,))
    row = cur.fetchone()
    if not row or str(row[0]) != str(access.get("tenant_id")):
        conn.close(); return JSONResponse({"error": "trip not authorized"}, status_code=403)
    cur.execute("SELECT trip_id FROM trips WHERE booking_id=:1", (booking_id,))
    if not cur.fetchone():
        conn.close(); return JSONResponse({"error": "trip not ready for signature"}, status_code=409)
    cur.execute(
        "UPDATE trips SET customer_signature='Captured', customer_signature_source='GUEST_SECURE_ACCESS', "
        "customer_signature_at=SYSTIMESTAMP, customer_signature_by=:1 WHERE booking_id=:2",
        ("guest-access:" + access["access_id"], booking_id),
    )
    audit(conn, {"user_id": "guest-access:" + access["access_id"], "role": "Guest"},
          "Guest Signature Captured", booking_id, "source=GUEST_SECURE_ACCESS")
    conn.commit(); conn.close()
    return RedirectResponse("/guest/trip?msg=signature-saved", status_code=303)


@router.post("/guest/trip/feedback")
def guest_feedback(request: Request, rating: str = Form(""), feedback: str = Form(""),
                   safety_status: str = Form(""), safety_issues: list[str] = Form([])):
    from .bookings import submit_feedback
    conn = get_connection(); cur = conn.cursor()
    access = session_access(cur, request.cookies.get("rentago_guest_trip"))
    if not access:
        conn.close(); return JSONResponse({"error": "guest session required"}, status_code=401)
    conn.close()
    return submit_feedback(request, access.get("booking_id"), rating, feedback,
                           [], [], safety_status, safety_issues)


@router.post("/bookings/{booking_id}/guest-access/revoke")
def revoke_guest_access(request: Request, booking_id: str,
                        guest_trip_access_id: str = Form("")):
    user = current_user(request)
    if not _can_create_access(user):
        return JSONResponse({"error": "not authorized"}, status_code=403)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE guest_trip_access SET status='REVOKED', revoked_at=SYSTIMESTAMP "
                "WHERE guest_trip_access_id=:1 AND booking_id=:2 AND status='ACTIVE'",
                (guest_trip_access_id.strip(), booking_id))
    if not cur.rowcount:
        conn.close(); return JSONResponse({"error": "access not found"}, status_code=404)
    audit(conn, user, "Guest Trip Access Revoked", booking_id,
          f"guest_trip_access_id={guest_trip_access_id.strip()}")
    conn.commit(); conn.close()
    return JSONResponse({"ok": True})
