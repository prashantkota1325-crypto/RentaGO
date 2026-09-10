"""SLA monitoring sweep (port of the VBA Application.OnTime 5-minute checker).

Rules (SOP section 9):
  1. Vendor allocation SLA (5 min):  Step 1 submitted > 5 minutes ago and no
     vendor allocated yet -> INFO alert.
  2. Driver/vehicle allocation SLA (45/60 min): vendor assigned but no driver
     for 45 minutes -> WARNING; at 60 minutes -> AUTO-REASSIGN (vendor cleared,
     status reset to 'Vendor Reallocation Pending (60 min timeout)').

The sweep remains available on-request for operator roles and can be forced
from the Ops dashboard. The durable `app.sla_worker` also runs it every minute
so auto-reassignments, TAT status changes, and escalations continue while the
dashboard is closed.
"""

import threading
from datetime import datetime

from .db import get_connection

VENDOR_SLA_MINUTES = 5
DRIVER_WARNING_MINUTES = 45
DRIVER_REASSIGN_MINUTES = 60

REALLOC_REASON = "Vendor Reallocation Pending (60 min timeout)"

_last_sweep = None
_lock = threading.Lock()


def _sla_for(cur, department):
    cur.execute(
        "SELECT vendor_minutes, driver_warning_minutes, driver_reassign_minutes "
        "FROM sla_settings WHERE department=:1", (department or "Operations",))
    row = cur.fetchone()
    if not row:
        return VENDOR_SLA_MINUTES, DRIVER_WARNING_MINUTES, DRIVER_REASSIGN_MINUTES
    return tuple(int(x) for x in row)


def _minutes_since(cur, column, booking_id):
    """Whole minutes between a bookings timestamp column and now (or None)."""
    try:
        cur.execute(
            f"SELECT TO_CHAR({column}, 'YYYY-MM-DD HH24:MI:SS') FROM bookings "
            f"WHERE booking_id=:1",
            (booking_id,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        ref = datetime.strptime(str(row[0]).strip(), "%Y-%m-%d %H:%M:%S")
        return max(0, int((datetime.now() - ref).total_seconds() // 60))
    except Exception:
        return None


def run_sweep(conn, force=False):
    """Run the SLA sweep (if due) and return the current alert list.

    Returns a list of alert dicts:
      {booking_id, kind, level, minutes, message}
    kind: 'vendor' (5-min) | 'driver-warning' (45) | 'reassigned' (60 applied)
    """
    global _last_sweep
    with _lock:
        now = datetime.now()
        if not force and _last_sweep and (now - _last_sweep).total_seconds() < 300:
            return None  # not due; caller may show the "no fresh sweep" state
        _last_sweep = now

    from .sla_engine import evaluate_instances
    evaluate_instances(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT booking_id, booking_status, status_reason, vendor_name, "
        "driver_name, department FROM bookings WHERE booking_status LIKE '1-%'"
    )
    pending = cur.fetchall()

    alerts = []
    for booking_id, status, reason, vendor, driver, department in pending:
        vendor_sla, driver_warning, driver_reassign = _sla_for(cur, department)
        reason = (reason or "").strip()
        vendor = (vendor or "").strip()
        driver = (driver or "").strip()

        if not vendor and reason in (
            "Vehicle & Driver Allocation Pending",
            REALLOC_REASON,
        ):
            mins = _minutes_since(cur, "step1_time", booking_id)
            if mins is not None and mins > vendor_sla:
                alerts.append({
                    "booking_id": booking_id, "kind": "vendor", "level": "info",
                    "minutes": mins,
                    "message": (f"Vendor not allocated for {booking_id} - "
                                f"{mins} minutes elapsed (SLA {vendor_sla} min)."),
                })
            continue

        if vendor and not driver and reason == "Awaiting Driver & Vehicle Allocation":
            mins = _minutes_since(cur, "step2_time", booking_id)
            if mins is None:
                mins = _minutes_since(cur, "step1_time", booking_id)
            if mins is None:
                continue
            if mins >= driver_reassign:
                # AUTO-REASSIGN: clear the vendor, reset to step 2 intake.
                try:
                    cur.execute(
                        "UPDATE bookings SET vendor_name='', vendor_contact='', "
                        "vendor_email='', vendor_pkg_type='', step2_time=NULL, "
                        f"status_reason='{REALLOC_REASON}', done_by_vendor='SLA-ENGINE' "
                        "WHERE booking_id=:1",
                        (booking_id,),
                    )
                    alerts.append({
                        "booking_id": booking_id, "kind": "reassigned",
                        "level": "danger", "minutes": mins,
                        "message": (f"AUTO-REASSIGN: vendor cleared for {booking_id} "
                                    f"after {mins} min without driver/vehicle "
                                    f"allocation (60 min timeout)."),
                    })
                except Exception:
                    pass
            elif mins >= driver_warning:
                left = driver_reassign - mins
                alerts.append({
                    "booking_id": booking_id, "kind": "driver-warning",
                    "level": "warning", "minutes": mins,
                    "message": (f"Only {left} minutes left to allocate driver & "
                                f"vehicle for {booking_id} (vendor assigned "
                                f"{mins} min ago)."),
                })
    try:
        conn.commit()
    except Exception:
        pass
    return alerts


def maybe_sweep(user):
    """Run the sweep (throttled) when `user` is an operator. Returns alerts or None."""
    if not user or (user.get("role") or "").strip().lower() not in (
        "super admin", "hq", "ceo", "operations", "vendor manager",
    ):
        return None
    try:
        conn = get_connection()
    except Exception:
        return None
    try:
        return run_sweep(conn, force=False)
    except Exception:
        return None
    finally:
        conn.close()
