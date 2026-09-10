"""Notification composition + outbox (SOP section 13 notification matrix port).

SMTP sending is blocked on tenant-level M365 admin action (see README), so
notifications are composed and queued in the `notifications` table with
ready-to-open links:
  - email    -> mailto: with subject/body pre-filled (opens the default client)
  - whatsapp -> https://wa.me/<phone>?text=... (opens WhatsApp Web)

Operations can click through from the Notifications screen (or the booking
page card) and mark entries as sent. When SMTP is enabled later, a sender can
drain the queue instead - the payloads are already structured per event.
"""

from datetime import datetime
import os
import sys
from urllib.parse import quote

from .db import get_connection

OPS_EMAIL = os.environ.get("RENTAGO_OPS_EMAIL", "info@rentago.co.in").strip()
OPS_PHONE = os.environ.get("RENTAGO_OPS_PHONE", "").strip()
BRAND_SIGNATURE = "\n\nRentaGO Technologies Pvt. Ltd."


def _portal_role(user):
    return (user or {}).get("role", "").strip().lower()


def _wa_number(phone):
    """Normalize a phone number for wa.me (bare digits, IN default +91)."""
    digits = "".join(c for c in str(phone or "") if c.isdigit() or c == "+")
    digits = digits.replace("+", "")
    if not digits:
        return ""
    if len(digits) == 10:
        digits = "91" + digits
    return digits


def _mailto(email, subject, body):
    return f"mailto:{quote(email)}?subject={quote(subject)}&body={quote(body)}"


def _wa_link(phone, body):
    num = _wa_number(phone)
    if not num:
        return ""
    return f"https://wa.me/{num}?text={quote(body)}"


def _next_notification_id(cur):
    cur.execute("SELECT notification_id FROM notifications")
    max_num = 0
    for (nid,) in cur.fetchall():
        s = str(nid or "").strip()
        if s.upper().startswith("NTF-"):
            try:
                n = int(s[4:])
                if n > max_num:
                    max_num = n
            except Exception:
                pass
    return "NTF-%06d" % (max_num + 1)


def queue(conn, user, event, booking_id, recipients, subject, body):
    """Queue notifications for a list of recipients.

    recipients: list of dicts {name, email, phone, channels, role} where
    channels is a subset of ("email", "whatsapp"). When a recipient carries a
    "role" (Guest / Booking SPOC / Vendor / Driver / Operations), the stored event
    becomes "<event>-<role>" (e.g. step1-Guest, step3-Driver) so the outbox
    Event column identifies who the message is for.
    Returns the list of created ids. Returns [] (and never raises) on failure.
    """
    ids = []
    body = body.rstrip() + BRAND_SIGNATURE
    try:
        cur = conn.cursor()
        now = datetime.now()
        for r in recipients:
            ev = f"{event}-{r['role']}" if r.get("role") else event
            channels = r.get("channels") or ("email", "whatsapp")
            if "email" in channels and (r.get("email") or "").strip():
                nid = _next_notification_id(cur)
                link = _mailto(r["email"], subject, body)
                cur.execute(
                    "INSERT INTO notifications (notification_id, tenant_id, event, channel, "
                    "booking_id, recipient_name, recipient_email, recipient_phone, "
                    "subject, body, link, status, created_dt, created_by) VALUES "
                    "(:1,:2,:3,'email',:4,:5,:6,:7,:8,:9,:10,'Queued',:11,:12)",
                    (nid, (user or {}).get("tenant_id") or "TEN-RENTA-GO", ev, booking_id, r.get("name"), r.get("email"),
                     r.get("phone"), subject[:500], body[:4000], link[:2000],
                      now, (user or {}).get("user_id")),
                )
                ids.append(nid)
            if "whatsapp" in channels and _wa_number(r.get("phone")):
                nid = _next_notification_id(cur)
                link = _wa_link(r.get("phone"), body)
                cur.execute(
                    "INSERT INTO notifications (notification_id, tenant_id, event, channel, "
                    "booking_id, recipient_name, recipient_email, recipient_phone, "
                    "subject, body, link, status, created_dt, created_by) VALUES "
                    "(:1,:2,:3,'whatsapp',:4,:5,:6,:7,:8,:9,:10,'Queued',:11,:12)",
                    (nid, (user or {}).get("tenant_id") or "TEN-RENTA-GO", ev, booking_id, r.get("name"), r.get("email"),
                     r.get("phone"), subject[:500], body[:4000], link[:2000],
                     now, (user or {}).get("user_id")),
                )
                ids.append(nid)
    except Exception:
        import traceback
        print("[notify.queue] FAILED to queue notification:",
              file=sys.stderr, flush=True)
        traceback.print_exc()
    return ids


# ---------------------------------------------------------------------------
# Event composers (SOP 13.1 / 13.2)
# ---------------------------------------------------------------------------
def _step1_body(b):
    bid = b.get("booking_id")
    body = (
        f"RentaGO Booking Request\n\n"
        f"Booking ID: {bid}\n"
        f"Type: {b.get('booking_type') or '-'}\n"
        f"Company: {b.get('company_name') or '-'}\n"
        f"Guest: {b.get('guest_name_1') or '-'}\n"
        f"Pickup: {b.get('pickup_address') or '-'} ({b.get('pickup_city') or '-'}) "
        f"on {b.get('pickup_date') or '-'} at {b.get('pickup_time') or '-'}\n"
        f"Drop: {b.get('drop_address') or '-'} ({b.get('drop_city') or '-'})\n"
        f"Vehicle Type: {b.get('vehicle_type') or '-'}\n"
        + (f"Flight Details: {b.get('flight_details')}\n" if b.get("flight_details") else "")
        + "\nStatus: Pending - Vehicle & Driver Allocation Pending."
    )
    if b.get("driver_reporting_time"):
        body += f"\nDriver Reporting Time: {b.get('driver_reporting_time')}"
    return body


def notify_step1(conn, user, b):
    """Step 1 submitted: email to Guest + Booking SPOC, WhatsApp to Guest."""
    bid = b.get("booking_id")
    subject = f"RentaGO Booking Request {bid}"
    body = _step1_body(b)
    recipients = []
    if b.get("guest_email") or b.get("guest_contact"):
        recipients.append({"name": b.get("guest_name_1"), "email": b.get("guest_email"),
                           "phone": b.get("guest_contact"), "role": "Guest"})
    if b.get("admin_email"):
        recipients.append({"name": b.get("admin_name"), "email": b.get("admin_email"),
                           "phone": b.get("admin_contact"), "channels": ("email",),
                           "role": "Admin"})
    if _portal_role(user).startswith("corporate"):
        recipients.append({"name": "RentaGO Operations", "email": OPS_EMAIL,
                           "phone": OPS_PHONE, "channels": ("email", "whatsapp"),
                           "role": "Operations"})
    return queue(conn, user, "step1", bid, recipients, subject, body)


def notify_tracking_shared(conn, user, b, who, link):
    """Notify RentaGO when a guest or driver shares the live tracking link."""
    party = "Guest" if who == "guest" else "Driver"
    subject = f"RentaGO Live Tracking Shared - {b.get('booking_id')}"
    body = (
        f"RentaGO LIVE TRACKING SHARED\n\n"
        f"Booking ID: {b.get('booking_id')}\n"
        f"Shared by: {party} ({b.get('guest_name_1') if who == 'guest' else b.get('driver_name') or '-'})\n"
        f"Pickup: {b.get('pickup_address') or '-'}\n"
        f"Drop: {b.get('drop_address') or '-'}\n\n"
        f"Open the {party.lower()} tracking link:\n{link}"
    )
    return queue(conn, user, "tracking-share", b.get("booking_id"),
                 [{"name": "RentaGO Operations", "email": OPS_EMAIL,
                   "phone": OPS_PHONE, "channels": ("email", "whatsapp"),
                   "role": "Operations"}], subject, body)


def notify_sos(conn, user, b):
    """Queue an emergency red-trigger notification for Operations and Booking SPOC."""
    bid = b.get("booking_id")
    subject = f"RentaGO SOS EMERGENCY - {bid}"
    body = (
        f"RENTAgo SOS EMERGENCY\n\n"
        f"Booking ID: {bid}\n"
        f"Triggered by: {user.get('name') or user.get('user_id') or '-'}\n"
        f"Guest: {b.get('guest_name_1') or '-'}\n"
        f"Driver: {b.get('driver_name') or '-'}\n"
        f"Pickup: {b.get('pickup_address') or '-'}\n"
        f"Drop: {b.get('drop_address') or '-'}\n"
        f"Driver GPS: {b.get('driver_gps') or '-'}\n"
        f"Guest GPS: {b.get('guest_gps') or '-'}\n\n"
        "URGENT: Contact the passenger/driver and Operations immediately."
    )
    recipients = [{"name": "RentaGO Operations", "email": OPS_EMAIL,
                   "phone": OPS_PHONE, "channels": ("email", "whatsapp"),
                   "role": "Operations"}]
    admin_email = b.get("admin_email") or (user.get("email") if
                                            (user.get("role") or "").lower().startswith("corporate")
                                            else "")
    if admin_email:
        recipients.append({"name": b.get("admin_name") or user.get("name"),
                           "email": admin_email, "phone": b.get("admin_contact") or user.get("mobile"),
                           "channels": ("email", "whatsapp"), "role": "Admin"})
    cur = conn.cursor()
    cur.execute("SELECT name, email, mobile FROM users WHERE UPPER(role) IN ('SUPER ADMIN','HQ') AND status='Active'")
    for name, email, phone in cur.fetchall():
        if email and not any(r.get("email") == email for r in recipients):
            recipients.append({"name": name, "email": email, "phone": phone,
                               "channels": ("email", "whatsapp"), "role": "Management"})
    return queue(conn, user, "sos", bid, recipients, subject, body)


def notify_safety_incident(conn, user, b, priority, issues):
    """Immediately notify Operations and Management of a safety complaint."""
    subject = f"RentaGO {priority} SAFETY INCIDENT - {b.get('booking_id')}"
    body = (f"RENTAgo SAFETY INCIDENT ({priority})\n\nBooking ID: {b.get('booking_id')}\n"
            f"Guest: {b.get('guest_name_1') or '-'}\nDriver: {b.get('driver_name') or '-'}\n"
            f"Safety issues: {issues or '-'}\nPickup: {b.get('pickup_address') or '-'}\n"
            f"Drop: {b.get('drop_address') or '-'}\n\nImmediate review required.")
    recipients = [
        {"name": "RentaGO Operations", "email": OPS_EMAIL, "phone": OPS_PHONE,
         "channels": ("email", "whatsapp"), "role": "Operations"},
        {"name": "RentaGO Management", "email": OPS_EMAIL, "phone": OPS_PHONE,
         "channels": ("email", "whatsapp"), "role": "Management"},
    ]
    return queue(conn, user, "safety-incident", b.get("booking_id"), recipients,
                 subject, body)


def notify_trip_trigger(conn, user, b, trigger):
    """Notify RentaGO executives after each Guest/Driver end confirmation."""
    subject = f"RentaGO Trip Trigger - {b.get('booking_id')}"
    body = (f"RENTAgo TRIP TRIGGER\n\nBooking ID: {b.get('booking_id')}\n"
            f"Trigger: {trigger}\nGuest: {b.get('guest_name_1') or '-'}\n"
            f"Driver: {b.get('driver_name') or '-'}\n"
            "Please review the next operational/feedback action.")
    return queue(conn, user, "trip-trigger", b.get("booking_id"), [
        {"name": "RentaGO Operations", "email": OPS_EMAIL, "phone": OPS_PHONE,
         "channels": ("email", "whatsapp"), "role": "Operations"},
    ], subject, body)


def notify_pickup_arrival(conn, user, b, distance_m):
    """Notify Guest, Booking SPOC, and Operations when Driver reaches pickup."""
    bid = b.get("booking_id")
    subject = f"RentaGO Driver Near Pickup - {bid}"
    body = (f"RentaGO DRIVER ARRIVAL ALERT\n\nBooking ID: {bid}\n"
            f"Driver: {b.get('driver_name') or '-'}\n"
            f"Pickup: {b.get('pickup_address') or '-'}\n"
            f"Distance from pickup: {distance_m:.0f} metres\n\n"
            "The Driver has reached near the Pickup Location.")
    recipients = []
    if b.get("guest_email") or b.get("guest_contact"):
        recipients.append({"name": b.get("guest_name_1"), "email": b.get("guest_email"),
                           "phone": b.get("guest_contact"), "role": "Guest"})
    if b.get("admin_email") or b.get("admin_contact"):
        recipients.append({"name": b.get("admin_name"), "email": b.get("admin_email"),
                           "phone": b.get("admin_contact"),
                           "channels": ("email", "whatsapp"), "role": "Admin"})
    recipients.append({"name": "RentaGO Operations", "email": OPS_EMAIL,
                       "phone": OPS_PHONE, "channels": ("email", "whatsapp"),
                       "role": "Operations"})
    return queue(conn, user, "pickup-arrival", bid, recipients, subject, body)


def notify_route_deviation(conn, user, b, planned_km, actual_km, percent):
    subject = f"RentaGO RED FLAG Route Deviation - {b.get('booking_id')}"
    body = (f"RENTAgo ROUTE DEVIATION RED FLAG\n\nBooking ID: {b.get('booking_id')}\n"
            f"Driver: {b.get('driver_name') or '-'}\n"
            f"Planned Google Routes distance: {planned_km:.1f} km\n"
            f"Tracked Driver path: {actual_km:.1f} km\n"
            f"Deviation: {percent:.1f}%\n\n"
            "RentaGO Operations must contact the Driver immediately and record the reason.")
    recipients = [{"name": "RentaGO Operations", "email": OPS_EMAIL,
                   "phone": OPS_PHONE, "channels": ("email", "whatsapp"),
                   "role": "Operations"}]
    if b.get("guest_email") or b.get("guest_contact"):
        recipients.append({"name": b.get("guest_name_1"), "email": b.get("guest_email"),
                           "phone": b.get("guest_contact"), "role": "Guest"})
    if b.get("admin_email") or b.get("admin_contact"):
        recipients.append({"name": b.get("admin_name"), "email": b.get("admin_email"),
                           "phone": b.get("admin_contact"),
                           "channels": ("email", "whatsapp"), "role": "Admin"})
    if b.get("driver_contact"):
        recipients.append({"name": b.get("driver_name"), "email": "",
                           "phone": b.get("driver_contact"),
                           "channels": ("whatsapp",), "role": "Driver"})
    return queue(conn, user, "route-deviation", b.get("booking_id"),
                 recipients, subject, body)


def notify_step2(conn, user, b):
    """Step 2: vendor assignment notification to the vendor."""
    bid = b.get("booking_id")
    subject = f"RentaGO Vendor Assignment {bid}"
    body = (
        f"RentaGO Vendor Assignment\n\n"
        f"Booking ID: {bid}\n"
        f"Vendor: {b.get('vendor_name') or '-'}\n"
        f"Package: {b.get('vendor_pkg_type') or '-'}\n"
        f"Guest: {b.get('guest_name_1') or '-'}\n"
        f"Pickup: {b.get('pickup_address') or '-'} on {b.get('pickup_date') or '-'} "
        f"at {b.get('pickup_time') or '-'}\n"
        f"Drop: {b.get('drop_address') or '-'}\n"
        f"Vehicle Type: {b.get('vehicle_type') or '-'}\n"
        f"Flight Details: {b.get('flight_details') or '-'}\n\n"
        f"Please provide vehicle & driver details before the allocation deadline."
    )
    if b.get("driver_reporting_time"):
        body += f"\nDriver Reporting Time: {b.get('driver_reporting_time')}"
    recipients = [{"name": b.get("vendor_name"), "email": b.get("vendor_email"),
                   "phone": b.get("vendor_contact"), "role": "Vendor"}]
    return queue(conn, user, "step2", bid, recipients, subject, body)


def _route_link(b):
    from urllib.parse import quote as _q
    return "https://www.google.com/maps/dir/{}/{}".format(
        _q((b.get("pickup_address") or "").strip()),
        _q((b.get("drop_address") or "").strip()),
    )


def notify_step3(conn, user, b):
    """Step 3 confirmed: Guest + Booking SPOC confirmation; driver trip WhatsApp."""
    bid = b.get("booking_id")
    subject = f"RentaGO Booking Confirmed {bid}"
    body = (
        f"RentaGO Booking CONFIRMED\n\n"
        f"Booking ID: {bid}\n"
        f"Guest: {b.get('guest_name_1') or '-'}\n"
        f"Driver: {b.get('driver_name') or '-'} ({b.get('driver_contact') or '-'})\n"
        f"Vehicle: {b.get('vehicle_no') or '-'} ({b.get('vehicle_type') or '-'})\n"
        f"Driver Reporting Time: {b.get('driver_reporting_time') or '-'}\n"
        f"Pickup: {b.get('pickup_address') or '-'} on {b.get('pickup_date') or '-'} "
        f"at {b.get('pickup_time') or '-'}\n"
        f"Drop: {b.get('drop_address') or '-'}\n"
        f"Route: {_route_link(b)}\n\n"
        f"Status: Booking Confirmed - Driver & Vehicle Allocated."
    )
    recipients = []
    if b.get("guest_email") or b.get("guest_contact"):
        recipients.append({"name": b.get("guest_name_1"), "email": b.get("guest_email"),
                           "phone": b.get("guest_contact"), "role": "Guest"})
    if b.get("admin_email"):
        recipients.append({"name": b.get("admin_name"), "email": b.get("admin_email"),
                           "phone": b.get("admin_contact"), "channels": ("email", "whatsapp"),
                           "role": "Admin"})
    if b.get("vendor_email") or b.get("vendor_contact"):
        recipients.append({"name": b.get("vendor_name"), "email": b.get("vendor_email"),
                           "phone": b.get("vendor_contact"), "role": "Vendor"})
    elif _portal_role(user) in {"vendor", "vendor admin", "vendor operations"}:
        recipients.append({"name": user.get("name"), "email": user.get("email"),
                           "phone": user.get("mobile"), "role": "Vendor"})
    if _portal_role(user) in {"vendor", "vendor admin", "vendor operations"}:
        recipients.append({"name": "RentaGO Operations", "email": OPS_EMAIL,
                           "phone": OPS_PHONE, "channels": ("email", "whatsapp"),
                           "role": "Operations"})
    ids = queue(conn, user, "step3", bid, recipients, subject, body)

    driver_body = (
        f"RentaGO Trip Assignment\n\n"
        f"Booking ID: {bid}\n"
        f"Driver: {b.get('driver_name') or '-'}\n"
        f"Vehicle: {b.get('vehicle_no') or '-'}\n"
        f"Reporting Time: {b.get('driver_reporting_time') or '-'}\n"
        f"Pickup: {b.get('pickup_address') or '-'} on {b.get('pickup_date') or '-'} "
        f"at {b.get('pickup_time') or '-'}\n"
        f"Drop: {b.get('drop_address') or '-'}\n"
        f"Route: {_route_link(b)}\n"
        f"Instructions: {b.get('driver_instructions') or '-'}"
    )
    ids += queue(conn, user, "step3", bid,
                 [{"name": b.get("driver_name"), "email": "",
                   "phone": b.get("driver_contact"), "channels": ("whatsapp",),
                   "role": "Driver"}],
                 f"RentaGO Trip {bid}", driver_body)
    return ids


def notify_cancellation(conn, user, b, code, desc, charges):
    """Cancellation: Guest + Booking SPOC + Vendor email; + Driver WhatsApp."""
    bid = b.get("booking_id")
    subject = f"RentaGO Booking Cancelled {bid}"
    body = (
        f"RentaGO Booking CANCELLED\n\n"
        f"Booking ID: {bid}\n"
        f"Guest: {b.get('guest_name_1') or '-'}\n"
        f"Company: {b.get('company_name') or '-'}\n"
        f"Pickup: {b.get('pickup_address') or '-'} on {b.get('pickup_date') or '-'} "
        f"at {b.get('pickup_time') or '-'}\n\n"
        f"Cancellation Reason ({code}): {desc}\n"
        f"Cancellation Charges: Rs. {charges:.0f}\n\n"
        f"Cancellation Policy:\n"
        f"1: After Step 1 before Step 3 (guest cancel) - Rs.0\n"
        f"2: After Step 3, 6+ hrs before pickup - Rs.0\n"
        f"3: After Step 3, under 6 hrs before pickup - Rs.500\n"
        f"4: Cab reached, guest no-show - Rs.1000\n"
        f"5: Cab did not reach on time (vendor fault) - Rs.0\n"
        f"6: Cab breakdown during ongoing trip - Rs.0"
    )
    recipients = []
    if b.get("guest_email") or b.get("guest_contact"):
        recipients.append({"name": b.get("guest_name_1"), "email": b.get("guest_email"),
                           "phone": b.get("guest_contact"), "role": "Guest"})
    if b.get("admin_email"):
        recipients.append({"name": b.get("admin_name"), "email": b.get("admin_email"),
                           "phone": b.get("admin_contact"), "channels": ("email", "whatsapp"),
                           "role": "Admin"})
    if b.get("vendor_email") or b.get("vendor_contact"):
        recipients.append({"name": b.get("vendor_name"), "email": b.get("vendor_email"),
                           "phone": b.get("vendor_contact"), "role": "Vendor"})
    if b.get("driver_contact"):
        recipients.append({"name": b.get("driver_name"), "email": "",
                           "phone": b.get("driver_contact"), "channels": ("whatsapp",),
                           "role": "Driver"})
    return queue(conn, user, "cancellation", bid, recipients, subject, body)


def notify_final_invoice(conn, user, inv, b):
    """Final invoice: full expense breakdown to Guest + Booking SPOC."""
    iid = inv.get("invoice_id")
    subject = f"RentaGO Final Invoice {iid}"
    body = (
        f"RentaGO FINAL INVOICE\n\n"
        f"Invoice ID: {iid}\n"
        f"Booking ID: {inv.get('booking_id')}\n"
        f"Guest: {inv.get('guest_name') or '-'}\n"
        f"Company: {inv.get('company_name') or '-'}\n\n"
        f"Expense Breakdown:\n"
        f"  Toll: Rs. {inv.get('toll') or 0}\n"
        f"  Parking: Rs. {inv.get('parking') or 0}\n"
        f"  Extra Kms: Rs. {inv.get('extra_kms') or 0}\n"
        f"  Extra Hours: Rs. {inv.get('extra_hours') or 0}\n"
        f"  Other Expenses: Rs. {inv.get('other_expenses') or 0}\n"
         f"  Total Trip Expenses: Rs. {inv.get('total_vendor_expenses') or 0}\n"
        f"  Final Amount: Rs. {inv.get('final_amount') or 0}\n\n"
        f"Original Amount: Rs. {inv.get('original_amount') or 0}"
    )
    recipients = []
    guest_email = (b or {}).get("guest_email") or ""
    guest_phone = (b or {}).get("guest_contact") or ""
    if guest_email or guest_phone:
        recipients.append({"name": inv.get("guest_name"), "email": guest_email,
                           "phone": guest_phone, "role": "Guest"})
    admin_email = (b or {}).get("admin_email") or ""
    if admin_email:
        recipients.append({"name": (b or {}).get("admin_name"), "email": admin_email,
                           "phone": (b or {}).get("admin_contact"),
                           "channels": ("email", "whatsapp"), "role": "Admin"})
    return queue(conn, user, "final-invoice", inv.get("booking_id"), recipients,
                 subject, body)


def notify_red_flag(conn, user, b, report):
    """GPS red flag: Ops + Guest + Booking SPOC with coordinates and distance."""
    bid = b.get("booking_id")
    subject = f"RentaGO RED FLAG - Location Mismatch {bid}"
    body = (
        f"RentaGO LOCATION RED FLAG\n\n"
        f"Booking ID: {bid}\n"
        f"Guest: {b.get('guest_name_1') or '-'}\n"
        f"Driver: {b.get('driver_name') or '-'}\n"
        f"Distance between driver & guest: {report.get('distance_m'):.0f} m "
        f"(threshold {report.get('threshold')} m)\n"
        f"Driver location: {report.get('driver') or '-'}\n"
        f"Guest location: {report.get('guest') or '-'}\n\n"
        f"Please verify the trip immediately."
    )
    recipients = [{"name": "RentaGO Operations", "email": OPS_EMAIL,
                   "phone": OPS_PHONE, "channels": ("email",), "role": "Operations"}]
    if b.get("guest_email"):
        recipients.append({"name": b.get("guest_name_1"), "email": b.get("guest_email"),
                           "phone": b.get("guest_contact"), "channels": ("email", "whatsapp"),
                           "role": "Guest"})
    if b.get("admin_email"):
        recipients.append({"name": b.get("admin_name"), "email": b.get("admin_email"),
                           "phone": b.get("admin_contact"), "channels": ("email", "whatsapp"),
                           "role": "Admin"})
    return queue(conn, user, "red-flag", bid, recipients, subject, body)


def request_driver_location(conn, user, b):
    """WhatsApp to the driver with live-location sharing steps (SOP 8.2)."""
    bid = b.get("booking_id")
    subject = f"RentaGO Location Request {bid}"
    body = (
        f"RentaGO Driver Live Location Request\n\n"
        f"Booking ID: {bid}\n"
        f"Driver: {b.get('driver_name') or '-'}\n"
        f"Pickup: {b.get('pickup_address') or '-'} at {b.get('pickup_time') or '-'}\n\n"
        f"Please share your live location:\n"
        f"1. Open Google Maps\n"
        f"2. Tap the blue dot -> 'Share location'\n"
        f"3. Choose 'Until you turn this off' or at least 1 hour\n"
        f"4. Copy the link and send it to RentaGO Operations on WhatsApp."
    )
    recipients = [{"name": b.get("driver_name"), "email": "",
                   "phone": b.get("driver_contact"), "channels": ("whatsapp",),
                   "role": "Driver"}]
    return queue(conn, user, "driver-location-request", bid, recipients, subject, body)


def notify_modification(conn, user, b, changes, section="Booking Details",
                        notify_driver=False):
    """Booking information was MODIFIED after submission: re-send the updated
    details to the Guest and the Booking SPOC (email + WhatsApp), listing what
    changed. When the driver/vehicle changed, the new driver also gets the
    trip assignment on WhatsApp.

    changes: list of (label, old, new) tuples (empty -> full summary only).
    """
    bid = b.get("booking_id")
    subject = f"RentaGO Booking Updated {bid}"
    lines = [
        f"RentaGO BOOKING UPDATED - {section}", "",
        f"Booking ID: {bid}",
        f"Guest: {b.get('guest_name_1') or '-'}",
        f"Company: {b.get('company_name') or '-'}", "",
    ]
    if changes:
        lines.append("Changed details:")
        for label, old, new in changes[:15]:
            lines.append(f"  {label}: {old}  ->  {new}")
        if len(changes) > 15:
            lines.append(f"  ...and {len(changes) - 15} more change(s)")
        lines.append("")
    lines += [
        "Current booking summary:",
        f"Pickup: {b.get('pickup_address') or '-'} ({b.get('pickup_city') or '-'}) "
        f"on {b.get('pickup_date') or '-'} at {b.get('pickup_time') or '-'}",
        f"Drop: {b.get('drop_address') or '-'} ({b.get('drop_city') or '-'})",
        f"Vehicle Type: {b.get('vehicle_type') or '-'}",
        f"Package: {b.get('package_type') or '-'}",
    ]
    if b.get("vendor_name"):
        lines.append(f"Vendor: {b.get('vendor_name')} "
                     f"({b.get('vendor_pkg_type') or '-'})")
    if b.get("driver_name"):
        lines.append(f"Driver: {b.get('driver_name')} ({b.get('driver_contact') or '-'})")
        lines.append(f"Vehicle No: {b.get('vehicle_no') or '-'}")
        lines.append(f"Driver Reporting Time: {b.get('driver_reporting_time') or '-'}")
    body = "\n".join(lines)

    recipients = []
    if b.get("guest_email") or b.get("guest_contact"):
        recipients.append({"name": b.get("guest_name_1"),
                           "email": b.get("guest_email"),
                           "phone": b.get("guest_contact"), "role": "Guest"})
    if b.get("admin_email"):
        recipients.append({"name": b.get("admin_name"),
                           "email": b.get("admin_email"),
                           "phone": b.get("admin_contact"),
                           "channels": ("email", "whatsapp"), "role": "Admin"})
    ids = queue(conn, user, "modification", bid, recipients, subject, body)

    if notify_driver and b.get("driver_contact"):
        driver_body = (
            f"RentaGO Trip Assignment (UPDATED)\n\n"
            f"Booking ID: {bid}\n"
            f"Driver: {b.get('driver_name') or '-'}\n"
            f"Vehicle: {b.get('vehicle_no') or '-'}\n"
            f"Reporting Time: {b.get('driver_reporting_time') or '-'}\n"
            f"Pickup: {b.get('pickup_address') or '-'} on {b.get('pickup_date') or '-'} "
            f"at {b.get('pickup_time') or '-'}\n"
            f"Drop: {b.get('drop_address') or '-'}\n"
            f"Route: {_route_link(b)}\n"
            f"Instructions: {b.get('driver_instructions') or '-'}"
        )
        ids += queue(conn, user, "modification", bid,
                     [{"name": b.get("driver_name"), "email": "",
                       "phone": b.get("driver_contact"),
                       "channels": ("whatsapp",), "role": "Driver"}],
                  f"RentaGO Trip {bid} (Updated)", driver_body)
    return ids
