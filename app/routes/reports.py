"""Reports module (port of the VBA Reports sheet + GenerateReport macro).

A filtered bookings report joined with the first trip and first invoice per
booking. Filters: booking type, company/guest, and pickup-date range
(DD-MM-YYYY). Access is matrix-driven via the "Reports" sheet
(Super Admin / HQ = F in the imported roles matrix).
"""

import csv
import io
from datetime import date, datetime
from datetime import timedelta

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from ..auth import current_user, module_level
from ..templating import templates
from ..db import get_connection
from ..audit import audit
from ..scope import visible_booking_ids, can_view
from ..auth import FEEDBACK_EXTERNAL_ROLES

router = APIRouter(prefix="/reports")

MAX_ROWS = 500


@router.get("/vendor-compliance")
def vendor_compliance(request: Request, vendor_id: str = ""):
    user = current_user(request)
    if not user or module_level(user, "Reports") is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    is_vendor = (user.get("role") or "").strip().lower() in {"vendor", "vendor admin", "vendor operations", "vendor viewer"}
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT vendor_id, vendor_name FROM vendors WHERE (status IS NULL OR UPPER(status)='ACTIVE') ORDER BY vendor_name")
    vendors = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    if is_vendor:
        cur.execute("SELECT vendor_id FROM vendors WHERE UPPER(TRIM(vendor_name))=UPPER(TRIM(:1))", (user.get("company_name") or user.get("company") or "",))
        vendor_row = cur.fetchone()
        vendor_id = vendor_row[0] if vendor_row else ""
    vehicles, drivers = [], []
    today = date.today()
    due_date = today + timedelta(days=30)

    def expiry_status(value):
        if not value:
            return "Missing"
        value = value.date() if hasattr(value, "date") else value
        if value < today:
            return "Expired"
        if value <= due_date:
            return "Due within 30 days"
        return "Valid"

    if vendor_id:
        cur.execute("SELECT * FROM vehicles WHERE vendor_id=:1 ORDER BY reg_number", (vendor_id,))
        cols = [d[0].lower() for d in cur.description]
        for row in cur.fetchall():
            item = dict(zip(cols, row))
            item["documents"] = {
                "Insurance": expiry_status(item.get("insurance_exp")),
                "Permit": expiry_status(item.get("permit_exp")),
                "Fitness": expiry_status(item.get("fitness_exp")),
                "PUC": expiry_status(item.get("puc_exp")),
            }
            vehicles.append(item)
        cur.execute("SELECT * FROM drivers WHERE vendor_id=:1 ORDER BY driver_name", (vendor_id,))
        cols = [d[0].lower() for d in cur.description]
        for row in cur.fetchall():
            item = dict(zip(cols, row))
            item["license_status"] = expiry_status(item.get("license_expiry"))
            drivers.append(item)
    conn.close()
    return templates.TemplateResponse(
        "reports/vendor_compliance.html", {"request": request, "user": user,
        "vendors": vendors, "selected_vendor": vendor_id, "is_vendor": is_vendor,
        "vehicles": vehicles, "drivers": drivers, "due_days": 30},
    )


@router.get("/employee-productivity")
def employee_productivity(request: Request, start: str = "", end: str = "",
                          hourly_rate: str = "", role_filter: str = "", department: str = "", export: str = ""):
    user = current_user(request)
    role = (user or {}).get("role", "").strip().lower()
    if not user or role in FEEDBACK_EXTERNAL_ROLES or role in {"guest", "driver"}:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    start_date = _parse_date(start) or date.today().replace(day=1)
    end_date = _parse_date(end) or date.today()
    try:
        rate = float(hourly_rate or 0)
    except ValueError:
        rate = 0.0
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT role FROM users WHERE role IS NOT NULL ORDER BY role")
    roles = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT DISTINCT department FROM employees WHERE department IS NOT NULL ORDER BY department")
    departments = [r[0] for r in cur.fetchall()]
    conditions = ["l.login_dt >= :1", "l.login_dt < :2 + 1"]
    params = [start_date, end_date]
    if role_filter:
        params.append(role_filter); conditions.append(f"UPPER(l.role)=UPPER(:{len(params)})")
    if department:
        params.append(department); conditions.append(f"EXISTS (SELECT 1 FROM employees e WHERE UPPER(e.emp_id)=UPPER(l.user_id) AND UPPER(e.department)=UPPER(:{len(params)}))")
    cur.execute(
        "SELECT l.user_id, MAX(l.user_name), MAX(l.role), "
        "COUNT(DISTINCT TRUNC(l.login_dt)), COUNT(*), "
        "NVL(SUM(l.hours_worked),0), MIN(l.login_dt), MAX(l.logout_dt) "
        "FROM login_log l WHERE " + " AND ".join(conditions) + " "
        "GROUP BY l.user_id ORDER BY MAX(l.user_name)",
        params,
    )
    rows = []
    for r in cur.fetchall():
        hours = float(r[5] or 0)
        rows.append({"user_id": r[0], "name": r[1], "role": r[2],
                     "days": int(r[3] or 0), "logins": int(r[4] or 0),
                     "hours": round(hours, 2), "payroll": round(hours * rate, 2),
                     "first": r[6], "last": r[7]})
    audit(conn, user, "Employee Productivity Report Exported" if export else "Employee Productivity Report Viewed", "Login Log",
          f"from={start_date}; to={end_date}; rows={len(rows)}")
    conn.commit()
    conn.close()
    if export:
        import csv, io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["User ID", "Employee", "Role", "Present Days", "Login Sessions", "Total Hours", "Estimated Payroll", "First Login", "Last Logout"])
        for r in rows:
            writer.writerow([r[k] for k in ("user_id", "name", "role", "days", "logins", "hours", "payroll", "first", "last")])
        return Response(content=buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="rentago-employee-productivity.csv"'})
    return templates.TemplateResponse(
        "reports/employee_productivity.html", {"request": request, "user": user,
         "rows": rows, "start": start_date, "end": end_date, "hourly_rate": rate,
         "roles": roles, "departments": departments, "role_filter": role_filter, "department_filter": department},
    )

# (db key, header) — mirrors the VBA GenerateReport column layout 1:1.
REPORT_COLS = [
    ("booking_id", "Booking ID"), ("booking_date", "Booking Date"),
    ("booking_type", "Booking Type"), ("company_id", "Company ID"),
    ("company_name", "Company"), ("entity_name", "Entity"),
    ("guest_name_1", "Guest"), ("guest_contact", "Guest Contact"),
    ("admin_name", "Admin"), ("pickup_address", "Pickup Address"),
    ("drop_address", "Drop Address"), ("pickup_city", "Pickup City"),
    ("drop_city", "Drop City"), ("pickup_date", "Pickup Date"),
    ("pickup_time", "Pickup Time"), ("vehicle_type", "Vehicle Type"),
    ("booked_by_step1", "Step 1 Booked By"),
    ("trip_id", "Trip ID"), ("trip_status", "Trip Status"),
    ("actual_start_dt", "Actual Trip Start"), ("actual_end_dt", "Actual Trip End"),
    ("pickup_start_km", "Start Odometer"), ("drop_end_km", "End Odometer"),
    ("actual_kms", "Actual Kms"), ("actual_hrs", "Actual Hours"),
    ("extra_kms", "Extra Kms"), ("extra_hrs", "Extra Hours"),
    ("guest_rating", "Guest Rating"), ("guest_feedback", "Feedback"),
    ("safety_status", "Safety Status"), ("incident_priority", "Incident Priority"),
    ("feedback_owner_group", "Feedback Ownership"), ("feedback_status", "Feedback Status"),
    ("client_invoice_id", "Client Invoice ID"), ("client_invoice_status", "Client Invoice Status"),
    ("client_payment_status", "Client Payment Status"), ("client_original_amount", "Client Original"),
    ("client_final_amount", "Client Final"), ("trip_expenses", "Trip Expenses"),
    ("vendor_billing_status", "Vendor Billing Status"), ("client_paid", "Client Paid"),
    ("vendor_paid", "Vendor Paid"), ("account_status", "Account Status"),
    ("status", "Booking Status"), ("booked_by_step2", "Step 2 Booked By"),
    ("booked_by_step3", "Step 3 Booked By"),
]

_BOOKING_KEYS = ["booking_id", "booking_date", "booking_type", "company_id", "company_name",
                 "entity_name", "guest_name_1", "guest_contact", "admin_name", "pickup_address",
                 "drop_address", "pickup_city", "drop_city", "pickup_date", "pickup_time",
                 "vehicle_type", "done_by_booking"]
_TRIP_KEYS = ["trip_id", "trip_status", "actual_start_dt", "actual_end_dt", "pickup_start_km",
              "drop_end_km", "actual_kms", "actual_hrs", "extra_kms", "extra_hrs",
              "guest_rating", "guest_feedback", "safety_status", "incident_priority",
              "feedback_owner_group", "feedback_status"]
_INVOICE_KEYS = ["invoice_id", "invoice_status", "payment_status", "original_amount",
                 "final_amount", "total_vendor_expenses"]


def _parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None


def _filters(request: Request):
    p = request.query_params
    ftype = (p.get("type") or "All Types").strip() or "All Types"
    fci = (p.get("ci") or "All").strip() or "All"
    sdate = _parse_date(p.get("from", ""))
    edate = _parse_date(p.get("to", ""))
    return ftype, fci, sdate, edate


def _run_report(cur, ftype, fci, sdate, edate, tenant_id=None):
    where = ["1=1"]
    params = []

    def bind(value):
        params.append(value)
        return f":{len(params)}"

    if ftype != "All Types":
        where.append(f"UPPER(TRIM(b.booking_type))=UPPER(TRIM({bind(ftype)}))")
    if fci != "All":
        b = bind(fci)
        where.append(f"(UPPER(TRIM(b.company_name))=UPPER(TRIM({b})) "
                     f"OR UPPER(TRIM(b.guest_name_1))=UPPER(TRIM({b})))")
    if sdate and edate:
        where.append(f"b.pickup_date BETWEEN {bind(sdate)} AND {bind(edate)}")
    elif sdate:
        where.append(f"b.pickup_date >= {bind(sdate)}")
    elif edate:
        where.append(f"b.pickup_date <= {bind(edate)}")
    if tenant_id:
        where.append(f"b.tenant_id={bind(tenant_id)}")

    bcols = ", ".join(f"b.{c}" for c in _BOOKING_KEYS)
    tcols = ", ".join(f"t.{c}" for c in _TRIP_KEYS)
    icols = ", ".join(f"i.{c}" for c in _INVOICE_KEYS)
    cur.execute(
        f"SELECT {bcols}, {tcols}, {icols}, "
        "(SELECT NVL(SUM(CASE WHEN p.pay_type='Receipt from Customer' THEN p.amount ELSE 0 END),0) FROM payments p WHERE p.ref_id=i.invoice_id) client_paid, "
        "(SELECT NVL(SUM(CASE WHEN p.pay_type='Payment to Vendor' THEN p.amount ELSE 0 END),0) FROM payments p WHERE p.ref_id=i.invoice_id) vendor_paid "
        f"FROM bookings b "
        f"LEFT JOIN trips t ON t.booking_id = b.booking_id "
        f"LEFT JOIN invoices i ON i.booking_id = b.booking_id "
        f"WHERE {' AND '.join(where)} "
        f"ORDER BY b.booking_date DESC NULLS LAST, b.booking_id DESC, t.trip_id DESC, i.invoice_id DESC",
        params or None,
    )
    headers = [d[0].lower() for d in cur.description]
    raw = [dict(zip(headers, r)) for r in cur.fetchall()]

    # One row per booking: first trip / first invoice wins (VBA semantics).
    rows, seen = [], set()
    for r in raw:
        bid = str(r.get("booking_id") or "")
        if bid in seen:
            continue
        seen.add(bid)
        item = {k: r.get(k) for k, _ in REPORT_COLS}
        item["client_invoice_id"] = r.get("invoice_id")
        item["client_invoice_status"] = r.get("invoice_status")
        item["client_payment_status"] = r.get("payment_status")
        item["client_original_amount"] = r.get("original_amount")
        item["client_final_amount"] = r.get("final_amount")
        item["trip_expenses"] = r.get("total_vendor_expenses")
        item["vendor_billing_status"] = "Submitted" if r.get("total_vendor_expenses") else "Pending"
        item["client_paid"] = r.get("client_paid")
        item["vendor_paid"] = r.get("vendor_paid")
        item["account_status"] = "Closed" if str(r.get("booking_status") or "").startswith(("2-", "3-")) else "Open"
        item["status"] = r.get("booking_status")
        item["booked_by_step1"] = r.get("done_by_booking")
        item["booked_by_step2"] = r.get("done_by_vendor")
        item["booked_by_step3"] = r.get("done_by_driver")
        rows.append(item)
        if len(rows) >= MAX_ROWS:
            break
    return rows


def _dropdowns(cur):
    cur.execute("SELECT DISTINCT booking_type FROM bookings "
                "WHERE booking_type IS NOT NULL ORDER BY booking_type")
    types = [str(r[0]).strip() for r in cur.fetchall() if str(r[0] or "").strip()]
    cur.execute(
        "SELECT name FROM (SELECT DISTINCT TRIM(company_name) AS name FROM bookings "
        "UNION SELECT DISTINCT TRIM(guest_name_1) AS name FROM bookings) "
        "WHERE name IS NOT NULL ORDER BY name")
    cis = [str(r[0]).strip() for r in cur.fetchall() if str(r[0] or "").strip()]
    return types, cis


@router.get("")
def report_page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if (user.get("role") or "").strip().lower() in {"vendor", "vendor admin", "vendor operations", "vendor viewer"}:
        return RedirectResponse(url="/dashboards/vendor", status_code=303)
    if module_level(user, "Reports") is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)

    ftype, fci, sdate, edate = _filters(request)
    conn = get_connection()
    cur = conn.cursor()
    visible = visible_booking_ids(user, cur)
    types, cis = _dropdowns(cur)
    tenant_id = None if (user.get("role") or "").strip().lower() == "super admin" else user.get("tenant_id")
    rows = _run_report(cur, ftype, fci, sdate, edate, tenant_id)
    rows = [r for r in rows if can_view(visible, str(r.get("booking_id") or ""))]
    conn.close()

    total_amount = 0.0
    for r in rows:
        try:
            total_amount += float(r.get("final_amount") or 0)
        except (TypeError, ValueError):
            pass

    return templates.TemplateResponse(
        "reports/index.html",
        {"request": request, "user": user, "rows": rows,
         "cols": REPORT_COLS, "types": types, "cis": cis,
         "cur_type": ftype, "cur_ci": fci,
         "cur_from": request.query_params.get("from", ""),
         "cur_to": request.query_params.get("to", ""),
         "total_amount": total_amount, "max_rows": MAX_ROWS},
    )


@router.get("/export")
def report_export(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if (user.get("role") or "").strip().lower() in {"vendor", "vendor admin", "vendor operations", "vendor viewer"}:
        return RedirectResponse(url="/dashboards/vendor", status_code=303)
    if module_level(user, "Reports") is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)

    ftype, fci, sdate, edate = _filters(request)
    conn = get_connection()
    cur = conn.cursor()
    visible = visible_booking_ids(user, cur)
    tenant_id = None if (user.get("role") or "").strip().lower() == "super admin" else user.get("tenant_id")
    rows = _run_report(cur, ftype, fci, sdate, edate, tenant_id)
    rows = [r for r in rows if can_view(visible, str(r.get("booking_id") or ""))]
    audit(conn, user, "Report Exported", ftype,
          f"ci={fci}; from={sdate}; to={edate}; rows={len(rows)}")
    conn.close()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([label for _, label in REPORT_COLS])
    for r in rows:
        w.writerow(["" if r.get(k) is None else str(r.get(k))
                    for k, _ in REPORT_COLS])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition":
                 'attachment; filename="rentago-report.csv"'},
    )
