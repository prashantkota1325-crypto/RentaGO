"""Authenticated mobile Guest/Driver portal with only trip actions."""

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from datetime import datetime
import uuid
from urllib.parse import quote
import json

from ..auth import current_user, create_session_token
from ..db import get_connection
from ..scope import visible_booking_ids, can_view
from ..templating import templates
from ..device import is_mobile_request
from ..audit import audit
from .. import notify
from ..mobile_pin import attempt_allowed, attempt_key, pin_matches, record_attempt, find_mobile_user
from ..config import settings

router = APIRouter(prefix="/mobile")


def _load_current(request, who):
    user = current_user(request)
    role = (user or {}).get("role", "").strip().lower()
    if not user or role != who or not is_mobile_request(request):
        return None, None
    conn = get_connection()
    cur = conn.cursor()
    visible = visible_booking_ids(user, cur)
    mobile_booking_id = user.get("mobile_booking_id")
    if mobile_booking_id:
        cur.execute("SELECT * FROM bookings WHERE booking_id=:1", (mobile_booking_id,))
    elif who == "driver":
        cur.execute("SELECT * FROM bookings WHERE pickup_date >= TRUNC(SYSDATE) AND pickup_date < TRUNC(SYSDATE)+7 AND status_reason IN ('Booking Confirmed - Driver & Vehicle Allocated','Guest Trip Started - Awaiting Driver Confirmation','Trip In Progress','Guest Trip Ended - Awaiting Driver Confirmation') ORDER BY pickup_date, booking_id")
    elif who == "guest":
        cur.execute("SELECT * FROM bookings WHERE pickup_date >= TRUNC(SYSDATE) AND pickup_date < TRUNC(SYSDATE)+7 AND status_reason IN ('Booking Confirmed - Driver & Vehicle Allocated','Guest Trip Started - Awaiting Driver Confirmation','Trip In Progress','Guest Trip Ended - Awaiting Driver Confirmation') AND (UPPER(guest_name_1)=UPPER(:1) OR REPLACE(guest_contact,' ','')=REPLACE(:2,' ','') OR UPPER(guest_email)=UPPER(:3)) ORDER BY pickup_date, booking_id", (user.get("name") or "", user.get("mobile") or "", user.get("email") or ""))
    else:
        cur.execute("SELECT * FROM bookings ORDER BY pickup_date DESC, booking_id DESC")
    rows = []
    for row in cur.fetchall():
        cols = [d[0].lower() for d in cur.description]
        booking = dict(zip(cols, row))
        if can_view(visible, str(booking.get("booking_id") or "")):
            rows.append(booking)
    conn.close()
    if not rows:
        return user, None
    return user, rows[0]


@router.get("/{who}-login")
def mobile_login_page(request: Request, who: str, msg: str = ""):
    if who not in ("guest", "driver"):
        return RedirectResponse("/auth/login", status_code=303)
    return templates.TemplateResponse("mobile/login.html", {"request": request, "who": who, "message": msg})


@router.post("/{who}-login")
def mobile_login(request: Request, who: str, identity: str = Form(...), booking_id: str = Form(...), pin: str = Form(...)):
    if who not in ("guest", "driver") or not is_mobile_request(request):
        return RedirectResponse(f"/mobile/{who}-login?msg=mobile-only", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    key = attempt_key(identity, who, booking_id)
    if not attempt_allowed(cur, key):
        conn.close(); return RedirectResponse(f"/mobile/{who}-login?msg=locked", status_code=303)
    user_row = find_mobile_user(cur, identity, who)
    cur.execute("SELECT * FROM bookings WHERE booking_id=:1", (booking_id.strip(),)); booking_row = cur.fetchone()
    user_ok = bool(user_row and pin_matches(pin, user_row[5]))
    booking = None
    if booking_row:
        cols = [d[0].lower() for d in cur.description]; booking = dict(zip(cols, booking_row))
    assigned = False
    if booking and user_row:
        if who == "guest":
            assigned = (str(user_row[1] or "").strip().lower() == str(booking.get("guest_name_1") or "").strip().lower() or
                        str(user_row[3] or "").replace(" ", "") == str(booking.get("guest_contact") or "").replace(" ", ""))
        else:
            assigned = (str(user_row[1] or "").strip().lower() == str(booking.get("driver_name") or "").strip().lower() or
                        str(user_row[3] or "").replace(" ", "") == str(booking.get("driver_contact") or "").replace(" ", ""))
    if not user_ok or not assigned or not booking or booking.get("status_reason") in ("Trip Completed", "Booking Cancelled"):
        record_attempt(cur, key, False); conn.commit(); conn.close()
        return RedirectResponse(f"/mobile/{who}-login?msg=invalid", status_code=303)
    record_attempt(cur, key, True)
    session_id = str(uuid.uuid4())
    cur.execute("DELETE FROM user_sessions WHERE UPPER(user_id)=UPPER(:1)", (user_row[0],))
    cur.execute("INSERT INTO user_sessions (session_id,user_id,login_dt,last_activity,ip_address,mobile_booking_id) VALUES (:1,:2,SYSDATE,SYSDATE,:3,:4)",
                (session_id, user_row[0], request.client.host if request.client else None, booking_id.strip()))
    audit(conn, {"user_id": user_row[0], "name": user_row[1]}, "Mobile PIN Login", booking_id, who)
    conn.commit(); conn.close()
    response = RedirectResponse(f"/mobile/{who}", status_code=303)
    response.set_cookie("rentago_session", create_session_token(user_row[0], session_id), httponly=True,
                        secure=settings.SESSION_COOKIE_SECURE, samesite="lax", domain=settings.SESSION_COOKIE_DOMAIN)
    return response


@router.get("/{who}")
def mobile_home(request: Request, who: str):
    user, booking = _load_current(request, who)
    if not user:
        return RedirectResponse(url=f"/mobile/{who}-login?msg=login-required", status_code=303)
    driver_stops = []
    if who == "driver" and booking:
        try:
            payload = booking.get("planned_route_json") or "{}"
            if hasattr(payload, "read"): payload = payload.read()
            driver_stops = json.loads(payload).get("stops", [])
        except (TypeError, ValueError):
            driver_stops = []
    return templates.TemplateResponse(
        "mobile/participant.html", {"request": request, "user": user,
        "booking": booking, "who": who,
        "driver_stops": driver_stops, "rentago_contact": notify.OPS_PHONE,
        "tracking_link": request.query_params.get("tracking_link", ""),
        "message": request.query_params.get("msg", "")},
    )


@router.post("/{who}/{booking_id}/signature")
def save_signature(request: Request, who: str, booking_id: str,
                   signature_type: str = Form("")):
    user, booking = _load_current(request, who)
    if not user or not booking or str(booking.get("booking_id")) != booking_id:
        return RedirectResponse(url=f"/mobile/{who}?msg=not-allowed", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    column = "customer_signature" if signature_type == "guest" else "driver_signature"
    cur.execute(f"UPDATE trips SET {column}=:1 WHERE booking_id=:2",
                ("Captured", booking_id))
    audit(conn, user, f"{who.title()} Signature Captured", booking_id, "")
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/mobile/{who}?msg=signature-saved", status_code=303)
