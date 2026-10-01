"""Server-side Ideal Now eligibility, availability, and booking claims."""

from datetime import datetime, timedelta
import uuid

from .db import get_connection
from .scope import authorization_tenant, VENDOR_PORTAL_ROLES
from .audit import audit

STALE_MINUTES = 30
ACTIVE_TRIP_STATES = ("In Progress", "Trip In Progress")


def _driver(cur, user):
    tenant_id = str(user.get("tenant_id") or "").strip()
    emp_id = str(user.get("emp_id") or "").strip()
    if not tenant_id or not emp_id:
        return None
    cur.execute(
        "SELECT d.driver_id,d.tenant_id,d.vendor_id,d.driver_name,d.mobile,d.status,"
        "d.license_expiry,d.police_verification,d.background_check,d.compliance_status,"
        "v.status FROM drivers d JOIN vendors v ON v.vendor_id=d.vendor_id "
        "AND v.tenant_id=d.tenant_id WHERE d.tenant_id=:1 AND d.driver_id=:2",
        (tenant_id, emp_id),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            "SELECT d.driver_id,d.tenant_id,d.vendor_id,d.driver_name,d.mobile,d.status,"
            "d.license_expiry,d.police_verification,d.background_check,d.compliance_status,"
            "v.status FROM drivers d JOIN vendors v ON v.vendor_id=d.vendor_id "
            "AND v.tenant_id=d.tenant_id WHERE d.tenant_id=:1 "
            "AND UPPER(TRIM(d.driver_name))=UPPER(TRIM(:2)) "
            "AND REPLACE(d.mobile,' ','')=REPLACE(:3,' ','')",
            (tenant_id, user.get("name") or "", user.get("mobile") or ""),
        )
        row = cur.fetchone()
    return row


def _eligibility(cur, user, driver_row):
    if not driver_row:
        return False, "driver-not-found"
    if str(driver_row[5] or "").strip().lower() != "active":
        return False, "driver-inactive"
    if str(driver_row[10] or "").strip().lower() != "active":
        return False, "vendor-inactive"
    expiry = driver_row[6]
    if expiry and hasattr(expiry, "date"):
        expiry = expiry.date()
    if expiry and expiry < datetime.now().date():
        return False, "driver-license-expired"
    for value in (driver_row[7], driver_row[8], driver_row[9]):
        if str(value or "").strip().lower() in {"no", "failed", "expired", "invalid"}:
            return False, "driver-compliance-failed"
    cur.execute(
        "SELECT COUNT(*) FROM trips WHERE tenant_id=:1 AND UPPER(TRIM(driver_name))=UPPER(TRIM(:2)) "
        "AND trip_status IN ('In Progress','Trip In Progress')",
        (driver_row[1], driver_row[3]),
    )
    if int(cur.fetchone()[0] or 0):
        return False, "active-trip"
    cur.execute(
        "SELECT COUNT(*) FROM bookings WHERE tenant_id=:1 "
        "AND (UPPER(TRIM(driver_name))=UPPER(TRIM(:2)) OR REPLACE(driver_contact,' ','')=REPLACE(:3,' ','')) "
        "AND pickup_date>=TRUNC(SYSDATE) AND pickup_date<TRUNC(SYSDATE)+1 "
        "AND booking_status NOT LIKE '3-%' AND NVL(status_reason,'')<>'Trip Completed'",
        (driver_row[1], driver_row[3], driver_row[4]),
    )
    if int(cur.fetchone()[0] or 0):
        return False, "same-day-conflict"
    return True, "eligible"


def _active_session(cur, driver_id, tenant_id):
    cur.execute(
        "SELECT availability_id,status,last_seen_at FROM driver_availability_sessions "
        "WHERE driver_id=:1 AND tenant_id=:2 AND status='IDEAL_NOW' "
        "ORDER BY activated_at DESC FETCH FIRST 1 ROWS ONLY",
        (driver_id, tenant_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    last_seen = row[2]
    if last_seen and datetime.now() - last_seen > timedelta(minutes=STALE_MINUTES):
        cur.execute(
            "UPDATE driver_availability_sessions SET status='OFFLINE',deactivated_at=SYSDATE,updated_at=SYSTIMESTAMP WHERE availability_id=:1",
            (row[0],),
        )
        return None
    return row


def activate(user):
    conn = get_connection(); cur = conn.cursor()
    try:
        tenant_id = authorization_tenant(user) or user.get("tenant_id")
        driver = _driver(cur, user)
        ok, reason = _eligibility(cur, user, driver)
        if not tenant_id or not ok:
            conn.close(); return False, reason
        active = _active_session(cur, driver[0], tenant_id)
        if active:
            cur.execute("UPDATE driver_availability_sessions SET last_seen_at=SYSDATE,updated_at=SYSTIMESTAMP WHERE availability_id=:1", (active[0],))
            conn.commit(); conn.close(); return True, "already-active"
        aid = "DAS-" + uuid.uuid4().hex[:20]
        cur.execute(
            "INSERT INTO driver_availability_sessions (availability_id,tenant_id,driver_id,vendor_id,status,activated_at,last_seen_at,created_at,updated_at) "
            "VALUES (:1,:2,:3,:4,'IDEAL_NOW',SYSTIMESTAMP,SYSTIMESTAMP,SYSTIMESTAMP,SYSTIMESTAMP)",
            (aid, tenant_id, driver[0], driver[2]),
        )
        audit(conn, user, "IDEAL_NOW_ENABLED", driver[0], f"tenant_id={tenant_id}; vendor_id={driver[2]}")
        conn.commit(); conn.close(); return True, "activated"
    except Exception:
        conn.rollback(); conn.close(); raise


def deactivate(user):
    conn = get_connection(); cur = conn.cursor()
    try:
        driver = _driver(cur, user); tenant_id = authorization_tenant(user) or user.get("tenant_id")
        if not driver or not tenant_id:
            conn.close(); return False
        cur.execute("UPDATE driver_availability_sessions SET status='OFFLINE',deactivated_at=SYSDATE,updated_at=SYSTIMESTAMP WHERE driver_id=:1 AND tenant_id=:2 AND status='IDEAL_NOW'", (driver[0], tenant_id))
        audit(conn, user, "IDEAL_NOW_DISABLED", driver[0], f"tenant_id={tenant_id}")
        conn.commit(); conn.close(); return True
    except Exception:
        conn.rollback(); conn.close(); raise


def opportunities(user):
    conn = get_connection(); cur = conn.cursor()
    try:
        tenant_id = authorization_tenant(user) or user.get("tenant_id")
        driver = _driver(cur, user)
        ok, _ = _eligibility(cur, user, driver)
        if not tenant_id or not driver or not ok or not _active_session(cur, driver[0], tenant_id):
            conn.close(); return []
        cur.execute(
            "SELECT booking_id,booking_type,pickup_date,pickup_time,pickup_address,drop_address,vehicle_type,package_type "
            "FROM bookings WHERE tenant_id=:1 AND vendor_id=:2 AND booking_status='1-Pending' "
            "AND status_reason='Awaiting Driver & Vehicle Allocation' AND (driver_name IS NULL OR TRIM(driver_name) IS NULL) "
            "AND (vehicle_no IS NULL OR TRIM(vehicle_no) IS NULL) ORDER BY pickup_date,pickup_time",
            (tenant_id, driver[2]),
        )
        rows = [dict(zip(("booking_id","booking_type","pickup_date","pickup_time","pickup_address","drop_address","vehicle_type","package_type"), r)) for r in cur.fetchall()]
        conn.close(); return rows
    except Exception:
        conn.close(); raise


def heartbeat(user):
    conn = get_connection(); cur = conn.cursor()
    try:
        tenant_id = authorization_tenant(user) or user.get("tenant_id")
        driver = _driver(cur, user)
        if not tenant_id or not driver:
            conn.close(); return False, "driver-not-found"
        active = _active_session(cur, driver[0], tenant_id)
        if not active:
            conn.close(); return False, "ideal-now-inactive"
        cur.execute(
            "UPDATE driver_availability_sessions SET last_seen_at=SYSDATE,updated_at=SYSTIMESTAMP WHERE availability_id=:1",
            (active[0],),
        )
        conn.commit(); conn.close(); return True, "heartbeat"
    except Exception:
        conn.rollback(); conn.close(); raise


def status(user):
    conn = get_connection(); cur = conn.cursor()
    try:
        driver = _driver(cur, user)
        tenant_id = authorization_tenant(user) or user.get("tenant_id")
        if not driver or not tenant_id:
            conn.close(); return {"status": "OFFLINE", "reason": "driver-not-found"}
        row = _active_session(cur, driver[0], tenant_id)
        conn.commit(); conn.close()
        return {"status": "IDEAL_NOW" if row else "OFFLINE", "reason": "active" if row else "inactive"}
    except Exception:
        conn.close(); raise


def accept(user, booking_id, vehicle_no):
    """Atomically claim a Vendor-assigned booking for the authenticated Driver."""
    conn = get_connection(); cur = conn.cursor()
    try:
        tenant_id = authorization_tenant(user) or user.get("tenant_id")
        driver = _driver(cur, user)
        if not tenant_id or not driver:
            conn.close(); return False, "driver-not-found"
        if not _active_session(cur, driver[0], tenant_id):
            conn.close(); return False, "ideal-now-inactive"
        cur.execute("SELECT * FROM bookings WHERE booking_id=:1 FOR UPDATE", (booking_id.strip(),))
        row = cur.fetchone()
        if not row:
            conn.close(); return False, "booking-not-found"
        cols = [d[0].lower() for d in cur.description]
        booking = dict(zip(cols, row))
        if (str(booking.get("tenant_id") or "") != str(tenant_id)
                or str(booking.get("vendor_id") or "") != str(driver[2])
                or (booking.get("booking_status") or "").strip() != "1-Pending"
                or (booking.get("status_reason") or "").strip() != "Awaiting Driver & Vehicle Allocation"
                or (booking.get("driver_name") or "").strip()
                or (booking.get("vehicle_no") or "").strip()):
            conn.close(); return False, "booking-not-available"
        ok, reason = _eligibility(cur, user, driver)
        if not ok:
            conn.close(); return False, reason
        cur.execute(
            "SELECT vehicle_id,status,compliance_status,insurance_exp,permit_exp,fitness_exp,puc_exp "
            "FROM vehicles WHERE tenant_id=:1 AND vendor_id=:2 "
            "AND UPPER(TRIM(reg_number))=UPPER(TRIM(:3)) "
            "AND (status IS NULL OR UPPER(status) NOT IN ('INACTIVE','SCRAPPED'))",
            (tenant_id, driver[2], vehicle_no.strip()),
        )
        vehicle_row = cur.fetchone()
        if not vehicle_row:
            conn.close(); return False, "vehicle-not-available"
        if str(vehicle_row[1] or "").strip().lower() in {"inactive", "scrapped", "suspended"}:
            conn.close(); return False, "vehicle-inactive"
        if str(vehicle_row[2] or "").strip().lower() in {"no", "failed", "expired", "invalid"}:
            conn.close(); return False, "vehicle-compliance-failed"
        for expiry in vehicle_row[3:7]:
            if expiry and hasattr(expiry, "date"):
                expiry = expiry.date()
            if expiry and expiry < datetime.now().date():
                conn.close(); return False, "vehicle-document-expired"
        from .routes.bookings import _add_to_trips_for_booking, _driver_reporting_time
        driver_name = str(driver[3] or "").strip()
        driver_mobile = str(driver[4] or "").strip()
        report_time = _driver_reporting_time(booking.get("pickup_time"))
        cur.execute(
            "UPDATE bookings SET driver_name=:1,driver_contact=:2,vehicle_no=:3,"
            "driver_reporting_time=:4,booking_status='2-Confirmed',"
            "status_reason='Booking Confirmed - Driver & Vehicle Allocated',"
            "step3_time=SYSDATE,done_by_driver=:5 WHERE booking_id=:6",
            (driver_name, driver_mobile, vehicle_no.strip(), report_time, user["user_id"], booking_id.strip()),
        )
        _add_to_trips_for_booking(conn, booking, driver_name, driver_mobile, vehicle_no.strip(), report_time)
        from . import notify
        from .sla_engine import emit_start, complete_for_entity
        completed_booking = dict(booking, driver_name=driver_name,
                                 driver_contact=driver_mobile,
                                 vehicle_no=vehicle_no.strip(),
                                 driver_reporting_time=report_time)
        complete_for_entity(conn, "BOOKING", booking_id, ("VENDOR_ALLOCATED",), "Driver accepted booking")
        emit_start(conn, "DRIVER_ALLOCATED", "BOOKING", booking_id,
                   context={"booking_type": booking.get("booking_type"),
                            "corporate_id": booking.get("company_id"),
                            "vehicle_type": booking.get("vehicle_type"),
                            "policy_category": "Booking"})
        emit_start(conn, "CUSTOMER_CONFIRMATION_REQUIRED", "BOOKING", booking_id,
                   context={"booking_type": booking.get("booking_type"),
                            "corporate_id": booking.get("company_id"),
                            "policy_category": "Booking"})
        notify.notify_step3(conn, user, completed_booking)
        cur.execute(
            "UPDATE driver_availability_sessions SET status='ALLOCATED',updated_at=SYSTIMESTAMP "
            "WHERE tenant_id=:1 AND driver_id=:2 AND status='IDEAL_NOW'",
            (tenant_id, driver[0]),
        )
        audit(conn, user, "BOOKING_ACCEPTED", booking_id, f"vendor_id={driver[2]}; driver_id={driver[0]}")
        conn.commit(); conn.close(); return True, "accepted"
    except Exception:
        conn.rollback(); conn.close(); raise
