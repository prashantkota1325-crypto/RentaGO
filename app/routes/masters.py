"""Master data + admin sheet CRUD (Super Admin data catalog).

Config-driven generic handlers (list + search + pagination, create, edit) with
RBAC from the roles matrix (F = edit, V = view). Covers the five core masters
(Companies, Employees, Vendors, Vehicles, Drivers) plus every remaining
workbook sheet: Individuals, Contacts, Contracts, Ratecards, Leads, Settings
(editable) and the Audit / Login / OTP logs (view-only). Also hosts the
Roles Matrix grid editor (Super Admin).
"""

from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ..auth import current_user, module_level, clear_roles_cache
from ..templating import templates
from ..db import get_connection, run_script
from ..audit import audit
from .. import ids

router = APIRouter(prefix="/masters")

PAGE_SIZE = 100

# Keep the matrix editor complete even when a workbook import did not contain
# rows for newer web modules. Missing rows remain no-access until an admin
# explicitly saves F or V for a role.
MATRIX_SHEETS = (
    "Bookings", "Trips", "Invoices", "Payments", "Reports", "Notifications",
    "Companies", "Employees", "Vendors", "Vehicles", "Drivers", "Ratecards",
    "Leads", "Contracts", "Contacts", "Individuals", "Settings",
    "Audit Log", "Login Log", "OTP Log", "Users", "Approvals",
    "Feedback",
    "Policies",
    "CEO Dashboard", "Ops Dashboard", "Sales Dashboard", "Finance Dashboard",
    "Vendor Dashboard", "Customer 360", "Investor MIS", "Compliance",
    "Tracking Dashboard", "SLA Dashboard", "Roles Matrix",
)

_STATUS = ("Active", "Inactive")
_YESNO = ("Yes", "No")


def _f(name, label, ftype="text", required=False, options=None):
    return {"name": name, "label": label, "type": ftype, "required": required,
            "options": options}


MASTERS = {
    # ---- core masters (matrix-scoped access) ----
    "companies": {
        "title": "Companies", "sheet": "Companies", "table": "companies",
        "pk": "company_id", "gen": "next_company_id",
        "list": [("company_id", "ID"), ("company_name", "Company"), ("industry", "Industry"),
                 ("city", "City"), ("state", "State"), ("credit_limit", "Credit Limit"),
                 ("credit_days", "Credit Days"), ("status", "Status")],
        "search": ["company_name", "city", "industry", "company_id", "account_manager"],
        "fields": [
            _f("company_name", "Company Name", required=True),
            _f("legal_name", "Legal Name"),
            _f("gst", "GST"), _f("pan", "PAN"),
            _f("industry", "Industry"), _f("city", "City"), _f("state", "State"),
            _f("booker_name", "Booker Name"), _f("booker_email", "Booker Email", "email"),
            _f("booker_phone", "Booker Phone", "tel"),
            _f("guest_name", "Guest Name"), _f("guest_email", "Guest Email", "email"),
            _f("guest_phone", "Guest Phone", "tel"),
            _f("credit_limit", "Credit Limit (Rs.)", "number"),
            _f("credit_days", "Credit Days", "number"),
            _f("account_manager", "Account Manager"),
            _f("status", "Status", "select", options=_STATUS),
        ],
    },
    "company-entities": {
        "title": "Company Legal Entities", "sheet": "Company Legal Entities", "table": "company_entities",
        "pk": "entity_id", "gen": lambda cur: ids.next_company_entity_id(cur),
        "list": [("entity_id", "Entity ID"), ("company_id", "Company ID"), ("entity_code", "Entity Code"),
                  ("legal_name", "Legal Entity"), ("gstin", "GSTIN"), ("city", "City"), ("state", "State"), ("status", "Status")],
        "search": ["entity_id", "company_id", "entity_code", "legal_name", "gstin", "city"],
        "fields": [
            _f("company_id", "Company ID", required=True), _f("entity_code", "Entity Code"),
            _f("legal_name", "Legal Entity Name", required=True), _f("gstin", "GSTIN"),
            _f("city", "City"), _f("state", "State"), _f("address", "Address"),
            _f("status", "Status", "select", options=_STATUS),
        ],
    },
    "employees": {
        "title": "Employees", "sheet": "Employees", "table": "employees",
        "pk": "emp_id", "pk2": "emp_code", "gen": "next_employee_ids",
         "list": [("emp_id", "Emp ID"), ("emp_code", "Code"), ("company_name", "Company"),
                  ("guest_name", "Guest Name"), ("guest_mobile", "Mobile"),
                   ("guest_email", "Email"), ("department", "Department"), ("designation", "Designation"),
                  ("reporting_manager_name", "Reporting Manager"), ("doj", "DOJ"),
                  ("job_status", "Job Status"), ("status", "Status")],
        "search": ["guest_name", "company_name", "guest_mobile", "emp_code", "emp_id"],
        "filters": [
            ("company_name", "Company"), ("guest_name", "Guest Name"),
            ("guest_mobile", "Mobile No."), ("guest_email", "Email ID"),
             ("emp_code", "Emp Code"), ("admin_name", "SPOC Name"),
             ("admin_mobile", "SPOC Mobile"), ("admin_email", "SPOC Email"),
            ("pickup_location", "Pickup Location"), ("drop_location", "Drop Location"),
            ("status", "Status"),
        ],
        "fields": [
            _f("company_name", "Company", required=True),
            _f("company_id", "Company ID"),
             _f("department", "Department"), _f("designation", "Designation"), _f("reporting_manager_name", "Reporting Manager Name"),
            _f("doj", "Date of Joining", "date"),
            _f("job_status", "Job Status", "select", options=("Probation", "Permanent")),
            _f("guest_name", "Guest / Employee Name", required=True),
            _f("guest_mobile", "Mobile", "tel"), _f("guest_email", "Email", "email"),
             _f("admin_name", "SPOC Name"), _f("admin_mobile", "SPOC Mobile", "tel"),
             _f("admin_email", "SPOC Email", "email"),
            _f("pickup_location", "Pickup Location"),
            _f("drop_location", "Drop Location"),
            _f("shift_timing", "Shift Timing"),
            _f("emergency_contact", "Emergency Contact"),
            _f("status", "Status", "select", options=_STATUS),
        ],
    },
    "vendors": {
        "title": "Vendors", "sheet": "Vendors", "table": "vendors",
        "pk": "vendor_id", "gen": "next_vendor_id",
        "list": [("vendor_id", "ID"), ("vendor_name", "Vendor"), ("company_name", "Company"),
                 ("mobile", "Mobile"), ("email", "Email"), ("kyc_status", "KYC"),
                 ("grade", "Grade"), ("status", "Status")],
        "search": ["vendor_name", "company_name", "mobile", "email", "vendor_id"],
        "fields": [
            _f("vendor_name", "Vendor Name", required=True),
            _f("company_name", "Company"), _f("pan", "PAN"), _f("gst", "GST"),
            _f("mobile", "Mobile", "tel"), _f("email", "Email", "email"),
            _f("address", "Address"),
            _f("bank_account", "Bank Account"), _f("ifsc", "IFSC"),
            _f("kyc_status", "KYC Status"),
            _f("agreement_status", "Agreement Status"),
            _f("grade", "Grade"), _f("rating", "Rating"),
            _f("status", "Status", "select", options=_STATUS),
        ],
    },
    "vehicles": {
        "title": "Vehicles", "sheet": "Vehicles", "table": "vehicles",
        "pk": "vehicle_id", "gen": "next_vehicle_id",
        "list": [("vehicle_id", "ID"), ("reg_number", "Reg No"), ("make", "Make"),
                 ("model", "Model"), ("category", "Category"), ("vendor_id", "Vendor"),
                 ("seats", "Seats"), ("status", "Status")],
        "search": ["reg_number", "make", "model", "category", "vendor_id", "vehicle_id"],
        "fields": [
            _f("reg_number", "Registration No", required=True),
            _f("make", "Make"), _f("model", "Model"), _f("variant", "Variant"),
            _f("fuel", "Fuel"), _f("ev_ice", "EV/ICE"), _f("v_year", "Year"),
            _f("seats", "Seats", "number"), _f("category", "Category"),
            _f("vendor_id", "Vendor ID"),
            _f("insurance_exp", "Insurance Expiry", "date"),
            _f("permit_exp", "Permit Expiry", "date"),
             _f("fitness_exp", "Fitness Expiry", "date"),
             _f("puc_exp", "PUC Expiry", "date"),
             _f("compliance_status", "Vehicle Compliance", "select", options=("Pending", "Yes", "No")),
             _f("status", "Status", "select", options=_STATUS),
        ],
    },
    "drivers": {
        "title": "Drivers", "sheet": "Drivers", "table": "drivers",
        "pk": "driver_id", "gen": "next_driver_id",
        "list": [("driver_id", "ID"), ("driver_name", "Driver"), ("vendor_id", "Vendor"),
                 ("mobile", "Mobile"), ("license_no", "License"),
                 ("license_expiry", "License Expiry"), ("rating", "Rating"),
                 ("status", "Status")],
        "search": ["driver_name", "mobile", "license_no", "vendor_id", "driver_id"],
        "fields": [
            _f("driver_name", "Driver Name", required=True),
            _f("vendor_id", "Vendor ID"),
            _f("mobile", "Mobile", "tel", required=True),
            _f("license_no", "License No"),
            _f("license_expiry", "License Expiry", "date"),
            _f("aadhaar_ref", "Aadhaar Ref"),
             _f("police_verification", "Police Verification"),
             _f("background_check", "Background Check"),
             _f("languages_known", "Languages Known"),
             _f("passport_photo_path", "Passport Photo URL"),
             _f("compliance_status", "Driver Compliance", "select", options=("Pending", "Yes", "No")),
             _f("rating", "Rating"),
            _f("status", "Status", "select", options=_STATUS),
        ],
    },
    # ---- additional workbook sheets; access is controlled by the same matrix
    #      as the core masters and is not implicitly Super Admin-only ----
    "individuals": {
        "title": "Individuals", "sheet": "Individuals", "table": "individuals",
        "pk": "individual_id",
        "gen": lambda cur: ids.next_individual_id(cur, None),
        "list": [("individual_id", "ID"), ("guest_name", "Guest"), ("guest_contact", "Mobile"),
                 ("guest_email", "Email"), ("company_name", "Company"),
                 ("company_id", "Company ID"), ("booking_type", "Booking Type"),
                 ("status", "Status")],
        "search": ["individual_id", "guest_name", "guest_contact", "company_name"],
        "filters": [
            ("company_name", "Company"), ("guest_name", "Guest Name"),
            ("guest_contact", "Mobile No."), ("guest_email", "Email ID"),
            ("admin_name", "Admin Name"), ("admin_contact", "Admin Mobile"),
            ("admin_email", "Admin Email"), ("pickup_location", "Pickup Location"),
            ("drop_location", "Drop Location"), ("booking_type", "Booking Type"),
            ("status", "Status"),
        ],
        "fields": [
            _f("guest_name", "Guest Name", required=True),
            _f("guest_contact", "Guest Mobile", "tel"),
            _f("guest_email", "Guest Email", "email"),
            _f("company_name", "Company"), _f("company_id", "Company ID"),
            _f("admin_name", "Admin Name"), _f("admin_contact", "Admin Mobile", "tel"),
            _f("admin_email", "Admin Email", "email"),
            _f("pickup_location", "Pickup Location"),
            _f("drop_location", "Drop Location"),
            _f("booking_type", "Booking Type"),
            _f("status", "Status", "select", options=_STATUS),
        ],
    },
    "contacts": {
        "title": "Company Contacts", "sheet": "Contacts", "table": "contacts",
        "pk": "contact_id", "gen": "next_contact_id",
         "list": [("contact_id", "Admin ID"), ("company_id", "Company ID"), ("company_name", "Company Name"), ("contact_name", "Admin Name"),
                 ("designation", "Designation"), ("department", "Department"),
                  ("email", "Email"), ("mobile", "Mobile"), ("account_manager_name", "Account Manager"),
                  ("account_manager_contact", "Account Manager Contact"), ("account_manager_email", "Account Manager Email"),
                 ("approval_authority", "Approval Authority"), ("status", "Status")],
        "search": ["contact_name", "company_id", "email", "mobile", "contact_id"],
        "fields": [
             _f("company_id", "Company ID", required=True), _f("company_name", "Company Name"),
             _f("contact_type", "Contact Type"),
            _f("contact_name", "Contact Name", required=True),
            _f("designation", "Designation"), _f("department", "Department"),
            _f("email", "Email", "email"), _f("mobile", "Mobile", "tel"),
            _f("account_manager_name", "Account Manager Name"),
            _f("account_manager_contact", "Account Manager Contact", "tel"),
            _f("account_manager_email", "Account Manager Email", "email"),
            _f("approval_authority", "Approval Authority", "select", options=_YESNO),
            _f("status", "Status", "select", options=_STATUS),
        ],
    },
    "contracts": {
        "title": "Contracts", "sheet": "Contracts", "table": "contracts",
        "pk": "contract_id", "gen": "next_contract_id",
        "list": [("contract_id", "ID"), ("company_id", "Company"), ("contract_no", "Contract No"),
                 ("service_type", "Service Type"), ("start_date", "Start"),
                 ("end_date", "End"), ("credit_days", "Credit Days"),
                 ("sla_pct", "SLA %"), ("status", "Status")],
        "search": ["contract_no", "company_id", "service_type", "contract_id"],
        "fields": [
            _f("company_id", "Company ID", required=True),
            _f("contract_no", "Contract No"),
            _f("service_type", "Service Type"),
            _f("start_date", "Start Date", "date"),
            _f("end_date", "End Date", "date"),
            _f("min_commitment", "Min Commitment (trips)", "number"),
            _f("credit_days", "Credit Days", "number"),
            _f("sla_pct", "SLA %", "number"),
            _f("status", "Status", "select", options=_STATUS),
        ],
    },
    "ratecards": {
        "title": "Ratecards", "sheet": "Ratecards", "table": "ratecards",
        "pk": "rate_card_id", "gen": "next_ratecard_id",
        "list": [("sr_no", "Sr. No."), ("company_id", "Company ID"), ("legal_name", "Legal Name"),
                 ("city", "CITY"), ("category", "VEHICLE Category"), ("vehicle_model", "VEHICLE MODEL"),
                 ("package_name", "PACKAGE NAME"), ("package_rate", "Package Rate"),
                 ("pkg_fixed_kms", "Pkg Fixed Km's"), ("pkg_fixed_hrs", "Pkg Fixed Hr's"),
                 ("extra_hr_rate", "Extra Hr Rate"), ("extra_km_rate", "Extra KM Rate"),
                 ("toll_amt", "Toll Amt"), ("parking_amt", "Parking Amt"),
                 ("da", "DA"), ("night_allowance_after_10_pm", "Night Allowance After 10 PM"),
                 ("night_allowance_after_11_pm", "Night Allowance After 11 PM"),
                 ("garage_to_garage_kms", "Garage To Garage Km's"),
                 ("garage_to_garage_pct", "Garage To Garage %")],
        "search": ["sr_no", "company_id", "legal_name", "category", "vehicle_model"],
        "fields": [
            _f("sr_no", "Sr. No.", "number"),
            _f("company_id", "Company ID"),
            _f("legal_name", "Legal Name", required=True),
            _f("city", "CITY"),
            _f("category", "VEHICLE Category", required=True),
            _f("vehicle_model", "VEHICLE MODEL"),
            _f("package_name", "PACKAGE NAME"),
            _f("package_rate", "Package Rate", "number"),
            _f("pkg_fixed_kms", "Pkg Fixed Km's", "number"),
            _f("pkg_fixed_hrs", "Pkg Fixed Hr's", "number"),
            _f("extra_hr_rate", "Extra Hr Rate", "number"),
            _f("extra_km_rate", "Extra KM Rate", "number"),
            _f("toll_amt", "Toll Amt", "number"),
            _f("parking_amt", "Parking Amt", "number"),
            _f("da", "DA", "number"),
            _f("night_allowance_after_10_pm", "Night Allowance After 10 PM", "number"),
            _f("night_allowance_after_11_pm", "Night Allowance After 11 PM", "number"),
            _f("garage_to_garage_kms", "Garage To Garage Km's", "number"),
            _f("garage_to_garage_pct", "Garage To Garage %", "number"),
        ],
    },
    "leads": {
        "title": "Sales Leads", "sheet": "Leads", "table": "leads",
        "pk": "lead_id", "gen": "next_lead_id",
        "list": [("lead_id", "ID"), ("company", "Company"), ("industry", "Industry"),
                 ("city", "City"), ("contact", "Contact"), ("phone", "Phone"),
                 ("sales_owner", "Sales Owner"), ("stage", "Stage"),
                 ("funnel_status", "Funnel")],
        "search": ["company", "contact", "sales_owner", "city", "lead_id"],
        "fields": [
            _f("company", "Company", required=True),
            _f("industry", "Industry"), _f("city", "City"),
            _f("contact", "Contact Person"), _f("phone", "Phone", "tel"),
            _f("requirement", "Requirement"),
            _f("est_vehicles", "Est. Vehicles", "number"),
            _f("est_monthly_rev", "Est. Monthly Rev", "number"),
            _f("est_contribution", "Est. Contribution", "number"),
            _f("sales_owner", "Sales Owner"),
            _f("stage", "Stage"),
            _f("probability", "Probability", "number"),
            _f("expected_close", "Expected Close", "date"),
            _f("next_followup", "Next Follow-up", "date"),
            _f("notes", "Notes"),
            _f("funnel_status", "Funnel Status"),
        ],
    },
    "settings": {
        "title": "Settings", "sheet": "Settings", "table": "settings",
        "pk": "setting_name", "pk_input": True,
        "list": [("setting_name", "Setting"), ("setting_value", "Value"),
                 ("setting_desc", "Description")],
        "search": ["setting_name", "setting_value", "setting_desc"],
        "fields": [
            _f("setting_value", "Value"),
            _f("setting_desc", "Description"),
        ],
    },
    # ---- logs: view-only (readonly) ----
    "audit-log": {
        "title": "Audit Log", "sheet": "Audit Log", "table": "audit_log",
        "pk": "log_seq", "readonly": True,
        "order": "TO_NUMBER(log_seq) DESC NULLS LAST",
        "list": [("log_seq", "#"), ("audit_date", "Date"), ("audit_time", "Time"),
                 ("user_id", "User"), ("audit_user", "Name"), ("action", "Action"),
                 ("record", "Record"), ("notes", "Notes")],
        "search": ["user_id", "audit_user", "action", "record"],
        "fields": [],
    },
    "login-log": {
        "title": "Login Log", "sheet": "Login Log", "table": "login_log",
        "pk": "log_id", "readonly": True, "order": "log_id DESC",
        "list": [("log_id", "Log ID"), ("user_id", "User"), ("user_name", "Name"),
                 ("role", "Role"), ("login_dt", "Login"), ("logout_dt", "Logout"),
                 ("hours_worked", "Hours")],
        "search": ["user_id", "user_name", "role", "log_id"],
        "fields": [],
    },
    "otp-log": {
        "title": "OTP Log", "sheet": "OTP Log", "table": "otp_log",
        "pk": "otp_id", "readonly": True, "order": "otp_id DESC",
        "list": [("otp_id", "OTP ID"), ("user_id", "User"), ("otp_code", "Code"),
                 ("purpose", "Purpose"), ("generated_by", "Generated By"),
                 ("generated_dt", "Generated"), ("expires_dt", "Expires"),
                 ("used_dt", "Used"), ("status", "Status")],
        "search": ["user_id", "purpose", "otp_id"],
        "fields": [],
    },
}

# Portal-specific views reuse the existing tables instead of duplicating data.
MASTERS["corporate-admin-contacts"] = {
    **MASTERS["contacts"], "title": "Corporate Admin Contacts",
    "sheet": "Corporate Admin Contacts",
    "base_where": "UPPER(NVL(contact_type,'ADMIN'))='ADMIN'",
    "defaults": {"contact_type": "ADMIN"},
}
MASTERS["rentago-employees"] = {
    **MASTERS["employees"], "title": "RentaGO Employees",
    "sheet": "RentaGO Employee Contacts",
    "gen": "next_rentago_employee_id",
    "base_where": "UPPER(TRIM(company_name))='RENTAGO TECHNOLOGIES PVT LTD'",
    "defaults": {"company_name": "RentaGO Technologies Pvt Ltd"},
}


def _cfg(key):
    return MASTERS.get(key)


def _sync_rentago_employees(conn):
    """Mirror internal RentaGO users into the RentaGO Employees master."""
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id,name,email,mobile,emp_id,department,status,role FROM users "
        "WHERE UPPER(NVL(organization_type,'RENTAgo'))='RENTAGO' "
        "AND LOWER(NVL(role,'')) NOT IN ('guest','driver','vendor','corporate admin','corporate user')")
    for user_id, name, email, mobile, emp_id, department, status, role in cur.fetchall():
        employee_id = str(emp_id or user_id).strip()[:60]
        cur.execute("SELECT COUNT(1) FROM employees WHERE emp_id=:1", (employee_id,))
        if int(cur.fetchone()[0] or 0):
            cur.execute(
                "UPDATE employees SET company_name='RentaGO Technologies Pvt Ltd',guest_name=:1,guest_mobile=:2,guest_email=:3,department=:4,status=:5,emp_code=:6 WHERE emp_id=:7",
                (name, mobile, email, department, status or 'Active', employee_id, employee_id),
            )
        else:
            cur.execute(
                "INSERT INTO employees (emp_id,company_name,department,emp_code,guest_name,guest_mobile,guest_email,status) "
                "VALUES (:1,'RentaGO Technologies Pvt Ltd',:2,:3,:4,:5,:6,:7)",
                (employee_id, department, employee_id, name, mobile, email, status or 'Active'),
            )


def _to_value(field, raw):
    ftype = field["type"]
    s = (raw or "").strip()
    if ftype == "number":
        if not s:
            return None
        try:
            return float(s) if "." in s else int(s)
        except ValueError:
            return None
    if ftype == "date":
        if not s:
            return None
        for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%b-%y", "%d-%b-%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                continue
        return None
    return s or None


@router.get("")
def masters_index(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    cards = []
    for key, cfg in MASTERS.items():
        level = module_level(user, cfg["sheet"])
        if level is None:
            continue
        if cfg.get("readonly"):
            level = "V"
        cards.append({"key": key, "title": cfg["title"], "level": level,
                      "readonly": cfg.get("readonly", False)})
    matrix = module_level(user, "Roles Matrix")
    return templates.TemplateResponse(
        "masters/index.html",
        {"request": request, "user": user, "cards": cards,
         "matrix_access": matrix == "F"},
    )


@router.get("/{key}")
def master_list(request: Request, key: str, q: str = "", page: int = 1):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    cfg = _cfg(key)
    if not cfg:
        return RedirectResponse(url="/masters", status_code=303)
    level = module_level(user, cfg["sheet"])
    if level is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    if cfg.get("readonly"):
        level = "V"
    page = max(1, page)
    offset = (page - 1) * PAGE_SIZE
    conn = get_connection()
    cur = conn.cursor()
    if key == "rentago-employees":
        _sync_rentago_employees(conn)
        conn.commit()

    cols = ", ".join(c for c, _ in cfg["list"])
    # Quick search (q): OR across the configured search columns.
    # Per-field filters (f_<col>): AND-ed together, so any one field alone
    # works and several fields narrow the result further.
    params, conds = [], []
    if cfg.get("base_where"):
        conds.append(cfg["base_where"])
    if q:
        ors = []
        for c in cfg["search"]:
            params.append(f"%{q}%")
            ors.append(f"LOWER(NVL({c}, ' ')) LIKE LOWER(:{len(params)})")
        conds.append("(" + " OR ".join(ors) + ")")
    active_filters = []
    for fcol, flabel in (cfg.get("filters") or []):
        val = (request.query_params.get("f_" + fcol) or "").strip()
        if val:
            params.append(f"%{val}%")
            conds.append(f"LOWER(NVL({fcol}, ' ')) LIKE LOWER(:{len(params)})")
        active_filters.append({"name": "f_" + fcol, "label": flabel,
                               "value": val})
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    cur.execute(f"SELECT COUNT(*) FROM {cfg['table']}{where}", params or None)
    total = int(cur.fetchone()[0])
    order = cfg.get("order") or cfg["pk"]
    cur.execute(
        f"SELECT {cols} FROM {cfg['table']}{where} ORDER BY {order} "
        f"OFFSET {offset} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY",
        params or None,
    )
    headers = [d[0].lower() for d in cur.description]
    rows = [dict(zip(headers, r)) for r in cur.fetchall()]
    conn.close()
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    qs_parts = []
    if q:
        qs_parts.append("q=" + quote(q))
    for f in active_filters:
        if f["value"]:
            qs_parts.append(f["name"] + "=" + quote(f["value"]))
    qs = "&".join(qs_parts)
    return templates.TemplateResponse(
        "masters/list.html",
        {"request": request, "user": user,
         "cfg": {"key": key, "title": cfg["title"], "list": cfg["list"],
                 "filters": active_filters},
         "rows": rows, "query": q, "qs": qs, "page": page, "pages": pages,
         "total": total, "level": level},
    )


def _load_row(cur, cfg, rec_id):
    where = f"{cfg['pk']}=:1"
    if cfg.get("base_where"):
        where += f" AND ({cfg['base_where']})"
    cur.execute(f"SELECT * FROM {cfg['table']} WHERE {where}", (rec_id,))
    row = cur.fetchone()
    if not row:
        return None
    headers = [d[0].lower() for d in cur.description]
    return dict(zip(headers, row))


def _editable(user, cfg):
    return module_level(user, cfg["sheet"]) == "F" and not cfg.get("readonly")


@router.get("/{key}/new")
def master_new(request: Request, key: str):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    cfg = _cfg(key)
    if not cfg:
        return RedirectResponse(url="/masters", status_code=303)
    if not _editable(user, cfg):
        return RedirectResponse(url=f"/masters/{key}?msg=not-allowed", status_code=303)
    return templates.TemplateResponse(
        "masters/form.html",
        {"request": request, "user": user,
         "cfg": {"key": key, "title": cfg["title"],
                 "pk_input": cfg.get("pk_input", False), "pk_name": cfg["pk"]},
         "fields": cfg["fields"], "rec": {}, "rec_id": None,
         "pk_label": cfg["pk"], "msg": request.query_params.get("msg", "")},
    )


def _parse_form(cfg, request_form):
    values = {}
    for field in cfg["fields"]:
        raw = request_form.get(field["name"], "")
        values[field["name"]] = _to_value(field, raw if isinstance(raw, str) else str(raw))
    return values


@router.post("/{key}/new")
async def master_create(request: Request, key: str):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    cfg = _cfg(key)
    if not cfg:
        return RedirectResponse(url="/masters", status_code=303)
    if not _editable(user, cfg):
        return RedirectResponse(url=f"/masters/{key}?msg=not-allowed", status_code=303)

    form = dict(await _form_pairs(request))
    values = _parse_form(cfg, form)
    values.update(cfg.get("defaults") or {})
    missing_fields = [field["label"] for field in cfg["fields"] if field["required"] and not str(form.get(field["name"]) or "").strip()]
    if missing_fields:
        return RedirectResponse(url=f"/masters/{key}/new?msg=missing&fields={quote(', '.join(missing_fields))}", status_code=303)
    if "status" in values and values.get("status") is None:
        values["status"] = "Active"

    conn = get_connection()
    cur = conn.cursor()
    try:
        if cfg.get("gen"):
            gen = cfg["gen"]
            if gen == "next_employee_ids":
                emp_id, emp_code = ids.next_employee_ids(cur)
                values["emp_id"], values["emp_code"] = emp_id, emp_code
                pk_val = emp_id
            elif gen == "next_rentago_employee_id":
                pk_val, emp_code = ids.next_rentago_employee_ids(cur)
                values["emp_id"] = pk_val
                values["emp_code"] = emp_code
            elif callable(gen):
                pk_val = gen(cur)
                values[cfg["pk"]] = pk_val
            else:
                pk_val = getattr(ids, gen)(cur)
                values[cfg["pk"]] = pk_val
        else:
            pk_val = (str(form.get(cfg["pk"]) or "")).strip()
            if not pk_val:
                conn.close()
                return RedirectResponse(url=f"/masters/{key}/new?msg=missing",
                                        status_code=303)
            values[cfg["pk"]] = pk_val
        if cfg["table"] == "employees":
            if not values.get("company_id") and values.get("company_name"):
                cur.execute(
                    "SELECT company_id FROM companies WHERE "
                    "UPPER(TRIM(company_name))=UPPER(TRIM(:1))",
                    (values["company_name"],),
                )
                r = cur.fetchone()
                values["company_id"] = str(r[0]) if r else None
        if cfg["table"] == "individuals":
            # new Individual guest -> auto Company ID 'RG-<n>'
            # (+1 over the last RG- number in the system database)
            if not values.get("company_id"):
                values["company_id"] = ids.next_guest_company_id(cur)

        cols = list(values.keys())
        cur.execute(
            f"INSERT INTO {cfg['table']} ({', '.join(cols)}) "
            f"VALUES ({', '.join(':' + str(i + 1) for i in range(len(cols)))})",
            [values[c] for c in cols],
        )
        audit(conn, user, f"{cfg['title']} Created", pk_val, "")
        conn.commit()
    except Exception:
        conn.close()
        return RedirectResponse(url=f"/masters/{key}/new?msg=error", status_code=303)
    conn.close()
    return RedirectResponse(url=f"/masters/{key}?msg=created", status_code=303)


@router.get("/{key}/{rec_id}/edit")
def master_edit(request: Request, key: str, rec_id: str):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    cfg = _cfg(key)
    if not cfg:
        return RedirectResponse(url="/masters", status_code=303)
    if not _editable(user, cfg):
        return RedirectResponse(url=f"/masters/{key}?msg=not-allowed", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    rec = _load_row(cur, cfg, rec_id)
    conn.close()
    if not rec:
        return RedirectResponse(url=f"/masters/{key}?msg=not-found", status_code=303)
    return templates.TemplateResponse(
        "masters/form.html",
        {"request": request, "user": user,
         "cfg": {"key": key, "title": cfg["title"],
                 "pk_input": False, "pk_name": cfg["pk"]},
         "fields": cfg["fields"], "rec": rec, "rec_id": rec_id,
         "pk_label": cfg["pk"], "msg": request.query_params.get("msg", "")},
    )


@router.post("/{key}/{rec_id}/edit")
async def master_update(request: Request, key: str, rec_id: str):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    cfg = _cfg(key)
    if not cfg:
        return RedirectResponse(url="/masters", status_code=303)
    if not _editable(user, cfg):
        return RedirectResponse(url=f"/masters/{key}?msg=not-allowed", status_code=303)
    if not cfg["fields"]:
        return RedirectResponse(url=f"/masters/{key}?msg=not-allowed", status_code=303)

    form = dict(await _form_pairs(request))
    values = _parse_form(cfg, form)
    values.update(cfg.get("defaults") or {})
    for field in cfg["fields"]:
        if field["required"] and not (str(form.get(field["name"]) or "").strip()):
            return RedirectResponse(
                url=f"/masters/{key}/{rec_id}/edit?msg=missing", status_code=303)
    if "status" in values and values.get("status") is None:
        values["status"] = "Active"

    conn = get_connection()
    cur = conn.cursor()
    old = _load_row(cur, cfg, rec_id)
    if not old:
        conn.close()
        return RedirectResponse(url=f"/masters/{key}?msg=not-found", status_code=303)
    try:
        sets = ", ".join(f"{c}=:{i + 1}" for i, c in enumerate(values))
        where = f"{cfg['pk']}=:{len(values) + 1}"
        if cfg.get("base_where"):
            where += f" AND ({cfg['base_where']})"
        cur.execute(
            f"UPDATE {cfg['table']} SET {sets} WHERE {where}",
            [*values.values(), rec_id],
        )
        audit(conn, user, f"{cfg['title']} Updated", rec_id, "")
        conn.commit()
    except Exception:
        conn.close()
        return RedirectResponse(
            url=f"/masters/{key}/{rec_id}/edit?msg=error", status_code=303)
    conn.close()
    return RedirectResponse(url=f"/masters/{key}?msg=updated", status_code=303)


# ---------------------------------------------------------------------------
# Roles Matrix grid editor (Super Admin) — mirrors the Roles sheet layout:
# rows = sheets, columns = roles, cells = F / V / blank (no access).
# ---------------------------------------------------------------------------
def _matrix_axes():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT sheet FROM roles ORDER BY sheet")
    sheets = [r[0] for r in cur.fetchall() if r[0]]
    master_sheets = {cfg["sheet"] for cfg in MASTERS.values() if cfg.get("sheet")}
    sheets = sorted(set(sheets) | set(MATRIX_SHEETS) | master_sheets, key=str.lower)
    cur.execute("SELECT DISTINCT role_code FROM roles ORDER BY role_code")
    role_codes = [r[0] for r in cur.fetchall()]
    conn.close()
    return sheets, role_codes


@router.get("/roles-matrix/grid")
def roles_matrix(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if module_level(user, "Roles Matrix") != "F":
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    sheets, role_codes = _matrix_axes()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT sheet, role_code, access_level FROM roles")
    grid = {s: {} for s in sheets}
    for sheet, role_code, level in cur.fetchall():
        if sheet in grid:
            grid[sheet][role_code] = (str(level or "").strip().upper() or None)
    conn.close()
    return templates.TemplateResponse(
        "masters/roles_matrix.html",
        {"request": request, "user": user, "sheets": sheets,
         "role_codes": role_codes, "grid": grid,
         "msg": request.query_params.get("msg", "")},
    )


@router.post("/roles-matrix/grid")
async def roles_matrix_save(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if module_level(user, "Roles Matrix") != "F":
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    form = dict(await _form_pairs(request))
    sheet = str(form.get("sheet") or "").strip()
    if not sheet:
        return RedirectResponse(url="/masters/roles-matrix/grid", status_code=303)
    _, role_codes = _matrix_axes()

    stmts = []
    changed = []
    for i, role_code in enumerate(role_codes):
        val = str(form.get(f"r{i}") or "").strip().upper()
        if val not in ("F", "V"):
            val = ""
        s_esc = sheet.replace("'", "''")
        r_esc = str(role_code).replace("'", "''")
        v_sql = f"'{val}'" if val else "NULL"
        stmts.append(
            f"UPDATE roles SET access_level={v_sql} "
            f"WHERE sheet='{s_esc}' AND role_code='{r_esc}'")
        if val:
            stmts.append(
                f"INSERT INTO roles (sheet, role_code, access_level) "
                f"SELECT '{s_esc}', '{r_esc}', '{val}' FROM dual "
                f"WHERE NOT EXISTS (SELECT 1 FROM roles "
                f"WHERE sheet='{s_esc}' AND role_code='{r_esc}')")
        changed.append(f"{role_code}={val or '-'}")
    try:
        run_script(";\n".join(stmts) + ";")
        clear_roles_cache()
        conn = get_connection()
        audit(conn, user, "Roles Matrix Updated", sheet, "; ".join(changed)[:500])
        conn.commit()
        conn.close()
    except Exception:
        return RedirectResponse(url="/masters/roles-matrix/grid?msg=error",
                                status_code=303)
    return RedirectResponse(url="/masters/roles-matrix/grid?msg=saved",
                            status_code=303)


async def _form_pairs(request: Request):
    """Read the submitted form as (name, value) pairs (last value wins)."""
    form = await request.form()
    return form.multi_items()
