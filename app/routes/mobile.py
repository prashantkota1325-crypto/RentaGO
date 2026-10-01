"""Authenticated mobile Guest/Driver portal with only trip actions."""

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from datetime import datetime, timedelta
import uuid
from urllib.parse import quote
import json

from ..auth import current_user, create_session_token
from ..db import get_connection
from ..scope import visible_booking_ids, can_view
from ..templating import templates
from ..device import is_mobile_request
from ..audit import audit, _parse_oracle_dt
from .. import notify
from ..mobile_pin import attempt_allowed, attempt_key, pin_matches, record_attempt, find_mobile_user
from ..config import settings

router = APIRouter(prefix="/mobile")


def _is_active_late_booking(booking):
    if not booking:
        return False
    return (str(booking.get("entry_mode") or "").strip().upper() == "OFFLINE_SYSTEM_DOWNTIME_ACTIVE"
            or str(booking.get("late_entry_type") or "").strip().upper() == "CURRENT_TRIP_ACTIVE")


def _is_post_trip_booking(booking):
    """Treat completed records consistently even when legacy values contain padding."""
    if not booking:
        return False
    entry_mode = str(booking.get("entry_mode") or "").strip().upper()
    late_type = str(booking.get("late_entry_type") or "").strip().upper()
    if entry_mode == "OFFLINE_SYSTEM_DOWNTIME_ACTIVE" or late_type == "CURRENT_TRIP_ACTIVE":
        return False
    reason = str(booking.get("status_reason") or "").strip().lower()
    status = str(booking.get("booking_status") or "").strip().lower()
    return (reason == "trip completed" or status.startswith("3-")
            or bool(booking.get("_post_trip_by_time")))


def _mark_post_trip_by_time(cur, booking):
    """Handle legacy records entered after the recorded actual trip end."""
    if not booking:
        return
    cur.execute(
        "SELECT actual_end_dt, drop_end_time FROM trips "
        "WHERE booking_id=:1 ORDER BY trip_id DESC FETCH FIRST 1 ROWS ONLY",
        (booking.get("booking_id"),),
    )
    row = cur.fetchone()
    actual_end = _parse_oracle_dt(row[0]) if row else None
    if actual_end is None and row:
        actual_end = _parse_oracle_dt(row[1])
    if actual_end is None and row and row[1] and booking.get("drop_date"):
        # Legacy trips may store only HH:MM/HH:MM:SS in DROP_END_TIME.
        raw_time = str(row[1]).strip()
        for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%H.%M"):
            try:
                parsed_time = datetime.strptime(raw_time, fmt).time()
                drop_date = _parse_oracle_dt(booking.get("drop_date"))
                if drop_date:
                    actual_end = datetime.combine(drop_date.date(), parsed_time)
                break
            except ValueError:
                continue
    entered_at = _parse_oracle_dt(
        booking.get("booking_punched_at") or booking.get("booking_date")
    )
    booking["_post_trip_by_time"] = bool(entered_at and actual_end and entered_at > actual_end)


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
        cur.execute("SELECT * FROM bookings WHERE status_reason IN ('Awaiting Driver & Vehicle Allocation','Booking Confirmed - Driver & Vehicle Allocated','Guest Trip Started - Awaiting Driver Confirmation','Trip In Progress','Guest Trip Ended - Awaiting Driver Confirmation') AND (UPPER(guest_name_1)=UPPER(:1) OR REPLACE(guest_contact,' ','')=REPLACE(:2,' ','') OR UPPER(guest_email)=UPPER(:3)) ORDER BY pickup_date DESC, booking_id DESC", (user.get("name") or "", user.get("mobile") or "", user.get("email") or ""))
    else:
        cur.execute("SELECT * FROM bookings ORDER BY pickup_date DESC, booking_id DESC")
    rows = []
    for row in cur.fetchall():
        cols = [d[0].lower() for d in cur.description]
        booking = dict(zip(cols, row))
        if can_view(visible, str(booking.get("booking_id") or "")):
            rows.append(booking)
    if not rows:
        conn.close()
        return user, None
    _mark_post_trip_by_time(cur, rows[0])
    planned_route = rows[0].get("planned_route_json")
    if hasattr(planned_route, "read"):
        rows[0]["planned_route_json"] = planned_route.read()
    conn.close()
    return user, rows[0]


@router.get("/{who}-login")
def mobile_login_page(request: Request, who: str, msg: str = ""):
    if who == "vendor":
        return vendor_mobile_login_page(request, msg)
    if who not in ("guest", "driver"):
        return RedirectResponse("/auth/login", status_code=303)
    return templates.TemplateResponse("mobile/login.html", {"request": request, "who": who, "message": msg})


@router.get("/vendor-login")
def vendor_mobile_login_page(request: Request, msg: str = ""):
    return templates.TemplateResponse("mobile/login.html", {"request": request, "who": "vendor", "message": msg})


@router.post("/vendor-login")
def vendor_mobile_login(request: Request, identity: str = Form(...), pin: str = Form(...)):
    if not is_mobile_request(request):
        return RedirectResponse("/mobile/vendor-login?msg=mobile-only", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    user_row = find_mobile_user(cur, identity, "vendor")
    tenant = None
    if user_row:
        cur.execute("SELECT tenant_id FROM tenant_memberships WHERE UPPER(user_id)=UPPER(:1) AND status='ACTIVE'", (user_row[0],))
        memberships = [r[0] for r in cur.fetchall()]
        if len(memberships) == 1:
            tenant = memberships[0]
    user_ok = bool(user_row and pin_matches(pin, user_row[6]))
    organization = ""
    if user_row:
        cur.execute("SELECT organization_id FROM users WHERE UPPER(user_id)=UPPER(:1)", (user_row[0],))
        organization_row = cur.fetchone()
        organization = str(organization_row[0] or "") if organization_row else ""
    vendor_id = organization[5:] if organization.upper().startswith("VEND-") else ""
    if not user_ok or not tenant or not vendor_id:
        conn.close()
        return RedirectResponse("/mobile/vendor-login?msg=invalid", status_code=303)
    session_id = str(uuid.uuid4())
    cur.execute("DELETE FROM user_sessions WHERE UPPER(user_id)=UPPER(:1)", (user_row[0],))
    cur.execute("INSERT INTO user_sessions (session_id,user_id,login_dt,last_activity,ip_address,mobile_booking_id) VALUES (:1,:2,SYSDATE,SYSDATE,:3,NULL)",
                (session_id, user_row[0], request.client.host if request.client else None))
    audit(conn, {"user_id": user_row[0], "name": user_row[1]}, "Vendor Mobile Login", vendor_id, f"tenant={tenant}")
    conn.commit(); conn.close()
    response = RedirectResponse("/mobile/vendor", status_code=303)
    response.set_cookie("rentago_session", create_session_token(user_row[0], session_id), httponly=True,
                        secure=settings.SESSION_COOKIE_SECURE, samesite="lax", domain=settings.SESSION_COOKIE_DOMAIN)
    return response


@router.get("/vendor")
def vendor_mobile_home(request: Request):
    user = current_user(request)
    if not user or (user.get("role") or "").strip().lower() not in {"vendor", "vendor admin", "vendor operations", "vendor viewer"} or not is_mobile_request(request):
        return RedirectResponse("/mobile/vendor-login?msg=login-required", status_code=303)
    tenant = str(user.get("tenant_id") or "").strip()
    organization = str(user.get("organization_id") or "")
    vendor_id = organization[5:] if organization.upper().startswith("VEND-") else ""
    if not tenant or not vendor_id:
        return RedirectResponse("/mobile/vendor-login?msg=vendor-scope-required", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT booking_id,guest_name_1,pickup_date,pickup_time,pickup_address,drop_address,driver_name,vehicle_no,booking_status,status_reason FROM bookings WHERE tenant_id=:1 AND vendor_id=:2 AND pickup_date >= TRUNC(SYSDATE) ORDER BY pickup_date,booking_id", (tenant, vendor_id))
    bookings = [dict(zip(("booking_id","guest","pickup_date","pickup_time","pickup","drop","driver","vehicle","booking_status","status_reason"), r)) for r in cur.fetchall()]
    cur.execute("SELECT t.trip_id,t.booking_id,t.guest_name,t.driver_name,t.vehicle_no,t.trip_status,t.pickup_address,t.drop_address FROM trips t JOIN bookings b ON b.booking_id=t.booking_id WHERE b.tenant_id=:1 AND b.vendor_id=:2 AND t.pickup_date >= TRUNC(SYSDATE) ORDER BY t.pickup_date,t.trip_id", (tenant, vendor_id))
    trips = [dict(zip(("trip_id","booking_id","guest","driver","vehicle","status","pickup","drop"), r)) for r in cur.fetchall()]
    cur.execute("SELECT driver_id,driver_name,mobile,status FROM drivers WHERE tenant_id=:1 AND vendor_id=:2 ORDER BY driver_name", (tenant, vendor_id))
    drivers = [dict(zip(("driver_id","name","mobile","status"), r)) for r in cur.fetchall()]
    cur.execute("SELECT vehicle_id,reg_number,make,model,status FROM vehicles WHERE tenant_id=:1 AND vendor_id=:2 ORDER BY reg_number", (tenant, vendor_id))
    vehicles = [dict(zip(("vehicle_id","registration","make","model","status"), r)) for r in cur.fetchall()]
    cur.execute("SELECT booking_id,driver_name,vehicle_no,status_reason,track_token FROM bookings WHERE tenant_id=:1 AND vendor_id=:2 AND status_reason IN ('Trip In Progress','Guest Trip Ended - Awaiting Driver Confirmation') ORDER BY pickup_date DESC", (tenant, vendor_id))
    tracking = [{"booking_id": r[0], "driver": r[1], "vehicle": r[2], "status": r[3], "tracking_url": f"/track/{r[0]}/guest/{r[4]}" if r[4] else ""} for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("mobile/vendor.html", {"request": request, "user": user, "bookings": bookings, "trips": trips, "drivers": drivers, "vehicles": vehicles, "tracking": tracking, "vendor_id": vendor_id})


@router.post("/{who}-login")
def mobile_login(request: Request, who: str, identity: str = Form(...), booking_id: str = Form(""), pin: str = Form(...)):
    if who == "vendor":
        return vendor_mobile_login(request, identity, pin)
    if who not in ("guest", "driver") or not is_mobile_request(request):
        return RedirectResponse(f"/mobile/{who}-login?msg=mobile-only", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    key = attempt_key(identity, who, booking_id)
    if not attempt_allowed(cur, key):
        conn.close(); return RedirectResponse(f"/mobile/{who}-login?msg=locked", status_code=303)
    user_row = find_mobile_user(cur, identity, who)
    booking_id = booking_id.strip()
    booking_row = None
    if booking_id:
        cur.execute("SELECT * FROM bookings WHERE booking_id=:1", (booking_id,)); booking_row = cur.fetchone()
    booking_cols = [d[0].lower() for d in cur.description] if booking_row else []
    tenant_id = None
    if user_row:
        cur.execute("SELECT tenant_id FROM tenant_memberships WHERE UPPER(user_id)=UPPER(:1) AND status='ACTIVE'", (user_row[0],))
        memberships = [r[0] for r in cur.fetchall()]
        if len(memberships) == 1:
            tenant_id = memberships[0]
    user_ok = bool(user_row and pin_matches(pin, user_row[6]))
    booking = None
    if booking_row:
        booking = dict(zip(booking_cols, booking_row))
        _mark_post_trip_by_time(cur, booking)
    assigned = False
    if booking and user_row and tenant_id and str(booking.get("tenant_id") or "") == str(tenant_id):
        if who == "guest":
            linked = str(user_row[5] or "").strip().lower()
            assigned = bool((linked and linked == str(booking.get("emp_guest_id") or "").strip().lower()) or
                        (not linked and (
                         str(user_row[1] or "").strip().lower() == str(booking.get("guest_name_1") or "").strip().lower() or
                         str(user_row[3] or "").replace(" ", "") == str(booking.get("guest_contact") or "").replace(" ", ""))))
        else:
            assigned = (str(user_row[1] or "").strip().lower() == str(booking.get("driver_name") or "").strip().lower() or
                        str(user_row[3] or "").replace(" ", "") == str(booking.get("driver_contact") or "").replace(" ", ""))
    elif who == "driver" and user_row and tenant_id and not booking_id:
        cur.execute("SELECT driver_id FROM drivers WHERE tenant_id=:1 AND driver_id=:2 "
                    "AND (status IS NULL OR UPPER(status)='ACTIVE') FETCH FIRST 1 ROWS ONLY",
                    (tenant_id, user_row[5] or ""))
        driver_row = cur.fetchone()
        if not driver_row:
            cur.execute("SELECT driver_id FROM drivers WHERE tenant_id=:1 AND "
                        "(UPPER(TRIM(driver_name))=UPPER(TRIM(:2)) OR mobile=:3) "
                        "AND (status IS NULL OR UPPER(status)='ACTIVE') FETCH FIRST 1 ROWS ONLY",
                        (tenant_id, user_row[1] or "", user_row[3] or ""))
            driver_row = cur.fetchone()
        assigned = bool(driver_row)
    completed_guest_access = False
    post_trip_access = _is_post_trip_booking(booking)
    if booking and who == "guest" and str(booking.get("status_reason") or "").strip() == "Trip Completed":
        cur.execute(
            "SELECT guest_rating, actual_end_dt, drop_end_time FROM trips WHERE booking_id=:1 "
            "ORDER BY trip_id DESC FETCH FIRST 1 ROWS ONLY",
            (booking_id.strip(),),
        )
        feedback_row = cur.fetchone()
        rating = None
        if feedback_row and feedback_row[0] not in (None, ""):
            try:
                rating = int(feedback_row[0])
            except (TypeError, ValueError):
                rating = None
        from ..audit import _parse_oracle_dt
        end_dt = _parse_oracle_dt(feedback_row[1]) if feedback_row else None
        if end_dt is None and feedback_row:
            end_dt = _parse_oracle_dt(feedback_row[2])
        completed_guest_access = bool(
            (rating is None or rating <= 3)
            and end_dt
            and datetime.now() <= end_dt + timedelta(hours=24)
        )
    post_trip_access = post_trip_access or completed_guest_access
    if (not user_ok or not assigned or (not booking and not (who == "driver" and not booking_id))
            or (str(booking.get("status_reason") or "").strip() in ("Trip Completed", "Booking Cancelled")
                and not post_trip_access)):
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
    tracking_link = request.query_params.get("tracking_link", "")
    if booking and not tracking_link and booking.get("track_token"):
        tracking_link = f"{str(request.base_url).rstrip('/')}/track/{booking.get('booking_id')}/{who}/{booking.get('track_token')}"
    return templates.TemplateResponse(
        "mobile/participant.html", {"request": request, "user": user,
        "booking": booking, "who": who,
        "driver_stops": driver_stops, "rentago_contact": notify.OPS_PHONE,
            "post_trip_mode": _is_post_trip_booking(booking),
        "active_late_mode": _is_active_late_booking(booking),
            "tracking_link": tracking_link,
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
    if signature_type not in ("guest", "driver") or (who == "guest" and signature_type != "guest"):
        conn.close()
        return RedirectResponse(url=f"/mobile/{who}?msg=not-allowed", status_code=303)
    column = "customer_signature" if signature_type == "guest" else "driver_signature"
    prefix = "customer" if signature_type == "guest" else "driver"
    source = "Guest Mobile" if who == "guest" else "Driver Mobile"
    cur.execute(
        f"UPDATE trips SET {column}=:1, {prefix}_signature_source=:2, "
        f"{prefix}_signature_at=SYSTIMESTAMP, {prefix}_signature_by=:3 WHERE booking_id=:4",
        ("Captured", source, user.get("user_id"), booking_id),
    )
    audit(conn, user, f"{who.title()} Signature Captured", booking_id,
          f"type={signature_type}; source={source}")
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/mobile/{who}?msg=signature-saved", status_code=303)


@router.post("/{who}/{booking_id}/feedback")
def mobile_feedback(request: Request, who: str, booking_id: str,
                    rating: str = Form(""), feedback: str = Form(""),
                    safety_status: str = Form(""), safety_issues: list[str] = Form([])):
    """Keep post-trip feedback on the participant mobile surface."""
    user, booking = _load_current(request, who)
    if not user or who != "guest" or not booking or str(booking.get("booking_id")) != booking_id:
        return RedirectResponse(url=f"/mobile/{who}?msg=not-allowed", status_code=303)
    from .bookings import submit_feedback
    return submit_feedback(request, booking_id, rating, feedback, [], [], safety_status, safety_issues)


@router.post("/driver/{booking_id}/participant-feedback")
def driver_participant_feedback(request: Request, booking_id: str,
                                feedback_kind: str = Form(""), feedback: str = Form(""),
                                safety_status: str = Form(""), safety_issues: str = Form("")):
    """Record Driver Mobile's post-trip guest observation or safety report."""
    user, booking = _load_current(request, "driver")
    if (not user or not booking or str(booking.get("booking_id")) != booking_id
            or not _is_post_trip_booking(booking)
            or feedback_kind not in ("guest", "safety")):
        return RedirectResponse(url="/mobile/driver?msg=not-allowed", status_code=303)
    if feedback_kind == "safety" and safety_status not in {"Yes", "Some concern", "Safety issue"}:
        return RedirectResponse(url="/mobile/driver?msg=feedback-invalid", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    if feedback_kind == "guest":
        cur.execute(
            "UPDATE trips SET driver_feedback=:1, driver_feedback_submitted_on=SYSTIMESTAMP, "
            "driver_feedback_by=:2 WHERE booking_id=:3",
            ((feedback or "").strip()[:2000], user.get("user_id"), booking_id),
        )
        action = "Driver Guest Feedback Submitted"
    else:
        cur.execute(
            "UPDATE trips SET driver_safety_status=:1, driver_safety_issues=:2, "
            "driver_feedback_submitted_on=SYSTIMESTAMP, driver_feedback_by=:3 WHERE booking_id=:4",
            (safety_status, (safety_issues or "").strip()[:2000], user.get("user_id"), booking_id),
        )
        action = "Driver Safety Feedback Submitted"
    audit(conn, user, action, booking_id, f"source=Driver Mobile")
    conn.commit()
    conn.close()
    return RedirectResponse(url="/mobile/driver?msg=feedback-saved", status_code=303)
