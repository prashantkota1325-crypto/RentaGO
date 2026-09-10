"""Dashboard routes: role-based KPI views + Ops actions + SLA surface.

Sheets (module) -> route mapping (guarded via the roles matrix):
  CEO Dashboard      -> /dashboards/home
  Ops Dashboard      -> /dashboards/ops
  Sales Dashboard    -> /dashboards/sales
  Finance Dashboard  -> /dashboards/finance
  Vendor Dashboard   -> /dashboards/vendor
  Customer 360       -> /dashboards/customer360
  Investor MIS       -> /dashboards/investor
  Compliance         -> /dashboards/compliance
  Tracking Dashboard -> /dashboards/tracking
"""

from datetime import datetime
import json
import uuid
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth import current_user, module_level
from ..templating import templates
from ..db import get_connection
from ..scope import visible_booking_ids, can_view, OPERATOR_ROLES, CORPORATE_PORTAL_ROLES
from .. import sla
from ..gps import gps_report
from .. import notify
from ..audit import audit
from ..ids import next_driver_id, next_vehicle_id

router = APIRouter(prefix="/dashboards")

ACTIVE_TRIP_REASONS = (
    "Booking Confirmed - Driver & Vehicle Allocated",
    "Guest Trip Started - Awaiting Driver Confirmation",
    "Trip In Progress",
    "Guest Trip Ended - Awaiting Driver Confirmation",
)


def _guard(request, user, module):
    """Redirect to /home when the role has no access to the dashboard module."""
    if module_level(user, module) is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    return None


def _is_operator(user):
    return (user.get("role") or "").strip().lower() in OPERATOR_ROLES


@router.get("")
def dashboard_entry(request: Request):
    """Role-aware dashboard routing (mirrors the Home sheet navigation).

    Super Admin / HQ / CEO see a catalog of ALL dashboards instead of a
    single role-specific redirect.
    """
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    role = (user.get("role") or "").strip().lower()
    if role in ("super admin", "hq", "ceo"):
        return templates.TemplateResponse(
            "dashboards/index.html", {"request": request, "user": user}
        )
    target = {
        "operations": "/dashboards/ops", "vendor manager": "/dashboards/ops",
        "sales": "/dashboards/sales",
        "finance": "/dashboards/finance",
        "vendor": "/dashboards/vendor",
        "investor": "/dashboards/investor",
        "compliance": "/dashboards/compliance",
        "corporate admin": "/dashboards/customer360",
        "corporate booking user": "/dashboards/customer360",
        "corporate manager": "/dashboards/customer360",
        "corporate viewer": "/dashboards/customer360",
        "driver": "/trips",
    }.get(role)
    if not target:
        target = "/dashboards/home"
    return RedirectResponse(url=target, status_code=303)


@router.get("/home")
def home_dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    denied = _guard(request, user, "CEO Dashboard")
    if denied and not _is_operator(user):
        return denied
    conn = get_connection()
    cur = conn.cursor()
    kpi = {}
    cur.execute("SELECT COUNT(*) FROM bookings")
    kpi["total"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM bookings WHERE booking_status LIKE '1-%'")
    kpi["pending"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM bookings WHERE booking_status LIKE '2-%'")
    kpi["confirmed"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM bookings WHERE booking_status LIKE '3-%'")
    kpi["cancelled"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM bookings WHERE TRUNC(booking_date)=TRUNC(SYSDATE)")
    kpi["today"] = cur.fetchone()[0]
    cur.execute("SELECT NVL(SUM(final_amount),0) FROM invoices")
    kpi["revenue"] = float(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM trips WHERE trip_status='In Progress'")
    kpi["active_trips"] = cur.fetchone()[0]
    conn.close()
    return templates.TemplateResponse(
        "dashboards/ceo.html", {"request": request, "user": user, "kpi": kpi}
    )


@router.get("/ops")
def ops_dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    denied = _guard(request, user, "Ops Dashboard")
    if denied and not _is_operator(user):
        return denied
    conn = get_connection()
    cur = conn.cursor()
    alerts = sla.run_sweep(conn, force=False)

    cur.execute(
        "SELECT booking_id, booking_type, company_name, guest_name_1, "
        "pickup_date, pickup_time, vendor_name, driver_name, status_reason "
        "FROM bookings WHERE booking_status LIKE '1-%' ORDER BY booking_id DESC"
    )
    pending_alloc = [dict(zip(
        ("booking_id", "booking_type", "company", "guest", "pickup_date",
         "pickup_time", "vendor", "driver", "reason"), r))
        for r in cur.fetchall()[:50]]

    cur.execute(
        "SELECT booking_id, guest_name_1, driver_name, vehicle_no, "
        "pickup_date, pickup_time, location_sync FROM bookings "
        "WHERE status_reason IN (:1,:2,:3,:4) ORDER BY pickup_date",
        ACTIVE_TRIP_REASONS,
    )
    active = [dict(zip(
        ("booking_id", "guest", "driver", "vehicle", "pickup_date",
         "pickup_time", "sync"), r))
        for r in cur.fetchall()[:50]]

    cur.execute("SELECT COUNT(*) FROM bookings WHERE TRUNC(pickup_date)=TRUNC(SYSDATE)")
    today_pickups = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM bookings WHERE location_sync='RED FLAG'")
    red_flags = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN booking_status LIKE '2-%' THEN 1 ELSE 0 END), SUM(CASE WHEN booking_status LIKE '1-%' THEN 1 ELSE 0 END) FROM bookings WHERE TRUNC(pickup_date)=TRUNC(SYSDATE)")
    today_total, today_confirmed, today_pending = cur.fetchone()
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN vehicle_no IS NOT NULL THEN 1 ELSE 0 END), SUM(CASE WHEN driver_name IS NOT NULL THEN 1 ELSE 0 END) FROM bookings WHERE TRUNC(pickup_date)=TRUNC(SYSDATE)")
    vehicles_required, vehicles_allocated, drivers_confirmed = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM bookings WHERE status_reason='Trip In Progress'")
    trips_started = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM bookings WHERE status_reason='Trip Completed' AND TRUNC(pickup_date)=TRUNC(SYSDATE)")
    trips_completed = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM invoices WHERE payment_status NOT IN ('Payment Received','Closed - No Charges') OR payment_status IS NULL")
    payment_pending = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM trips WHERE guest_rating IS NOT NULL AND NVL(feedback_status,'Open') NOT IN ('Closed','Resolved')")
    customer_complaints = cur.fetchone()[0]
    cur.execute("SELECT SUM(CASE WHEN compliance_status='No' OR insurance_exp<SYSDATE OR permit_exp<SYSDATE OR fitness_exp<SYSDATE OR puc_exp<SYSDATE THEN 1 ELSE 0 END), SUM(CASE WHEN compliance_status='Pending' OR insurance_exp IS NULL OR permit_exp IS NULL OR fitness_exp IS NULL OR puc_exp IS NULL OR insurance_exp<=SYSDATE+30 OR permit_exp<=SYSDATE+30 OR fitness_exp<=SYSDATE+30 OR puc_exp<=SYSDATE+30 THEN 1 ELSE 0 END), COUNT(*) FROM vehicles WHERE status IS NULL OR UPPER(status)='ACTIVE'")
    vehicle_red, vehicle_amber, vehicle_total = cur.fetchone()
    cur.execute("SELECT SUM(CASE WHEN compliance_status='No' OR license_expiry<SYSDATE THEN 1 ELSE 0 END), SUM(CASE WHEN compliance_status='Pending' OR license_expiry IS NULL OR license_expiry<=SYSDATE+30 THEN 1 ELSE 0 END), COUNT(*) FROM drivers WHERE status IS NULL OR UPPER(status)='ACTIVE'")
    driver_red, driver_amber, driver_total = cur.fetchone()
    compliance_total = int(vehicle_total or 0) + int(driver_total or 0)
    compliance_red = int(vehicle_red or 0) + int(driver_red or 0)
    compliance_amber = min(compliance_total - compliance_red, int(vehicle_amber or 0) + int(driver_amber or 0))
    compliance_green = max(0, compliance_total - compliance_red - compliance_amber)
    conn.close()
    return templates.TemplateResponse(
        "dashboards/ops.html",
        {"request": request, "user": user, "alerts": alerts or [],
         "pending_alloc": pending_alloc, "active": active,
          "today_pickups": today_pickups, "red_flags": red_flags,
          "ops_kpi": {"bookings": today_total or 0, "confirmed": today_confirmed or 0, "pending": today_pending or 0,
                      "vehicles_required": vehicles_required or 0, "vehicles_allocated": vehicles_allocated or 0,
                      "drivers_required": today_total or 0, "drivers_confirmed": drivers_confirmed or 0,
                      "trips_started": trips_started or 0, "trips_completed": trips_completed or 0,
                      "payment_pending": payment_pending or 0, "customer_complaints": customer_complaints or 0,
                      "compliance_green": compliance_green, "compliance_amber": compliance_amber, "compliance_red": compliance_red}},
    )


@router.post("/sla-check")
def sla_check(request: Request):
    """Force the SLA sweep (Run SLA Check button on the Ops dashboard)."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    conn = get_connection()
    try:
        sla.run_sweep(conn, force=True)
    finally:
        conn.close()
    return RedirectResponse(url="/dashboards/ops?msg=sla-checked", status_code=303)


@router.get("/sales")
def sales_dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    denied = _guard(request, user, "Sales Dashboard")
    if denied and not _is_operator(user):
        return denied
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT NVL(stage,'-'), COUNT(*), NVL(SUM(est_monthly_rev),0), "
        "NVL(SUM(weighted_value),0) FROM leads GROUP BY stage ORDER BY stage"
    )
    stages = [{"stage": r[0], "count": r[1],
               "est_rev": float(r[2] or 0), "weighted": float(r[3] or 0)}
              for r in cur.fetchall()]
    cur.execute(
        "SELECT lead_id, company, city, contact, sales_owner, stage, "
        "probability, est_monthly_rev, next_followup FROM leads "
        "ORDER BY NVL(next_followup, TO_DATE('9999-12-31','YYYY-MM-DD')) "
        "FETCH FIRST 30 ROWS ONLY"
    )
    leads = [dict(zip(
        ("lead_id", "company", "city", "contact", "owner", "stage",
         "probability", "est_rev", "next_followup"), r))
        for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse(
        "dashboards/sales.html",
        {"request": request, "user": user, "stages": stages, "leads": leads},
    )


@router.get("/finance")
def finance_dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    denied = _guard(request, user, "Finance Dashboard")
    if denied and not _is_operator(user):
        return denied
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT NVL(invoice_status,'-'), COUNT(*) FROM invoices "
        "GROUP BY invoice_status ORDER BY invoice_status"
    )
    inv_status = [{"status": r[0], "count": r[1]} for r in cur.fetchall()]
    cur.execute(
        "SELECT NVL(payment_status,'-'), COUNT(*) FROM invoices "
        "GROUP BY payment_status ORDER BY payment_status"
    )
    pay_status = [{"status": r[0], "count": r[1]} for r in cur.fetchall()]
    cur.execute(
        "SELECT NVL(SUM(final_amount),0) FROM invoices "
        "WHERE invoice_status IN ('Final Invoice','Cancellation Invoice') "
        "AND payment_status NOT IN ('Payment Received','Closed - No Charges')"
    )
    receivable = float(cur.fetchone()[0] or 0)
    cur.execute(
        "SELECT pay_type, NVL(SUM(amount),0), COUNT(*) FROM payments "
        "GROUP BY pay_type ORDER BY pay_type"
    )
    pay_totals = [{"type": r[0], "total": float(r[1] or 0), "count": int(r[2])}
                  for r in cur.fetchall()]
    pay_count = sum(p["count"] for p in pay_totals)
    cur.execute(
        "SELECT invoice_id, booking_id, guest_name, company_name, "
        "vendor_expense_deadline, payment_status FROM invoices "
        "WHERE vendor_expense_deadline < SYSDATE "
        "AND payment_status = 'Pending Trip Expenses' "
        "ORDER BY vendor_expense_deadline FETCH FIRST 20 ROWS ONLY"
    )
    overdue = [dict(zip(
        ("invoice_id", "booking_id", "guest", "company", "deadline",
         "payment_status"), r))
        for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse(
        "dashboards/finance.html",
        {"request": request, "user": user, "inv_status": inv_status,
         "pay_status": pay_status, "receivable": receivable,
         "pay_totals": pay_totals, "pay_count": pay_count, "overdue": overdue},
    )


@router.get("/vendor")
def vendor_dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    denied = _guard(request, user, "Vendor Dashboard")
    if denied and not _is_operator(user):
        return denied
    conn = get_connection()
    cur = conn.cursor()
    vendor_rows = []
    if (user.get("role") or "").strip().lower() == "vendor":
        visible = visible_booking_ids(user, cur)
        cur.execute(
            "SELECT booking_id, guest_name_1, company_name, pickup_date, pickup_time, pickup_address, pickup_1, pickup_2, pickup_3, pickup_4, "
            "drop_address, planned_route_json, booking_status, status_reason FROM bookings ORDER BY booking_id DESC"
        )
        rows = [r for r in cur.fetchall()
                if can_view(visible, str(r[0]))][:100]
        bookings = []
        for r in rows:
            try:
                payload = r[11].read() if hasattr(r[11], "read") else (r[11] or "{}")
                stops = json.loads(payload).get("stops", [])
            except (TypeError, ValueError):
                stops = []
            bookings.append({"booking_id": r[0], "guest": r[1], "company": r[2], "pickup_date": r[3], "pickup_time": r[4],
                             "pickup_address": r[5], "stops": stops, "drop_address": r[10],
                             "status": r[12], "reason": r[13]})
        kpi = {"bookings": len(bookings)}
    else:
        cur.execute(
            "SELECT NVL(vendor_name,'(unassigned)'), COUNT(*), "
            "SUM(CASE WHEN booking_status LIKE '2-%' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN booking_status LIKE '3-%' THEN 1 ELSE 0 END) "
            "FROM bookings GROUP BY vendor_name ORDER BY 2 DESC"
        )
        for r in cur.fetchall()[:50]:
            vendor_rows.append({"vendor": r[0], "total": r[1],
                                "confirmed": r[2] or 0, "cancelled": r[3] or 0})
        bookings = []
        kpi = {"vendors": len(vendor_rows)}
    conn.close()
    return templates.TemplateResponse(
        "dashboards/vendor.html",
        {"request": request, "user": user, "vendor_rows": vendor_rows,
         "bookings": bookings, "kpi": kpi},
    )


@router.get("/customer360")
def customer360_dashboard(request: Request, company: str = ""):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    denied = _guard(request, user, "Customer 360")
    if denied and not _is_operator(user):
        return denied
    conn = get_connection()
    cur = conn.cursor()
    role = (user.get("role") or "").strip().lower()
    is_corporate = role in CORPORATE_PORTAL_ROLES
    if is_corporate:
        # Never trust the query-string company for an external portal.
        company = (user.get("company") or user.get("company_name") or "").strip()
        companies = [company] if company else []
    else:
        cur.execute(
            "SELECT company_name FROM companies WHERE company_name IS NOT NULL "
            "AND (status IS NULL OR UPPER(status)='ACTIVE') "
            "ORDER BY company_name FETCH FIRST 200 ROWS ONLY"
        )
        companies = [r[0] for r in cur.fetchall()]
    if not company and companies:
        company = companies[0]

    info, stats, recent, invoices = None, {}, [], []
    if company:
        cur.execute(
            "SELECT company_id, company_name, industry, city, state, credit_limit, "
            "credit_days, account_manager, status FROM companies "
            "WHERE UPPER(TRIM(company_name))=UPPER(TRIM(:1))",
            (company,),
        )
        row = cur.fetchone()
        if row:
            info = dict(zip(
                ("company_id", "name", "industry", "city", "state", "credit_limit",
                 "credit_days", "account_manager", "status"), row))
        cur.execute(
            "SELECT COUNT(*), SUM(CASE WHEN booking_status LIKE '1-%' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN booking_status LIKE '2-%' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN booking_status LIKE '3-%' THEN 1 ELSE 0 END) "
            "FROM bookings WHERE UPPER(TRIM(company_name))=UPPER(TRIM(:1))",
            (company,),
        )
        s = cur.fetchone()
        stats = {"total": s[0] or 0, "pending": s[1] or 0,
                 "confirmed": s[2] or 0, "cancelled": s[3] or 0}
        cur.execute(
            "SELECT booking_id, guest_name_1, pickup_date, booking_status "
            "FROM bookings WHERE UPPER(TRIM(company_name))=UPPER(TRIM(:1)) "
            "ORDER BY booking_id DESC FETCH FIRST 15 ROWS ONLY",
            (company,),
        )
        recent = [dict(zip(("booking_id", "guest", "pickup_date", "status"), r))
                  for r in cur.fetchall()]
        cur.execute(
            "SELECT invoice_id, booking_id, "
            "(SELECT MIN(t.trip_id) FROM trips t WHERE t.booking_id=invoices.booking_id), "
            "invoice_status, payment_status, "
            "final_amount FROM invoices WHERE UPPER(TRIM(company_name))=UPPER(TRIM(:1)) "
            "ORDER BY invoice_id DESC FETCH FIRST 15 ROWS ONLY",
            (company,),
        )
        invoices = [dict(zip(
             ("invoice_id", "booking_id", "trip_id", "invoice_status", "payment_status",
              "final_amount"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse(
        "dashboards/customer360.html",
        {"request": request, "user": user, "companies": companies,
         "selected": company, "info": info, "stats": stats,
         "recent": recent, "invoices": invoices},
    )


@router.get("/investor")
def investor_dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    denied = _guard(request, user, "Investor MIS")
    if denied and not _is_operator(user):
        return denied
    conn = get_connection()
    cur = conn.cursor()
    kpi = {}
    cur.execute("SELECT COUNT(*) FROM bookings")
    kpi["bookings"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM companies")
    kpi["companies"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM vendors")
    kpi["vendors"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM drivers")
    kpi["drivers"] = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM trips WHERE trip_status='Trip Completed'")
    kpi["completed_trips"] = cur.fetchone()[0]
    cur.execute("SELECT NVL(SUM(final_amount),0), NVL(AVG(final_amount),0) "
                "FROM invoices WHERE final_amount > 0")
    rev = cur.fetchone()
    kpi["revenue"] = float(rev[0] or 0)
    kpi["avg_invoice"] = float(rev[1] or 0)
    cur.execute(
        "SELECT COUNT(*) FROM bookings WHERE booking_status LIKE '3-%'"
    )
    kpi["cancelled"] = cur.fetchone()[0]
    conn.close()
    return templates.TemplateResponse(
        "dashboards/investor.html",
        {"request": request, "user": user, "kpi": kpi},
    )


@router.get("/compliance")
def compliance_dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    denied = _guard(request, user, "Compliance")
    if denied and not _is_operator(user):
        return denied
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT NVL(status,'-'), COUNT(*) FROM users GROUP BY status ORDER BY status"
    )
    user_status = [{"status": r[0], "count": r[1]} for r in cur.fetchall()]
    cur.execute(
        "SELECT audit_date, audit_time, user_id, action, record, notes "
        "FROM audit_log ORDER BY log_seq DESC FETCH FIRST 30 ROWS ONLY"
    )
    audit_rows = [dict(zip(
        ("date", "time", "user_id", "action", "record", "notes"), r))
        for r in cur.fetchall()]
    cur.execute(
        "SELECT log_id, user_id, user_name, role, login_dt, logout_dt, "
        "hours_worked FROM login_log ORDER BY login_dt DESC "
        "FETCH FIRST 30 ROWS ONLY"
    )
    login_rows = [dict(zip(
        ("log_id", "user_id", "user_name", "role", "login_dt", "logout_dt",
         "hours_worked"), r)) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) FROM bookings WHERE location_sync='RED FLAG'")
    red_flags = cur.fetchone()[0]
    conn.close()
    return templates.TemplateResponse(
        "dashboards/compliance.html",
        {"request": request, "user": user, "user_status": user_status,
         "audit_rows": audit_rows, "login_rows": login_rows,
         "red_flags": red_flags},
    )


@router.get("/tracking")
def tracking_dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    denied = _guard(request, user, "Tracking Dashboard")
    if denied and not _is_operator(user):
        return denied
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT booking_id, booking_type, company_name, guest_name_1, "
        "guest_contact, pickup_date, pickup_time, pickup_address, drop_address, "
        "driver_name, driver_contact, vehicle_no, booking_status, status_reason, "
        "driver_live_location, guest_live_location, driver_gps, guest_gps, "
        "track_token, location_sync "
        "FROM bookings WHERE status_reason IN (:1,:2,:3,:4) "
        "OR (booking_status LIKE '1-%' AND TRUNC(pickup_date)=TRUNC(SYSDATE)) "
        "ORDER BY pickup_date, pickup_time",
        ACTIVE_TRIP_REASONS,
    )
    rows = cur.fetchall()
    visible = visible_booking_ids(user, cur)
    conn.close()
    trips = []
    for r in rows:
        if not can_view(visible, str(r[0])):
            continue
        t = dict(zip(
            ("booking_id", "booking_type", "company", "guest", "guest_contact",
             "pickup_date", "pickup_time", "pickup", "drop", "driver",
             "driver_contact", "vehicle", "status", "reason", "driver_link",
             "guest_link", "driver_gps", "guest_gps", "track_token", "sync"), r))
        base = str(request.base_url).rstrip("/")
        legacy_driver_link = t.get("driver_link") or ""
        legacy_guest_link = t.get("guest_link") or ""
        t["driver_link"] = legacy_driver_link if "google.com/maps" in legacy_driver_link else ""
        t["guest_link"] = legacy_guest_link if "google.com/maps" in legacy_guest_link else ""
        if t.get("driver_gps"):
            t["driver_link"] = "https://www.google.com/maps?q=" + str(t["driver_gps"])
        elif t.get("track_token"):
            t["driver_tracking_link"] = f"{base}/track/{t['booking_id']}/driver/{t['track_token']}"
        if t.get("guest_gps"):
            t["guest_link"] = "https://www.google.com/maps?q=" + str(t["guest_gps"])
        elif t.get("track_token"):
            t["guest_tracking_link"] = f"{base}/track/{t['booking_id']}/guest/{t['track_token']}"
        # Route link (VBA TrackTrip): Google Maps pickup -> drop
        t["route"] = "https://www.google.com/maps/dir/?api=1&" + urlencode({
            "origin": (t.get("pickup") or "").strip(),
            "destination": (t.get("drop") or "").strip(),
            "travelmode": "driving",
        })
        # Live distance when both location links exist (VBA CheckLocationSync)
        if t["driver_link"] and t["guest_link"]:
            report = gps_report(t["driver_link"], t["guest_link"], t["sync"])
            if report["distance_m"] is not None:
                t["distance_m"] = report["distance_m"]
        trips.append(t)
    role = (user.get("role") or "").strip().lower()
    can_track = role in ("super admin", "superadmin", "hq", "ceo",
                         "operations", "vendor manager")
    return templates.TemplateResponse(
        "dashboards/tracking.html",
        {"request": request, "user": user, "trips": trips,
         "can_track": can_track,
         "checked": request.query_params.get("checked", ""),
         "red": request.query_params.get("red", "")},
    )


@router.post("/tracking/auto-check")
def tracking_auto_check(request: Request):
    """Bulk location-sync sweep (VBA AutoCheckLocationSync).

    Re-checks every 'Trip In Progress' booking that has both live-location
    links, updates the sync status and queues RED FLAG alerts for trips whose
     driver/guest positions differ by more than 100 m.
    """
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _is_operator(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM bookings WHERE status_reason='Trip In Progress' "
        "AND driver_live_location IS NOT NULL "
        "AND guest_live_location IS NOT NULL"
    )
    cols = [d[0].lower() for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    visible = visible_booking_ids(user, cur)
    checked = red = 0
    for b in rows:
        if not can_view(visible, str(b.get("booking_id"))):
            continue
        driver_link = (b.get("driver_live_location") or "").strip()
        guest_link = (b.get("guest_live_location") or "").strip()
        report = gps_report(driver_link, guest_link, b.get("location_sync") or "")
        if report["distance_m"] is None:
            continue
        checked += 1
        cur.execute("UPDATE bookings SET location_sync=:1 WHERE booking_id=:2",
                    (report["status"], b.get("booking_id")))
        if report["status"] == "RED FLAG":
            red += 1
            notify.notify_red_flag(
                conn, user,
                dict(b, driver_live_location=driver_link,
                     guest_live_location=guest_link), report)
    audit(conn, user, "Auto Location Sync Check", "Tracking",
          f"checked={checked}; red flags={red}")
    conn.commit()
    conn.close()
    return RedirectResponse(
        url=f"/dashboards/tracking?checked={checked}&red={red}",
        status_code=303)
@router.get('/sla')
def sla_dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse('/auth/login', status_code=303)
    role = (user.get('role') or '').strip().lower()
    if module_level(user, "SLA Dashboard") is None:
        return RedirectResponse('/home?msg=not-allowed', status_code=303)
    # Simple SLA counts - no complex datetime math
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM bookings WHERE vendor_name IS NULL AND booking_status LIKE '1-%'")
    vendor_no_alloc = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM bookings WHERE vendor_name IS NOT NULL AND driver_name IS NULL AND booking_status LIKE '1-%'")
    vendor_without_driver = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM bookings WHERE request_received_time IS NOT NULL AND ack_sent_time IS NULL")
    no_ack = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT NVL(status,'ACTIVE'), COUNT(*) FROM sla_instances GROUP BY NVL(status,'ACTIVE')")
    sla_instance_counts = {str(r[0]): int(r[1] or 0) for r in cur.fetchall()}
    cur.execute("SELECT COUNT(*) FROM sla_escalations WHERE status IN ('Open','Acknowledged')")
    open_escalations = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM sla_exceptions WHERE status='Pending'")
    pending_exceptions = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM notifications WHERE status IN ('Retry','Failed')")
    notification_failures = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM sla_instances WHERE department='Compliance' AND status IN ('ACTIVE','AT_RISK','BREACHED')")
    compliance_open = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT department, vendor_minutes, driver_warning_minutes, driver_reassign_minutes, acknowledgement_minutes, updated_by, updated_dt FROM sla_settings ORDER BY department")
    sla_settings = [dict(zip(("department", "vendor_minutes", "driver_warning_minutes", "driver_reassign_minutes", "acknowledgement_minutes", "updated_by", "updated_dt"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse(
        "dashboards/sla_dashboard.html",
        {"request": request, "user": user,
         "vendor_no_alloc": vendor_no_alloc,
         "vendor_without_driver": vendor_without_driver,
          "no_ack": no_ack, "sla_settings": sla_settings,
          "open_escalations": open_escalations, "pending_exceptions": pending_exceptions,
          "notification_failures": notification_failures, "compliance_open": compliance_open,
          "sla_instance_counts": sla_instance_counts},
    )


def _vendor_id_for_user(cur, user):
    cur.execute("SELECT vendor_id FROM vendors WHERE UPPER(TRIM(vendor_name))=UPPER(TRIM(:1))", (user.get("company_name") or user.get("company") or "",))
    row = cur.fetchone()
    return row[0] if row else None


@router.get("/vendor/resources")
def vendor_resources(request: Request, edit_driver: str = "", edit_vehicle: str = ""):
    user = current_user(request)
    if not user or (user.get("role") or "").strip().lower() not in {"vendor", "vendor admin", "vendor operations"}:
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor(); vendor_id = _vendor_id_for_user(cur, user)
    if not vendor_id:
        conn.close(); return RedirectResponse("/dashboards/vendor?msg=vendor-not-found", status_code=303)
    cur.execute("SELECT driver_id,driver_name,mobile,license_no,license_expiry,languages_known,compliance_status,status FROM drivers WHERE vendor_id=:1 ORDER BY driver_name", (vendor_id,))
    drivers = [dict(zip(("id","name","mobile","license","expiry","languages","compliance","status"), r)) for r in cur.fetchall()]
    cur.execute("SELECT vehicle_id,reg_number,make,model,category,insurance_exp,permit_exp,fitness_exp,puc_exp,compliance_status,status FROM vehicles WHERE vendor_id=:1 ORDER BY reg_number", (vendor_id,))
    vehicles = [dict(zip(("id","reg","make","model","category","insurance","permit","fitness","puc","compliance","status"), r)) for r in cur.fetchall()]
    driver_edit = next((d for d in drivers if str(d["id"]) == edit_driver), {})
    vehicle_edit = next((v for v in vehicles if str(v["id"]) == edit_vehicle), {})
    conn.close()
    return templates.TemplateResponse("dashboards/vendor_resources.html", {"request": request, "user": user, "drivers": drivers, "vehicles": vehicles, "vendor_id": vendor_id, "driver_edit": driver_edit, "vehicle_edit": vehicle_edit})


@router.get("/vendor/billing")
def vendor_billing(request: Request):
    user = current_user(request)
    if not user or (user.get("role") or "").strip().lower() not in {"vendor", "vendor admin", "vendor operations"}:
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor(); vendor_id = _vendor_id_for_user(cur, user)
    if not vendor_id:
        conn.close(); return RedirectResponse("/dashboards/vendor?msg=vendor-not-found", status_code=303)
    cur.execute("SELECT vendor_invoice_id,invoice_number,booking_id,invoice_date,toll,parking,extra_kms,extra_hours,other_expenses,total_amount,status,notes FROM vendor_invoices WHERE vendor_id=:1 AND tenant_id=:2 ORDER BY invoice_date DESC", (vendor_id, user.get("tenant_id") or "TEN-RENTA-GO"))
    invoices = [dict(zip(("id","number","booking_id","date","toll","parking","extra_kms","extra_hours","other","total","status","notes"), r)) for r in cur.fetchall()]
    cur.execute("SELECT booking_id,pickup_address,drop_address FROM bookings WHERE vendor_id=:1 OR UPPER(TRIM(vendor_name))=UPPER(TRIM(:2)) ORDER BY pickup_date DESC", (vendor_id, user.get("company_name") or user.get("company") or ""))
    bookings = [{"id": r[0], "pickup": r[1], "drop": r[2]} for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("dashboards/vendor_billing.html", {"request": request, "user": user, "invoices": invoices, "bookings": bookings})


@router.get("/vendor-invoices")
def vendor_invoice_review(request: Request):
    user = current_user(request)
    if not user or not _is_operator(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "SELECT vi.invoice_number,v.vendor_name,vi.booking_id,vi.invoice_date,vi.total_amount,vi.status,vi.notes "
        "FROM vendor_invoices vi LEFT JOIN vendors v ON v.vendor_id=vi.vendor_id ORDER BY vi.invoice_date DESC")
    invoices = [dict(zip(("number", "vendor", "booking_id", "date", "total", "status", "notes"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("dashboards/vendor_invoice_review.html", {"request": request, "user": user, "invoices": invoices})


@router.get("/vendor/reports")
def vendor_reports(request: Request, start: str = "", end: str = "", period: str = "", vendor_filter: str = "", company_filter: str = ""):
    user = current_user(request)
    role = (user.get("role") or "").strip().lower()
    is_vendor = role in {"vendor", "vendor admin", "vendor operations", "vendor viewer"}
    external_roles = {"vendor", "vendor admin", "vendor operations", "vendor viewer", "guest", "driver", "corporate admin", "corporate booking user", "corporate manager", "corporate viewer"}
    if not user or (not is_vendor and ((user.get("role") or "").strip().lower() in external_roles or user.get("organization_type", "").strip().upper() != "RENTAGO")):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    vendor_id = _vendor_id_for_user(cur, user) if is_vendor else vendor_filter
    vendor_name = user.get("company_name") or user.get("company") or ""
    params = []; ownership = ""
    if vendor_id:
        if is_vendor:
            cur.execute("SELECT vendor_name FROM vendors WHERE vendor_id=:1", (vendor_id,)); row = cur.fetchone(); vendor_name = row[0] if row else vendor_name
        params.extend([vendor_id, vendor_name]); ownership = " AND (vendor_id=:1 OR UPPER(TRIM(vendor_name))=UPPER(TRIM(:2)))"
    if company_filter:
        params.append(company_filter); ownership += f" AND UPPER(TRIM(company_name))=UPPER(TRIM(:{len(params)}))"
    date_where = ""
    if period == "today":
        date_where = " AND pickup_date>=TRUNC(SYSDATE) AND pickup_date<TRUNC(SYSDATE)+1"
    elif period == "tomorrow":
        date_where = " AND pickup_date>=TRUNC(SYSDATE)+1 AND pickup_date<TRUNC(SYSDATE)+2"
    elif period == "next7":
        date_where = " AND pickup_date>=TRUNC(SYSDATE)+2 AND pickup_date<TRUNC(SYSDATE)+7"
    elif period == "not_completed":
        date_where = " AND (pickup_date>=TRUNC(SYSDATE) OR status_reason IN ('Guest Trip Started - Awaiting Driver Confirmation','Trip In Progress','Guest Trip Ended - Awaiting Driver Confirmation')) AND (status_reason IS NULL OR status_reason<>'Trip Completed') AND booking_status NOT LIKE '3-%'"
    else:
        if start.strip(): params.append(start.strip()); date_where += f" AND pickup_date>=TO_DATE(:{len(params)},'YYYY-MM-DD')"
        if end.strip(): date_where += f" AND pickup_date<TO_DATE(:{len(params)+1},'YYYY-MM-DD')+1"; params.append(end.strip())
    cur.execute("SELECT booking_id,company_name,guest_name_1,vendor_name,driver_name,driver_contact,pickup_address,drop_address,booking_status FROM bookings WHERE 1=1" + ownership + date_where + " ORDER BY booking_date DESC", params)
    bookings = [dict(zip(("id","company","guest","vendor","driver","driver_contact","pickup","drop","status"), r)) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) FROM vendor_invoices WHERE vendor_id=:1 AND tenant_id=:2", (vendor_id, user.get("tenant_id") or "TEN-RENTA-GO")); bills = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM bookings WHERE 1=1" + ownership + date_where + " AND status_reason='Trip Completed'", params); completed = int(cur.fetchone()[0] or 0)
    conn.close()
    summary={"bookings":len(bookings),"confirmed":sum(1 for b in bookings if str(b["status"] or "").startswith("2-")),"completed":completed,"bills":bills}
    if is_vendor:
        vendor_options, company_options = [], []
    else:
        cur.execute("SELECT vendor_id,vendor_name FROM vendors WHERE vendor_name IS NOT NULL ORDER BY vendor_name"); vendor_options = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT company_name FROM bookings WHERE company_name IS NOT NULL ORDER BY company_name"); company_options = [r[0] for r in cur.fetchall()]
    return templates.TemplateResponse("dashboards/vendor_reports.html", {"request": request, "user": user, "bookings": bookings, "summary": summary, "start": start, "end": end, "period": period, "is_vendor": is_vendor, "vendor_options": vendor_options, "company_options": company_options, "vendor_filter": vendor_filter, "company_filter": company_filter})


@router.post("/vendor/billing/save")
def vendor_billing_save(request: Request, booking_id: str = Form(...), vendor_invoice_id: str = Form(""), invoice_number: str = Form(""), toll: str = Form("0"), parking: str = Form("0"), extra_kms: str = Form("0"), extra_hours: str = Form("0"), other_expenses: str = Form("0"), notes: str = Form("")):
    user = current_user(request)
    if not user or (user.get("role") or "").strip().lower() not in {"vendor", "vendor admin", "vendor operations"}:
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor(); vendor_id = _vendor_id_for_user(cur, user); tenant_id = user.get("tenant_id") or "TEN-RENTA-GO"
    if not vendor_id: conn.close(); return RedirectResponse("/dashboards/vendor/billing?msg=vendor-not-found", status_code=303)
    def money(v):
        try: return max(0.0, float(v or 0))
        except ValueError: return 0.0
    values = (money(toll), money(parking), money(extra_kms), money(extra_hours), money(other_expenses))
    total = sum(values)
    if vendor_invoice_id:
        cur.execute("UPDATE vendor_invoices SET toll=:1,parking=:2,extra_kms=:3,extra_hours=:4,other_expenses=:5,total_amount=:6,notes=:7,updated_at=SYSTIMESTAMP WHERE vendor_invoice_id=:8 AND vendor_id=:9 AND tenant_id=:10 AND status='Draft'", values + (total, notes.strip()[:1000], vendor_invoice_id, vendor_id, tenant_id))
    else:
        invoice_id = "VIN-" + uuid.uuid4().hex[:20]
        number = invoice_number.strip()[:80] or f"VI-{datetime.now():%Y%m%d%H%M%S}"
        cur.execute("SELECT COUNT(1) FROM vendor_invoices WHERE tenant_id=:1 AND vendor_id=:2 AND invoice_number=:3", (tenant_id, vendor_id, number))
        if int(cur.fetchone()[0] or 0):
            conn.close(); return RedirectResponse("/dashboards/vendor/billing?msg=invoice-number-exists", status_code=303)
        cur.execute("INSERT INTO vendor_invoices (vendor_invoice_id,tenant_id,vendor_id,booking_id,invoice_number,toll,parking,extra_kms,extra_hours,other_expenses,total_amount,status,notes,created_by) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,'Draft',:12,:13)", (invoice_id,tenant_id,vendor_id,booking_id,number)+values+(total,notes.strip()[:1000],user["user_id"]))
    audit(conn,user,"VENDOR_INVOICE_UPDATED",vendor_id,f"booking={booking_id}; total={total}"); conn.commit(); conn.close()
    return RedirectResponse("/dashboards/vendor/billing", status_code=303)


@router.get("/vendor/billing/{vendor_invoice_id}")
def vendor_billing_detail(request: Request, vendor_invoice_id: str):
    user = current_user(request)
    if not user or (user.get("role") or "").strip().lower() not in {"vendor", "vendor admin", "vendor operations"}:
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor(); vendor_id = _vendor_id_for_user(cur, user)
    cur.execute("SELECT vi.invoice_number,vi.booking_id,vi.invoice_date,vi.toll,vi.parking,vi.extra_kms,vi.extra_hours,vi.other_expenses,vi.total_amount,vi.status,vi.notes,v.vendor_name,b.company_name,b.guest_name_1,b.pickup_address,b.drop_address,b.vehicle_type,b.package_type,b.pickup_date,b.drop_date,t.actual_start_dt,t.actual_end_dt,i.trip_end_date,i.vendor_expense_deadline,i.final_bill_deadline,i.cancellation_reason,i.cancellation_policy FROM vendor_invoices vi JOIN vendors v ON v.vendor_id=vi.vendor_id LEFT JOIN bookings b ON b.booking_id=vi.booking_id LEFT JOIN trips t ON t.booking_id=vi.booking_id LEFT JOIN invoices i ON i.booking_id=vi.booking_id WHERE vi.vendor_invoice_id=:1 AND vi.vendor_id=:2 AND vi.tenant_id=:3", (vendor_invoice_id, vendor_id, user.get("tenant_id") or "TEN-RENTA-GO"))
    row = cur.fetchone(); conn.close()
    if not row:
        return RedirectResponse("/dashboards/vendor/billing?msg=not-found", status_code=303)
    invoice = dict(zip(("number","booking_id","date","toll","parking","extra_kms","extra_hours","other","total","status","notes","vendor","company","guest","pickup","drop","vehicle","package","trip_date","drop_date","actual_start","actual_end","trip_end","expense_deadline","final_bill_deadline","cancellation_reason","cancellation_policy"), row))
    return templates.TemplateResponse("dashboards/vendor_invoice_detail.html", {"request": request, "user": user, "invoice": invoice})


@router.post("/vendor/resources/driver")
def vendor_save_driver(request: Request, driver_id: str = Form(""), driver_name: str = Form(...), mobile: str = Form(""), license_no: str = Form(""), license_expiry: str = Form(""), languages_known: str = Form(""), compliance_status: str = Form("Pending")):
    user = current_user(request)
    if not user or (user.get("role") or "").strip().lower() not in {"vendor", "vendor admin", "vendor operations"}:
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor(); vendor_id = _vendor_id_for_user(cur, user)
    if not vendor_id: conn.close(); return RedirectResponse("/dashboards/vendor/resources?msg=vendor-not-found", status_code=303)
    expiry = datetime.strptime(license_expiry, "%Y-%m-%d").date() if license_expiry.strip() else None
    if driver_id:
        cur.execute("UPDATE drivers SET driver_name=:1,mobile=:2,license_no=:3,license_expiry=:4,languages_known=:5,compliance_status=:6 WHERE driver_id=:7 AND vendor_id=:8", (driver_name.strip(),mobile.strip(),license_no.strip(),expiry,languages_known.strip(),compliance_status,driver_id,vendor_id))
    else:
        cur.execute("INSERT INTO drivers (driver_id,tenant_id,vendor_id,driver_name,mobile,license_no,license_expiry,languages_known,compliance_status,status) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,'Active')", (next_driver_id(cur),user.get("tenant_id") or "TEN-RENTA-GO",vendor_id,driver_name.strip(),mobile.strip(),license_no.strip(),expiry,languages_known.strip(),compliance_status))
    audit(conn,user,"VENDOR_DRIVER_UPDATED",vendor_id,f"driver={driver_name}"); conn.commit(); conn.close()
    return RedirectResponse("/dashboards/vendor/resources", status_code=303)


@router.post("/vendor/resources/vehicle")
def vendor_save_vehicle(request: Request, vehicle_id: str = Form(""), reg_number: str = Form(...), make: str = Form(""), model: str = Form(""), category: str = Form(""), insurance_exp: str = Form(""), permit_exp: str = Form(""), fitness_exp: str = Form(""), puc_exp: str = Form(""), compliance_status: str = Form("Pending")):
    user = current_user(request)
    if not user or (user.get("role") or "").strip().lower() not in {"vendor", "vendor admin", "vendor operations"}:
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor(); vendor_id = _vendor_id_for_user(cur, user)
    if not vendor_id: conn.close(); return RedirectResponse("/dashboards/vendor/resources?msg=vendor-not-found", status_code=303)
    def d(v): return datetime.strptime(v, "%Y-%m-%d").date() if v.strip() else None
    values=(reg_number.strip(),make.strip(),model.strip(),category.strip(),d(insurance_exp),d(permit_exp),d(fitness_exp),d(puc_exp),compliance_status)
    if vehicle_id:
        cur.execute("UPDATE vehicles SET reg_number=:1,make=:2,model=:3,category=:4,insurance_exp=:5,permit_exp=:6,fitness_exp=:7,puc_exp=:8,compliance_status=:9 WHERE vehicle_id=:10 AND vendor_id=:11", values+(vehicle_id,vendor_id))
    else:
        cur.execute("INSERT INTO vehicles (vehicle_id,tenant_id,vendor_id,reg_number,make,model,category,insurance_exp,permit_exp,fitness_exp,puc_exp,compliance_status,status) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,'Active')", (next_vehicle_id(cur),user.get("tenant_id") or "TEN-RENTA-GO",vendor_id)+values)
    audit(conn,user,"VENDOR_VEHICLE_UPDATED",vendor_id,f"vehicle={reg_number}"); conn.commit(); conn.close()
    return RedirectResponse("/dashboards/vendor/resources", status_code=303)


@router.post('/sla/settings')
async def save_sla_settings(request: Request):
    user = current_user(request)
    if not user or module_level(user, "SLA Dashboard") != "F":
        return RedirectResponse('/home?msg=not-allowed', status_code=303)
    form = await request.form()
    conn = get_connection()
    cur = conn.cursor()
    for department in form.getlist("department"):
        try:
            values = [int(form.get(f"{field}_{department}") or 0) for field in ("vendor", "warning", "reassign", "ack")]
            if any(v <= 0 for v in values):
                raise ValueError
        except ValueError:
            conn.close()
            return RedirectResponse('/dashboards/sla?msg=invalid-sla', status_code=303)
        cur.execute(
            "UPDATE sla_settings SET vendor_minutes=:1, driver_warning_minutes=:2, "
            "driver_reassign_minutes=:3, acknowledgement_minutes=:4, updated_by=:5, updated_dt=SYSDATE "
            "WHERE department=:6", (*values, user["user_id"], department))
    conn.commit()
    conn.close()
    return RedirectResponse('/dashboards/sla?msg=sla-saved', status_code=303)
