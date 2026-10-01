"""One-tap automatic GPS tracking (driver T-2h / guest T-15min windows).

/track/{booking_id}/{who}/{token}      -> mobile page, no login needed
/track/{booking_id}/{who}/{token}/ping -> JSON {lat, lon} auto-reported by
                                          the page's Geolocation watcher

The token is the booking's track_token, so drivers and guests - who have no
RentaGO account - can open the link from WhatsApp and simply allow location
access. Every ping stores the position; once both driver and guest positions
are known the sync (100 m) check runs automatically and RED FLAG alerts fire
on mismatch.
"""

from datetime import datetime
import hashlib
import uuid

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from urllib.parse import quote

from ..templating import templates
from ..db import get_connection
from ..gps import distance_meters, SYNC_THRESHOLD_METERS, reverse_geocode, route_estimate
from ..config import settings
from .. import notify
from ..auth import current_user, read_session_token
from ..scope import visible_booking_ids, can_view
from ..device import is_mobile_request
from ..sla_engine import emit_start
from ..trip_continuity import append_event
from ..realtime import subscribe, unsubscribe, publish
from ..gps_validation import validate_point

router = APIRouter(prefix="/track")

ACTIVE_REASONS = (
    "Booking Confirmed - Driver & Vehicle Allocated",
    "Guest Trip Started - Awaiting Driver Confirmation",
    "Trip In Progress",
    "Guest Trip Ended - Awaiting Driver Confirmation",
)

BOT = {"user_id": "tracking-bot", "name": "Auto Tracking", "role": "Operations"}


def _next_gps_id(cur):
    """Next gps_log id 'GPS-<nnnnnn>'."""
    cur.execute("SELECT log_id FROM gps_log")
    maxn = 0
    for (lid,) in cur.fetchall():
        s = str(lid or "").strip().upper()
        if s.startswith("GPS-"):
            try:
                maxn = max(maxn, int(s[4:]))
            except Exception:
                pass
    return "GPS-%06d" % (maxn + 1)


def _load(cur, booking_id, who, token):
    if who not in ("driver", "guest"):
        return None, "unknown-party"
    cur.execute(
        "SELECT booking_id, track_token, guest_name_1, guest_email, "
        "guest_contact, admin_name, admin_email, admin_contact, driver_name, "
        "pickup_address, pickup_date, pickup_time, pickup_lat, pickup_lon, "
        "pickup_arrival_trigger, status_reason, "
        "driver_contact, driver_gps, guest_gps, "
        "location_sync FROM bookings WHERE booking_id=:1",
        (booking_id,),
    )
    row = cur.fetchone()
    if not row:
        return None, "not-found"
    b = {
        "booking_id": row[0], "track_token": str(row[1] or "").strip(),
        "guest_name_1": row[2], "guest_email": row[3], "guest_contact": row[4],
        "admin_name": row[5], "admin_email": row[6], "admin_contact": row[7],
        "driver_name": row[8], "pickup_address": row[9],
        "pickup_date": row[10], "pickup_time": row[11],
        "pickup_lat": row[12], "pickup_lon": row[13],
        "pickup_arrival_trigger": row[14], "status_reason": row[15],
        "driver_contact": row[16], "driver_gps": row[17], "guest_gps": row[18],
        "location_sync": row[19],
    }
    if not b["track_token"] or b["track_token"] != str(token or "").strip():
        return None, "bad-token"
    if b["status_reason"] not in ACTIVE_REASONS:
        return None, "not-active"
    return b, None


def _window_open(b, who):
    from ..routes.bookings import _tracking_window_open
    return _tracking_window_open(b, who)


def _participant_authorized(request, user, b, who, cur):
    """Require the intended mobile participant, not merely a bearer URL."""
    if who == "guest":
        from ..guest_access import session_access
        access = session_access(cur, request.cookies.get("rentago_guest_trip"))
        if access and str(access.get("booking_id")) == str(b.get("booking_id")):
            cur.execute("SELECT tenant_id FROM bookings WHERE booking_id=:1", (b.get("booking_id"),))
            booking_tenant = cur.fetchone()
            if booking_tenant and str(access.get("tenant_id")) == str(booking_tenant[0]):
                return True
    if user and who == "guest" and (user.get("role") or "").strip().lower() in {
        "vendor", "vendor admin", "vendor operations", "vendor viewer",
    }:
        organization = str(user.get("organization_id") or "")
        vendor_id = organization[5:] if organization.upper().startswith("VEND-") else ""
        cur.execute("SELECT tenant_id,vendor_id FROM bookings WHERE booking_id=:1", (b.get("booking_id"),))
        vendor_booking = cur.fetchone()
        if (vendor_id and vendor_booking and str(user.get("tenant_id") or "") == str(vendor_booking[0])
                and vendor_id.lower() == str(vendor_booking[1] or "").lower()):
            return True
    if not user or not is_mobile_request(request):
        return False
    role = (user.get("role") or "").strip().lower()
    parsed = read_session_token(request)
    sid = parsed[1] if parsed else ""
    if not sid:
        return False
    cur.execute("SELECT mobile_booking_id FROM user_sessions WHERE session_id=:1 AND UPPER(user_id)=UPPER(:2)", (sid, user.get("user_id")))
    session_row = cur.fetchone()
    if not session_row:
        return False
    if not can_view(visible_booking_ids(user, cur), str(b.get("booking_id"))):
        return False
    if str(session_row[0] or "") != str(b.get("booking_id") or ""):
        # Guest identity sessions may have no booking-bound mobile session;
        # visible_booking_ids still enforces tenant and identity scope.
        if not (who == "guest" and not session_row[0] and role == "guest"):
            return False
    if who == "guest":
        return role == "guest"
    if role != "driver":
        return False
    name = (user.get("name") or "").strip().lower()
    mobile = (user.get("mobile") or "").strip().lower()
    return ((name and name == (b.get("driver_name") or "").strip().lower())
            or (mobile and mobile == (b.get("driver_contact") or "").strip().lower()))


def _fmt_dt(v):
    from ..audit import _parse_oracle_dt
    dt = _parse_oracle_dt(v)
    return dt.strftime("%d-%m-%Y %I:%M %p") if dt else "-"


def _token_hash(token):
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _tracking_context(request, cur, tracking_session_id, token):
    """Resolve tracking data from the authenticated mobile session only."""
    user = current_user(request)
    cur.execute(
        "SELECT tracking_session_id, tenant_id, booking_id, trip_continuity_id, user_id, who, tracking_token_hash, status "
        "FROM tracking_sessions WHERE tracking_session_id=:1", (tracking_session_id,))
    row = cur.fetchone()
    if not row or row[6] != _token_hash(token) or row[7] not in ("ACTIVE", "PAUSED"):
        return None, "invalid-tracking-session"
    cur.execute("SELECT tenant_id FROM bookings WHERE booking_id=:1", (row[2],))
    booking = cur.fetchone()
    if not booking or str(booking[0] or "") != str(row[1] or ""):
        return None, "tracking-object-mismatch"
    if not user or not is_mobile_request(request) or str(user.get("user_id")) != str(row[4]):
        return None, "participant-login-required"
    parsed = read_session_token(request)
    cur.execute("SELECT mobile_booking_id FROM user_sessions WHERE session_id=:1 AND UPPER(user_id)=UPPER(:2)",
                (parsed[1] if parsed else "", user.get("user_id")))
    session_row = cur.fetchone()
    if not session_row or str(session_row[0] or "") != str(row[2]):
        return None, "tracking-object-mismatch"
    return {"session_id": row[0], "tenant_id": row[1], "booking_id": row[2],
            "trip_continuity_id": row[3], "user_id": row[4], "who": row[5],
            "status": row[7]}, None


async def _control_context(request, tracking_session_id):
    """Authenticate a Driver Live Trip control against its active session."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    token = str(data.get("tracking_token") or "")
    conn = get_connection()
    cur = conn.cursor()
    context, err = _tracking_context(request, cur, tracking_session_id, token)
    return conn, cur, context, err, token


@router.post("/{booking_id}/{who}/{token}/session/start")
async def tracking_session_start(request: Request, booking_id: str, who: str, token: str):
    conn = get_connection()
    cur = conn.cursor()
    b, err = _load(cur, booking_id, who, token)
    user = current_user(request)
    if err or not user or not _participant_authorized(request, user, b or {}, who, cur):
        conn.close()
        return JSONResponse({"ok": False, "error": err or "participant-login-required"}, status_code=403)
    cur.execute("SELECT tenant_id, trip_continuity_id FROM bookings WHERE booking_id=:1", (booking_id,))
    row = cur.fetchone()
    if not row or not row[0]:
        conn.close()
        return JSONResponse({"ok": False, "error": "tenant-not-found"}, status_code=403)
    session_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO tracking_sessions (tracking_session_id,tenant_id,booking_id,trip_continuity_id,user_id,who,tracking_token_hash,status,started_at) "
        "VALUES (:1,:2,:3,:4,:5,:6,:7,'ACTIVE',SYSTIMESTAMP)",
        (session_id, row[0], booking_id, row[1], user.get("user_id"), who, _token_hash(token)))
    if row[1]:
        cur.execute("UPDATE trip_continuity SET tracking_session_id=:1, updated_at=SYSTIMESTAMP WHERE trip_continuity_id=:2",
                    (session_id, row[1]))
        append_event(conn, row[1], "TRACKING_SESSION_STARTED",
                     {"tracking_session_id": session_id},
                     "DRIVER" if who == "driver" else "GUEST", user.get("user_id"))
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True, "tracking_session_id": session_id, "booking_id": booking_id, "who": who})


async def _tracking_token_body(request):
    try:
        data = await request.json()
        return data, str(data.get("tracking_token") or "")
    except Exception:
        return {}, ""


@router.post("/session/{tracking_session_id}/batch")
async def tracking_session_batch(request: Request, tracking_session_id: str):
    data, token = await _tracking_token_body(request)
    events = data.get("events") if isinstance(data.get("events"), list) else []
    if not token or not events or len(events) > 100:
        return JSONResponse({"ok": False, "error": "bad-batch"}, status_code=400)
    conn = get_connection()
    cur = conn.cursor()
    context, err = _tracking_context(request, cur, tracking_session_id, token)
    if err:
        conn.close()
        return JSONResponse({"ok": False, "error": err}, status_code=403)
    if context.get("status") == "PAUSED":
        conn.close()
        return JSONResponse({"ok": False, "error": "tracking-paused"}, status_code=409)
    accepted, duplicates, rejected = [], [], []
    max_sequence = None
    for event in events:
        try:
            point = validate_point(event)
        except ValueError as exc:
            rejected.append({"gps_event_id": str(event.get("gps_event_id") or ""), "reason": str(exc)})
            continue
        event_id, sequence = point["gps_event_id"], point["sequence_number"]
        lat, lon = point["lat"], point["lon"]
        cur.execute("SELECT log_id FROM gps_log WHERE tracking_session_id=:1 AND gps_event_id=:2",
                    (tracking_session_id, event_id))
        if cur.fetchone():
            duplicates.append(event_id)
            continue
        cur.execute("SELECT sequence_number,captured_at,latitude,longitude,tracking_session_id FROM gps_latest_positions "
                    "WHERE booking_id=:1 AND who=:2", (context["booking_id"], context["who"]))
        latest = cur.fetchone()
        same_session_latest = latest and str(latest[4] or "") == str(tracking_session_id)
        if same_session_latest and (sequence <= int(latest[0]) or point["captured_at"] <= latest[1]):
            rejected.append({"gps_event_id": event_id, "reason": "old-event"})
            continue
        if same_session_latest:
            elapsed = (point["captured_at"] - latest[1]).total_seconds()
            if elapsed > 0:
                velocity = distance_meters(float(latest[2]), float(latest[3]), lat, lon) / elapsed
                if velocity > settings.GPS_MAX_SPEED_MPS:
                    rejected.append({"gps_event_id": event_id, "reason": "suspicious-movement"})
                    continue
        if max_sequence is not None and sequence < max_sequence:
            rejected.append({"gps_event_id": event_id, "reason": "out-of-order-sequence"})
            continue
        max_sequence = max(sequence, max_sequence or sequence)
        received_at = datetime.now()
        cur.execute(
            "INSERT INTO gps_log (log_id,booking_id,trip_continuity_id,who,lat,lon,tracking_session_id,gps_event_id,sequence_number,captured_dt,captured_at,received_at,validation_status,accuracy_m,speed_kmh) "
            "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:10,:11,'VALID',:12,:13)",
             (_next_gps_id(cur), context["booking_id"], context.get("trip_continuity_id"),
             context["who"], point["lat"], point["lon"], tracking_session_id, event_id, sequence,
             point["captured_at"], point["captured_at"], received_at, point["accuracy_m"],
             float(point["speed_mps"] or 0) * 3.6 if point["speed_mps"] is not None else None))
        if context.get("trip_continuity_id"):
            append_event(conn, context["trip_continuity_id"], "GPS_POINT",
                          {"gps_event_id": event_id, "sequence": sequence,
                           "lat": point["lat"], "lon": point["lon"]},
                         "DRIVER" if context["who"] == "driver" else "GUEST",
                         context.get("user_id"), idempotency_key=event_id)
        publish(context["booking_id"], {
            "event_type": "GPS_POINT", "event_version": 1,
            "booking_id": context["booking_id"],
            "trip_continuity_id": context.get("trip_continuity_id"),
            "tracking_session_id": tracking_session_id,
            "gps_event_id": event_id, "sequence": sequence,
             "latitude": point["lat"], "longitude": point["lon"],
         })
        cur.execute(
            "MERGE INTO gps_latest_positions p USING (SELECT :booking_id booking_id,:who who FROM dual) s "
            "ON (p.booking_id=s.booking_id AND p.who=s.who) "
            "WHEN MATCHED THEN UPDATE SET tracking_session_id=:session_id,trip_continuity_id=:continuity_id,latitude=:latitude,longitude=:longitude,accuracy_m=:accuracy,speed_mps=:speed,heading_deg=:heading,captured_at=:captured,received_at=:received,sequence_number=:sequence,status='LIVE',updated_at=SYSTIMESTAMP "
            "WHEN NOT MATCHED THEN INSERT (booking_id,tracking_session_id,trip_continuity_id,who,latitude,longitude,accuracy_m,speed_mps,heading_deg,captured_at,received_at,sequence_number,status) VALUES (:booking_id,:session_id,:continuity_id,:who,:latitude,:longitude,:accuracy,:speed,:heading,:captured,:received,:sequence,'LIVE')",
            {"booking_id": context["booking_id"], "who": context["who"], "session_id": tracking_session_id,
             "continuity_id": context.get("trip_continuity_id"), "latitude": point["lat"], "longitude": point["lon"],
             "accuracy": point["accuracy_m"], "speed": point["speed_mps"], "heading": point["heading_deg"],
             "captured": point["captured_at"], "received": received_at, "sequence": sequence})
        col = "driver_gps" if context["who"] == "driver" else "guest_gps"
        ts_col = col + "_ts"
        cur.execute(f"UPDATE bookings SET {col}=:1,{ts_col}=SYSTIMESTAMP WHERE booking_id=:2",
                    (f"{lat}, {lon}", context["booking_id"]))
        accepted.append(event_id)
    if accepted:
        cur.execute("UPDATE tracking_sessions SET last_sequence=GREATEST(last_sequence,:1), last_seen_at=SYSTIMESTAMP WHERE tracking_session_id=:2",
                    (max(int(e["sequence_number"]) for e in events if str(e.get("gps_event_id")) in accepted), tracking_session_id))
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True, "accepted": accepted, "duplicates": duplicates,
                         "rejected": rejected, "next_expected_sequence": (max_sequence or 0) + 1})


@router.websocket("/ws/{booking_id}/{who}/{token}")
async def tracking_websocket(websocket: WebSocket, booking_id: str, who: str, token: str):
    """LAB realtime display stream; REST/GPS_LOG remains authoritative."""
    conn = get_connection(); cur = conn.cursor()
    b, err = _load(cur, booking_id, who, token)
    user = current_user(websocket)
    if err or not _participant_authorized(websocket, user, b or {}, who, cur):
        conn.close()
        await websocket.close(code=4403)
        return
    cur.execute("SELECT lat,lon,captured_dt,gps_event_id,sequence_number,speed_kmh,accuracy_m FROM gps_log WHERE booking_id=:1 ORDER BY captured_dt,log_id", (booking_id,))
    history = [{"event_type": "GPS_POINT", "event_version": 1, "booking_id": booking_id,
                "latitude": r[0], "longitude": r[1], "captured_at": str(r[2] or ""),
                "gps_event_id": r[3], "sequence": r[4], "speed_kmh": r[5],
                "accuracy_m": r[6]} for r in cur.fetchall()]
    conn.close()
    await websocket.accept()
    await websocket.send_json({"event_type": "GPS_HISTORY", "event_version": 1,
                               "booking_id": booking_id, "points": history})
    queue = subscribe(booking_id)
    try:
        while True:
            await websocket.send_json(await queue.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        unsubscribe(booking_id, queue)


@router.post("/session/{tracking_session_id}/end")
async def tracking_session_end(request: Request, tracking_session_id: str):
    _, token = await _tracking_token_body(request)
    conn = get_connection()
    cur = conn.cursor()
    context, err = _tracking_context(request, cur, tracking_session_id, token)
    if err:
        conn.close()
        return JSONResponse({"ok": False, "error": err}, status_code=403)
    cur.execute("UPDATE tracking_sessions SET status='ENDED', ended_at=SYSTIMESTAMP WHERE tracking_session_id=:1",
                (tracking_session_id,))
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True, "tracking_session_id": context["session_id"], "status": "ENDED"})


@router.get("/{booking_id}/{who}/{token}")
def track_page(request: Request, booking_id: str, who: str, token: str):
    conn = get_connection()
    cur = conn.cursor()
    b, err = _load(cur, booking_id, who, token)
    if not err and not _participant_authorized(request, current_user(request), b, who, cur):
        err = "participant-login-required"
    conn.close()
    if err:
        return templates.TemplateResponse(
            "track.html",
            {"request": request, "error": err, "who": who,
             "booking_id": booking_id},
            status_code=404 if err in ("not-found", "bad-token") else 200,
        )
    name = b["driver_name"] if who == "driver" else b["guest_name_1"]
    return templates.TemplateResponse(
        "track.html",
        {"request": request, "error": None, "who": who,
         "booking_id": booking_id, "name": name or "",
         "pickup": f"{b['pickup_address'] or '-'} at "
                   f"{b['pickup_time'] or '-'} on {b['pickup_date'] or '-'}",
         "window_open": _window_open(b, who)},
    )


@router.get("/{booking_id}/{who}/{token}/snapshot")
def tracking_snapshot(request: Request, booking_id: str, who: str, token: str):
    """Authoritative persisted GPS snapshot/history for Live Map clients."""
    conn = get_connection(); cur = conn.cursor()
    b, err = _load(cur, booking_id, who, token)
    user = current_user(request)
    if err or not _participant_authorized(request, user, b or {}, who, cur):
        conn.close(); return JSONResponse({"ok": False, "error": err or "unauthorized"}, status_code=403)
    cur.execute("SELECT trip_continuity_id,drop_address,drop_lat,drop_lon,pickup_lat,pickup_lon,"
                "driver_name,vehicle_no,status_reason FROM bookings WHERE booking_id=:1", (booking_id,))
    booking = cur.fetchone()
    cur.execute("SELECT status FROM tracking_sessions WHERE booking_id=:1 AND who='driver' "
                "ORDER BY started_at DESC FETCH FIRST 1 ROWS ONLY", (booking_id,))
    tracking_state = cur.fetchone()
    cur.execute("SELECT pickup_start_km,drop_end_km FROM trips WHERE booking_id=:1 "
                "ORDER BY trip_id DESC FETCH FIRST 1 ROWS ONLY", (booking_id,))
    odometer = cur.fetchone()
    cur.execute("SELECT lat,lon,captured_dt,gps_event_id,sequence_number,speed_kmh,accuracy_m FROM gps_log WHERE booking_id=:1 ORDER BY captured_dt,log_id", (booking_id,))
    rows = cur.fetchall()
    conn.close()
    points = [{"latitude": r[0], "longitude": r[1], "captured_at": str(r[2] or ""),
               "gps_event_id": r[3], "sequence": r[4], "speed_kmh": r[5],
               "accuracy_m": r[6]} for r in rows]
    latest = points[-1] if points else None
    distance_to_drop_km = None
    time_to_drop_hm = None
    if latest and booking and booking[2] is not None and booking[3] is not None:
        current_lat = float(latest["latitude"])
        current_lon = float(latest["longitude"])
        distance_to_drop_km = round(distance_meters(current_lat, current_lon, float(booking[2]), float(booking[3])) / 1000, 2)
        route = route_estimate(current_lat, current_lon, float(booking[2]), float(booking[3]), settings.GOOGLE_MAPS_API_KEY)
        if route[1] is not None:
            minutes = max(0, round(float(route[1]) * 60))
            time_to_drop_hm = f"{minutes // 60:02d}:{minutes % 60:02d}"
    freshness = "NO GPS"
    if latest and latest["captured_at"]:
        from ..audit import _parse_oracle_dt
        dt = _parse_oracle_dt(latest["captured_at"])
        if dt:
            freshness = "LIVE" if (datetime.now() - dt).total_seconds() <= 120 else "STALE"
    return JSONResponse({"ok": True, "booking_id": booking_id,
                         "trip_continuity_id": booking[0] if booking else None,
                          "pickup": {"latitude": booking[4], "longitude": booking[5],
                                      "address": b.get("pickup_address")} if booking else {},
                          "drop": {"latitude": booking[2], "longitude": booking[3],
                                   "address": booking[1]} if booking else {},
                          "driver_name": booking[6] if booking else None,
                          "vehicle_no": booking[7] if booking else None,
                          "status": booking[8] if booking else None,
                          "start_odometer": odometer[0] if odometer else None,
                          "end_odometer": odometer[1] if odometer else None,
                          "tracking_state": tracking_state[0] if tracking_state else "ACTIVE",
                           "freshness": freshness, "last": latest, "points": points,
                           "distance_to_drop_km": distance_to_drop_km,
                           "time_to_drop_hm": time_to_drop_hm})


@router.post("/session/{tracking_session_id}/pause")
async def tracking_session_pause(request: Request, tracking_session_id: str):
    conn, cur, context, err, _ = await _control_context(request, tracking_session_id)
    if err or not context or context["who"] != "driver":
        conn.close()
        return JSONResponse({"ok": False, "error": err or "driver-only"}, status_code=403)
    cur.execute("SELECT status FROM tracking_sessions WHERE tracking_session_id=:1", (tracking_session_id,))
    row = cur.fetchone()
    if not row or row[0] == "ENDED":
        conn.close()
        return JSONResponse({"ok": False, "error": "already-ended"}, status_code=409)
    if row[0] == "PAUSED":
        conn.close()
        return JSONResponse({"ok": True, "status": "PAUSED"})
    cur.execute("UPDATE tracking_sessions SET status='PAUSED' WHERE tracking_session_id=:1", (tracking_session_id,))
    if context.get("trip_continuity_id"):
        from ..trip_continuity import update_status
        update_status(conn, context["trip_continuity_id"], "TRIP_PAUSED", "TRIP_PAUSED", context["user_id"])
    conn.commit(); conn.close()
    return JSONResponse({"ok": True, "status": "PAUSED"})


@router.post("/session/{tracking_session_id}/resume")
async def tracking_session_resume(request: Request, tracking_session_id: str):
    conn, cur, context, err, _ = await _control_context(request, tracking_session_id)
    if err or not context or context["who"] != "driver":
        conn.close()
        return JSONResponse({"ok": False, "error": err or "driver-only"}, status_code=403)
    cur.execute("SELECT status FROM tracking_sessions WHERE tracking_session_id=:1", (tracking_session_id,))
    row = cur.fetchone()
    if not row or row[0] == "ENDED":
        conn.close()
        return JSONResponse({"ok": False, "error": "already-ended"}, status_code=409)
    if row[0] == "ACTIVE":
        conn.close()
        return JSONResponse({"ok": True, "status": "ACTIVE"})
    cur.execute("UPDATE tracking_sessions SET status='ACTIVE' WHERE tracking_session_id=:1", (tracking_session_id,))
    if context.get("trip_continuity_id"):
        from ..trip_continuity import update_status
        update_status(conn, context["trip_continuity_id"], "TRIP_IN_PROGRESS", "TRIP_RESUMED", context["user_id"])
    conn.commit(); conn.close()
    return JSONResponse({"ok": True, "status": "ACTIVE"})


@router.post("/session/{tracking_session_id}/call-guest")
async def tracking_call_guest(request: Request, tracking_session_id: str):
    conn, cur, context, err, _ = await _control_context(request, tracking_session_id)
    if err or not context or context["who"] != "driver":
        conn.close()
        return JSONResponse({"ok": False, "error": err or "driver-only"}, status_code=403)
    cur.execute("SELECT guest_contact,guest_name_1,status_reason FROM bookings WHERE booking_id=:1",
                (context["booking_id"],))
    row = cur.fetchone()
    if not row or not row[0]:
        conn.close()
        return JSONResponse({"ok": False, "error": "guest-contact-unavailable"}, status_code=404)
    audit_user = current_user(request) or {"user_id": context["user_id"], "role": "Driver"}
    from ..audit import audit
    audit(conn, audit_user, "Driver Called Guest", context["booking_id"], "contact returned to authenticated Driver")
    conn.commit(); conn.close()
    return JSONResponse({"ok": True, "phone": str(row[0]), "guest_name": row[1] or "Guest"})


@router.post("/{booking_id}/{who}/{token}/ping")
async def track_ping(request: Request, booking_id: str, who: str, token: str):
    """Auto-reported GPS position from the tracking page."""
    try:
        data = await request.json()
        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("position out of range")
        speed_kmh = float(data["speed_kmh"]) if data.get("speed_kmh") is not None else None
        accuracy_m = float(data["accuracy_m"]) if data.get("accuracy_m") is not None else None
        if speed_kmh is not None and speed_kmh < 0:
            raise ValueError("speed out of range")
        if accuracy_m is not None and accuracy_m < 0:
            raise ValueError("accuracy out of range")
    except Exception:
        return JSONResponse({"ok": False, "error": "bad-position"})
    conn = get_connection()
    cur = conn.cursor()
    b, err = _load(cur, booking_id, who, token)
    if err:
        conn.close()
        return JSONResponse({"ok": False, "error": err})
    if not _participant_authorized(request, current_user(request), b, who, cur):
        conn.close()
        return JSONResponse({"ok": False, "error": "participant-login-required"}, status_code=403)
    cur.execute("SELECT status FROM tracking_sessions WHERE booking_id=:1 AND who=:2 "
                "ORDER BY started_at DESC FETCH FIRST 1 ROWS ONLY", (booking_id, who))
    tracking_row = cur.fetchone()
    if tracking_row and tracking_row[0] == "PAUSED":
        conn.close()
        return JSONResponse({"ok": False, "error": "tracking-paused"}, status_code=409)
    if tracking_row and tracking_row[0] == "ENDED":
        conn.close()
        return JSONResponse({"ok": False, "error": "tracking-ended"}, status_code=409)
    if not _window_open(b, who):
        conn.close()
        mins = 120 if who == "driver" else 15
        return JSONResponse({"ok": False,
                             "error": f"window-closed ({mins} min before pickup)"})
    now = datetime.now()
    col = "driver_gps" if who == "driver" else "guest_gps"
    ts_col = col + "_ts"
    live_col = "driver_live_location" if who == "driver" else "guest_live_location"
    maps_link = f"https://www.google.com/maps?q={lat},{lon}"
    location_address = reverse_geocode(lat, lon, settings.GOOGLE_MAPS_API_KEY)
    from_pickup_km = None
    to_drop_km = None
    time_to_drop_hm = None
    try:
        if b.get("pickup_lat") is not None and b.get("pickup_lon") is not None:
            from_pickup_km = round(distance_meters(float(b["pickup_lat"]), float(b["pickup_lon"]), lat, lon) / 1000, 2)
        if b.get("drop_lat") is not None and b.get("drop_lon") is not None:
            to_drop_km = round(distance_meters(lat, lon, float(b["drop_lat"]), float(b["drop_lon"])) / 1000, 2)
            route = route_estimate(lat, lon, float(b["drop_lat"]), float(b["drop_lon"]), settings.GOOGLE_MAPS_API_KEY)
            if route[1] is not None:
                total_minutes = max(0, round(float(route[1]) * 60))
                time_to_drop_hm = f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
    except Exception:
        pass
    cur.execute(
        f"UPDATE bookings SET {col}=:1, {ts_col}=:2, {live_col}=:3 WHERE booking_id=:4",
        (f"{lat}, {lon}", now, maps_link, booking_id),
    )
    # auto sync check once both positions are known
    status, dist = None, None
    d = str(b.get("driver_gps") or "").strip()
    g = str(b.get("guest_gps") or "").strip()
    if who == "driver":
        d = f"{lat}, {lon}"
    else:
        g = f"{lat}, {lon}"
    if who == "driver" and b.get("pickup_lat") is not None and b.get("pickup_lon") is not None:
        try:
            pickup_distance = distance_meters(float(lat), float(lon),
                                              float(b["pickup_lat"]), float(b["pickup_lon"]))
            if pickup_distance <= 100 and str(b.get("pickup_arrival_trigger") or "") != "TRIGGERED":
                cur.execute("UPDATE bookings SET pickup_arrival_trigger='TRIGGERED' WHERE booking_id=:1", (booking_id,))
                notify.notify_pickup_arrival(conn, BOT, dict(b, driver_gps=d), pickup_distance)
        except (TypeError, ValueError):
            pass
    if who == "driver":
        cur.execute("SELECT planned_kms, route_deviation_status FROM bookings WHERE booking_id=:1", (booking_id,))
        plan_row = cur.fetchone()
        planned_km = float(plan_row[0]) if plan_row and plan_row[0] else 0.0
        deviation_status = str(plan_row[1] or "") if plan_row else ""
        if planned_km > 0:
            cur.execute("SELECT lat, lon FROM gps_log WHERE booking_id=:1 AND who='driver' ORDER BY captured_dt, log_id", (booking_id,))
            path = [(float(r[0]), float(r[1])) for r in cur.fetchall()]
            path.append((lat, lon))
            actual_km = sum(distance_meters(path[i - 1][0], path[i - 1][1], path[i][0], path[i][1]) for i in range(1, len(path))) / 1000
            percent = max(0.0, (actual_km - planned_km) / planned_km * 100)
            # Allow normal GPS/road variation, but flag a material detour.
            if actual_km >= planned_km + 2 and percent >= 25 and deviation_status != "RED FLAG":
                cur.execute("UPDATE bookings SET route_deviation_status='RED FLAG', route_deviation_distance_km=:1, route_deviation_percent=:2, route_deviation_triggered_on=:3 WHERE booking_id=:4", (actual_km, percent, now, booking_id))
                notify.notify_route_deviation(conn, BOT, dict(b, driver_name=b.get("driver_name"), driver_contact=b.get("driver_contact")), planned_km, actual_km, percent)
                emit_start(conn, "GPS_ROUTE_DEVIATION", "BOOKING", booking_id, department="Safety",
                           context={"deviation_percent": percent, "planned_km": planned_km,
                                    "actual_km": actual_km, "policy_category": "Safety"})
    if d and g:
        try:
            dlat, dlon = [float(x) for x in d.split(",")[:2]]
            glat, glon = [float(x) for x in g.split(",")[:2]]
            dist = round(distance_meters(dlat, dlon, glat, glon), 1)
            status = "SYNCED" if dist <= SYNC_THRESHOLD_METERS else "RED FLAG"
            prev = str(b.get("location_sync") or "").strip()
            cur.execute("UPDATE bookings SET location_sync=:1 "
                        "WHERE booking_id=:2", (status, booking_id))
            if status == "RED FLAG" and prev != "RED FLAG":
                report = {"driver": d, "guest": g, "status": status,
                          "distance_m": dist,
                          "threshold": SYNC_THRESHOLD_METERS}
                notify.notify_red_flag(conn, BOT, dict(b, driver_gps=d,
                                                       guest_gps=g), report)
                emit_start(conn, "GPS_LOCATION_RED_FLAG", "BOOKING", booking_id, department="Safety",
                           context={"distance_m": dist, "policy_category": "Safety"})
        except Exception:
            status, dist = None, None

    # record EVERY capture in the gps_log tracking database (billing record:
    # the full 30-second trail stays available after the trip ends)
    try:
        gps_id = _next_gps_id(cur)
        cur.execute(
            "INSERT INTO gps_log (log_id, booking_id, who, lat, lon, "
            "distance_m, location_sync, location_address, speed_kmh, accuracy_m, captured_dt) "
            "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11)",
            (gps_id, booking_id, who, lat, lon, dist, status,
             location_address, speed_kmh, accuracy_m, now),
        )
        publish(booking_id, {"event_type": "GPS_UPDATE", "event_version": 1,
                             "booking_id": booking_id, "gps_event_id": gps_id,
                             "latitude": lat, "longitude": lon, "speed_kmh": speed_kmh,
                             "accuracy_m": accuracy_m, "timestamp": now.isoformat()})
    except Exception:
        pass
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True, "status": status, "distance_m": dist,
                         "distance_from_pickup_km": from_pickup_km,
                         "distance_to_drop_km": to_drop_km,
                         "current_address": location_address or None,
                         "time_to_drop_hm": time_to_drop_hm,
                         "ts": now.strftime("%I:%M:%S %p")})
