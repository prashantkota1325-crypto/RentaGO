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

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from urllib.parse import quote

from ..templating import templates
from ..db import get_connection
from ..gps import distance_meters, SYNC_THRESHOLD_METERS, reverse_geocode
from ..config import settings
from .. import notify
from ..auth import current_user
from ..scope import visible_booking_ids, can_view
from ..device import is_mobile_request
from ..sla_engine import emit_start

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
    if not user or not is_mobile_request(request):
        return False
    role = (user.get("role") or "").strip().lower()
    if not can_view(visible_booking_ids(user, cur), str(b.get("booking_id"))):
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


@router.post("/{booking_id}/{who}/{token}/ping")
async def track_ping(request: Request, booking_id: str, who: str, token: str):
    """Auto-reported GPS position from the tracking page."""
    try:
        data = await request.json()
        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("position out of range")
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
        cur.execute(
            "INSERT INTO gps_log (log_id, booking_id, who, lat, lon, "
            "distance_m, location_sync, location_address, captured_dt) "
            "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9)",
            (_next_gps_id(cur), booking_id, who, lat, lon, dist, status,
             location_address, now),
        )
    except Exception:
        pass
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True, "status": status, "distance_m": dist,
                         "ts": now.strftime("%I:%M:%S %p")})
