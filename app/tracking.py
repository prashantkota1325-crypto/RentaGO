"""Automatic GPS tracking sweep (driver T-2h, guest T-15min before pickup).

A background loop (started from app.main) wakes every minute and, for every
active confirmed booking:
  - when the DRIVER tracking window opens (2 hours before pickup), queues a
    WhatsApp carrying a one-tap tracking link;
  - when the GUEST tracking window opens (15 minutes before pickup), queues
    the same for the guest.

The recipient opens the link once and allows location access - after that
their phone auto-reports GPS to /track/.../ping every ~30 seconds (see
routes/track.py). No manual location sharing is needed.

Links are built on the public https base URL from the settings table
(browser geolocation is blocked on plain http).
"""

import asyncio
import traceback
import uuid

from .db import get_connection
from . import notify

# Booking states in which live tracking is active (same set as the manual
# live-location flow in routes.bookings).
ACTIVE_REASONS = (
    "Booking Confirmed - Driver & Vehicle Allocated",
    "Guest Trip Started - Awaiting Driver Confirmation",
    "Trip In Progress",
    "Guest Trip Ended - Awaiting Driver Confirmation",
)

SWEEP_USER = {"user_id": "tracking-sweep", "name": "Auto Tracking",
              "role": "Operations"}


def public_base_url(conn):
    """Public https base URL (settings row 'public_base_url')."""
    cur = conn.cursor()
    try:
        cur.execute("SELECT setting_value FROM settings "
                    "WHERE setting_name='public_base_url'")
        row = cur.fetchone()
        return (str(row[0]).strip().rstrip("/") if row and row[0] else "")
    except Exception:
        return ""


def ensure_track_token(cur, bid):
    """Return the booking's tracking token, creating one when missing."""
    cur.execute("SELECT track_token FROM bookings WHERE booking_id=:1", (bid,))
    row = cur.fetchone()
    tok = str(row[0]).strip() if row and row[0] else ""
    if not tok:
        tok = uuid.uuid4().hex[:32]
        cur.execute("UPDATE bookings SET track_token=:1 WHERE booking_id=:2",
                    (tok, bid))
    return tok


def queue_tracking_link(conn, cur, b, who, base):
    """Queue the one-tap tracking WhatsApp for `who` ('driver'|'guest')."""
    from .routes.bookings import _tracking_window_open
    if not _tracking_window_open(b, who):
        return False
    sent = str(b.get("track_sent") or "")
    flag = "D" if who == "driver" else "G"
    if flag in sent:
        return False  # link already sent for this window
    token = ensure_track_token(cur, b.get("booking_id"))
    bid = b.get("booking_id")
    url = f"{base}/track/{bid}/{who}/{token}"
    if who == "driver":
        name = b.get("driver_name")
        phone = b.get("driver_contact")
        role = "Driver"
        title = "RentaGO Live Tracking - Driver"
        who_text = "your live GPS location"
    else:
        name = b.get("guest_name_1")
        phone = b.get("guest_contact")
        role = "Guest"
        title = "RentaGO Live Tracking - Guest"
        who_text = "the guest's live GPS location"
    body = (
        f"{title}\n\n"
        f"Booking ID: {bid}\n"
        f"Pickup: {b.get('pickup_address') or '-'} at "
        f"{b.get('pickup_time') or '-'} on {b.get('pickup_date') or '-'}\n\n"
        f"Tap once and allow location access - {who_text} will be shared "
        f"with RentaGO Operations automatically until the trip ends:\n"
        f"{url}\n\n"
        f"No need to share your location manually - just keep this page open."
    )
    notify.queue(conn, SWEEP_USER, "tracking", bid,
                 [{"name": name, "email": "", "phone": phone,
                   "channels": ("whatsapp",), "role": role}],
                 f"RentaGO Tracking {bid}", body)
    cur.execute("UPDATE bookings SET track_sent=:1 WHERE booking_id=:2",
                ((sent + flag), bid))
    return True


def run_tracking_sweep_once():
    """One sweep pass. Returns a short summary string (or empty)."""
    from .routes.bookings import _pickup_datetime
    conn = get_connection()
    cur = conn.cursor()
    try:
        base = public_base_url(conn)
        placeholders = ", ".join(f":{i + 1}" for i in range(len(ACTIVE_REASONS)))
        cur.execute(
            f"SELECT booking_id, booking_type, company_name, guest_name_1, "
            f"guest_email, guest_contact, admin_name, admin_email, "
            f"admin_contact, driver_name, driver_contact, pickup_address, "
            f"pickup_date, pickup_time, status_reason, track_token, "
            f"track_sent, driver_live_location, guest_live_location, "
            f"location_sync FROM bookings "
            f"WHERE booking_status='2-Confirmed' "
            f"AND status_reason IN ({placeholders})",
            list(ACTIVE_REASONS),
        )
        rows = cur.fetchall()
        queued = []
        for r in rows:
            b = {
                "booking_id": r[0], "booking_type": r[1], "company_name": r[2],
                "guest_name_1": r[3], "guest_email": r[4], "guest_contact": r[5],
                "admin_name": r[6], "admin_email": r[7], "admin_contact": r[8],
                "driver_name": r[9], "driver_contact": r[10],
                "pickup_address": r[11], "pickup_date": r[12],
                "pickup_time": r[13], "status_reason": r[14],
                "track_token": r[15], "track_sent": r[16],
                "driver_live_location": r[17], "guest_live_location": r[18],
                "location_sync": r[19],
            }
            # skip when pickup unknowable (window considered open, but a
            # driver without contact cannot receive anything)
            if not base:
                break
            if queue_tracking_link(conn, cur, b, "driver", base):
                queued.append(f"{b['booking_id']}-Driver")
            if queue_tracking_link(conn, cur, b, "guest", base):
                queued.append(f"{b['booking_id']}-Guest")
        if queued:
            conn.commit()
        return ", ".join(queued)
    finally:
        conn.close()


async def sweep_loop():
    """Background loop: sweep every 60 seconds."""
    print("[tracking] automatic tracking sweep started (60s interval)",
          flush=True)
    while True:
        try:
            from .worker_status import touch_worker
            touch_worker("tracking")
            out = await asyncio.to_thread(run_tracking_sweep_once)
            if out:
                print("[tracking] queued:", out, flush=True)
        except Exception:
            traceback.print_exc()
        from .worker_status import touch_worker
        touch_worker("tracking")
        await asyncio.sleep(60)
