"""Master data + admin sheet CRUD (Super Admin data catalog).

Config-driven generic handlers (list + search + pagination, create, edit) with
RBAC from the roles matrix (F = edit, V = view). Covers the five core masters
(Companies, Employees, Vendors, Vehicles, Drivers) plus every remaining
workbook sheet: Individuals, Contacts, Contracts, Ratecards, Leads, Settings
(editable) and the Audit / Login / OTP logs (view-only). Also hosts the
Roles Matrix grid editor (Super Admin).
"""

from datetime import datetime
from io import BytesIO, StringIO
import base64
import csv
import json
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import RedirectResponse, JSONResponse, Response
import openpyxl

from ..auth import current_user, module_level, clear_roles_cache
from ..templating import templates
from ..db import get_connection, run_script
from ..audit import audit
from .. import ids
from ..scope import is_internal_user
from ..ratecard_import import validate_workbook, import_rows
from ..master_import import parse_and_validate, validate_rows
from ..master_import import sign_preview, verify_preview, source_hash
from ..config import settings
from ..master_designer import (
    FIELD_TYPES, PROTECTED_FIELDS, field_type, load_published_config,
    normalize_header, save_custom_values, seed_metadata, snapshot_config, validate_technical_name,
)

router = APIRouter(prefix="/masters")

PAGE_SIZE = 100
TENANT_MASTER_TABLES = {
    "companies", "company_entities", "employees", "vendors", "vehicles", "drivers",
    "individuals", "contacts", "contracts", "ratecards", "leads", "settings",
}


def _tenant_id(user):
    tenant_id = str(user.get("tenant_id") or "").strip()
    return tenant_id or None


def _import_value(field, value):
    if value is None:
        return None
    return _to_value(field, str(value))


def _record_import_errors(conn, import_id, errors):
    cur = conn.cursor()
    for error in errors:
        cur.execute(
            "INSERT INTO master_import_errors "
            "(error_id,import_id,row_number,source_field,source_value,canonical_field,error_code,message) "
            "VALUES (:1,:2,:3,:4,:5,:6,:7,:8)",
            (uuid.uuid4().hex, import_id, error.get("row"), error.get("source_field") or error.get("column"),
             str(error.get("value"))[:500] if error.get("value") is not None else None,
             error.get("canonical_field") or error.get("column"), error.get("code") or "VALIDATION_ERROR",
             error.get("message", "Import validation error")[:1000]),
        )


def _safe_csv_value(value):
    """Prevent spreadsheet formula execution when opening exported CSV."""
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"}:
        return "'" + value
    return value


def _export_rows(conn, cfg, tenant_id):
    columns = [column for column, _ in cfg["list"]]
    custom_fields = {field["name"]: field for field in cfg.get("fields", []) if field.get("custom_field")}
    db_columns = [column for column in columns if column not in custom_fields]
    cur = conn.cursor()
    cur.execute(f"SELECT {','.join(db_columns)} FROM {cfg['table']} WHERE tenant_id=:1 ORDER BY {cfg['pk']}", (tenant_id,))
    raw_rows = cur.fetchall()
    rows = []
    for raw in raw_rows:
        values = dict(zip(db_columns, raw))
        record_id = values.get(cfg["pk"])
        for name, field in custom_fields.items():
            cur.execute("SELECT value_text FROM master_custom_values WHERE master_id=:1 AND tenant_id=:2 AND record_id=:3 AND field_id=:4",
                        (cfg.get("_metadata_master_id"), tenant_id, str(record_id), field.get("field_id")))
            value = cur.fetchone()
            values[name] = value[0] if value else None
        rows.append([values.get(column) for column in columns])
    return columns, rows


def _master_access_allowed(user):
    """Generic masters are internal RentaGO administration surfaces."""
    return is_internal_user(user)


def _designer_allowed(user):
    if not user or not _master_access_allowed(user):
        return False
    return str(user.get("role") or "").strip().lower() in {"super admin", "superadmin"} or module_level(user, "Roles Matrix") == "F"


def _designer_master_id(cur, key):
    cur.execute("SELECT master_id FROM master_definitions WHERE master_key=:1 AND active='Y'", (key,))
    row = cur.fetchone()
    return row[0] if row else None


def _designer_audit(conn, user, master_id, action, field_id=None, old_value=None, new_value=None, version_id=None):
    conn.cursor().execute(
        "INSERT INTO master_configuration_audit (config_audit_id,tenant_id,user_id,master_id,field_id,config_version_id,action,old_value,new_value) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9)",
        (uuid.uuid4().hex, _tenant_id(user), user.get("user_id"), master_id, field_id, version_id, action,
         str(old_value)[:2000] if old_value is not None else None, str(new_value)[:2000] if new_value is not None else None),
    )

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
        "title": "Vendor Rate Chart", "sheet": "Ratecards", "table": "ratecards",
        "pk": "rate_card_id", "gen": "next_ratecard_id",
        # RATE_CARD_ID is generated and the source format has no stable key.
        # Do not enable generic confirmation until an approved business key and
        # matching database uniqueness policy exist.
        "import_blocked": True,
        "import_blocked_reason": "RATECARDS has no approved stable source business key.",
        "base_where": "UPPER(NVL(owner_type,'VENDOR'))='VENDOR'",
        "list": [("sr_no", "Sr.No."), ("company_id", "Company Id"), ("legal_name", "Legal Name"),
                 ("group_name", "Group"), ("city", "City"), ("state", "State"),
                 ("category", "Vehicle Category"), ("vehicle_model", "Vehicle Model"),
                 ("package_name", "Package Name"), ("package_rate", "Package Rate"),
                 ("pkg_fixed_kms", "Pkg Fixed Km's"), ("pkg_fixed_hrs", "Pkg Fixed Hr's"),
                 ("extra_km_rate", "Extra Km Rate"), ("extra_hr_rate", "Extra Hr Rate"),
                 ("toll_amt", "Toll Amt"), ("parking_amt", "Parking Amt"), ("da", "Da"),
                 ("night_allowance_after_10_pm", "Night Allowance After 10 Pm"),
                 ("night_allowance_after_11_pm", "Night Allowance After 11 Pm"),
                 ("garage_to_garage_kms", "Garage To Garage Km's"),
                 ("garage_to_garage_pct", "Garage To Garage %")],
        "search": ["company_id", "legal_name", "city", "category", "vehicle_model", "package_name"],
        "fields": [
            _f("sr_no", "Sr. No.", "number"),
             _f("company_id", "Company Id"), _f("group_name", "Group"),
             _f("legal_name", "Legal Name", required=True),
             _f("city", "City"), _f("state", "State"),
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
        "filters": [("user_id", "User"), ("audit_user", "Name")],
        "dropdown_filters": ["user_id", "audit_user"],
        "date_filters": [("from_date", "From Date"), ("to_date", "To Date")],
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
MASTERS["company-ratecards"] = {
    **MASTERS["ratecards"],
    "title": "Company Rate Chart",
    "base_where": "UPPER(owner_type)='COMPANY'",
}
MASTERS["individual-ratecards"] = {
    **MASTERS["ratecards"],
    "title": "Individual Rate Chart",
    "base_where": "UPPER(owner_type)='INDIVIDUAL'",
}


def _cfg(key):
    return MASTERS.get(key)


def _effective_cfg(key, cfg, user):
    if not cfg:
        return cfg
    try:
        conn = get_connection()
        effective = load_published_config(conn, key, cfg)
        conn.close()
        return effective
    except Exception:
        return cfg


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
        try:
            return datetime.fromisoformat(s).date()
        except ValueError:
            pass
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
    if not _master_access_allowed(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
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
    requested_columns = [
        ["companies", "company-entities", "employees", "corporate-admin-contacts", "contacts", "contracts", "company-ratecards"],
        ["rentago-employees", "roles-matrix", "leads", "settings", "login-log", "audit-log", "otp-log"],
        ["individuals", "individual-ratecards", "vendors", "ratecards", "vehicles", "drivers"],
    ]
    card_map = {card["key"]: card for card in cards}
    columns = []
    for keys in requested_columns:
        columns.append([card_map[key] for key in keys if key in card_map])
    if matrix == "F":
        columns[1].insert(1, {"key": "roles-matrix", "title": "Role Matrix", "level": "F", "readonly": False})
    listed = {card["key"] for column in columns for card in column}
    columns[1].extend([card for card in cards if card["key"] not in listed])
    return templates.TemplateResponse(
        "masters/index.html",
        {"request": request, "user": user, "cards": cards,
          "matrix_access": matrix == "F", "columns": columns},
    )

@router.get("/company-ratecards")
def company_ratecards_page(request: Request):
    user = current_user(request)
    level = module_level(user, "Ratecards") if user else None
    if not user or not _master_access_allowed(user) or level is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    return master_list(request, "company-ratecards")

# The canonical ratecard upload URL remains /masters/ratecards/import and is
# handled by the signed generic workflow below. Legacy handlers are retained
# only as migration reference and are intentionally not registered as routes.
def ratecard_import_page(request: Request, msg: str = "", owner_type: str = "VENDOR"):
    user = current_user(request)
    if not user or not _master_access_allowed(user) or module_level(user, "Ratecards") != "F":
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    return templates.TemplateResponse("masters/ratecard_import.html",
                                     {"request": request, "user": user, "message": msg,
                                      "owner_type": owner_type.strip().upper() if owner_type.strip().upper() in {"VENDOR", "COMPANY", "INDIVIDUAL"} else "VENDOR"})


def _vendor_code_rows(content):
    """Read the Code sheet used as the Vendor Master source."""
    workbook = openpyxl.load_workbook(BytesIO(content), data_only=True, read_only=True)
    if "Code" not in workbook.sheetnames:
        return [], [{"row": 0, "column": "Sheet", "value": "Code",
                     "message": "Workbook must contain a sheet named Code."}]
    sheet = workbook["Code"]
    rows = list(sheet.iter_rows(values_only=True))
    expected = ("Company Id", "Legal Name", "Company", "Mobile", "Email",
                "KYC", "Grade", "Status")
    header = tuple(str(value).strip() if value is not None else "" for value in (rows[0] if rows else ()))
    if header[:len(expected)] != expected:
        return [], [{"row": 1, "column": "Header", "value": ", ".join(header),
                     "message": "Code must use: " + ", ".join(expected)}]
    parsed = []
    errors = []
    seen = set()
    for number, values in enumerate(rows[1:], start=2):
        values = list(values) + [None] * (len(expected) - len(values))
        vendor_id = str(values[0]).strip() if values[0] is not None else ""
        if not vendor_id:
            continue
        if vendor_id in seen:
            errors.append({"row": number, "column": "Company Id", "value": vendor_id,
                           "message": "Duplicate Company Id."})
            continue
        seen.add(vendor_id)
        if not values[1] and not values[2]:
            errors.append({"row": number, "column": "Legal Name", "value": "",
                           "message": "Legal Name or Company is required."})
            continue
        parsed.append({
            "vendor_id": vendor_id,
            "vendor_name": str(values[1] or values[2]).strip(),
            "company_name": str(values[2] or values[1]).strip(),
            "mobile": values[3], "email": values[4], "kyc_status": values[5],
            "grade": values[6], "status": values[7],
        })
    return parsed, errors


async def vendor_master_import(request: Request, file: UploadFile = File(...)):
    user = current_user(request)
    if not user or not _master_access_allowed(user) or module_level(user, "Vendors") != "F":
        return JSONResponse({"error": "not authorized"}, status_code=403)
    rows, errors = _vendor_code_rows(await file.read())
    if errors:
        return RedirectResponse(url="/masters/vendors?msg=" + quote(errors[0]["message"]), status_code=303)
    tenant_id = user.get("tenant_id") or "TEN-RENTA-GO"
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT vendor_id,status FROM vendors WHERE tenant_id=:1", (tenant_id,))
        existing = {str(row[0]).strip(): row[1] for row in cur.fetchall()}
        for row in rows:
            status = row["status"] or existing.get(row["vendor_id"]) or "Active"
            cur.execute(
                "SELECT vendor_id FROM vendors WHERE tenant_id=:1 AND vendor_id=:2",
                (tenant_id, row["vendor_id"]),
            )
            if cur.fetchone():
                cur.execute(
                    "UPDATE vendors SET vendor_name=:1,company_name=:2,mobile=:3,email=:4,"
                    "kyc_status=:5,grade=:6,status=:7 WHERE tenant_id=:8 AND vendor_id=:9",
                    (row["vendor_name"], row["company_name"], row["mobile"], row["email"],
                     row["kyc_status"], row["grade"], status, tenant_id, row["vendor_id"]),
                )
            else:
                cur.execute(
                    "INSERT INTO vendors (vendor_id,tenant_id,vendor_name,company_name,mobile,email,"
                    "kyc_status,grade,status) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9)",
                    (row["vendor_id"], tenant_id, row["vendor_name"], row["company_name"],
                     row["mobile"], row["email"], row["kyc_status"], row["grade"], status),
                )
        audit(conn, user, "Vendor Master Imported", "VENDORS",
              f"rows={len(rows)}; sheet=Code; file={file.filename}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return RedirectResponse(url=f"/masters/vendors?msg={quote(f'Imported {len(rows)} Vendor Master rows from Code')}",
                             status_code=303)


async def ratecard_import_submit(request: Request, file: UploadFile = File(...),
                                 owner_type: str = Form("VENDOR"), owner_id: str = Form(""),
                                 vendor_id: str = Form("")):
    user = current_user(request)
    if not user or not _master_access_allowed(user) or module_level(user, "Ratecards") != "F":
        return JSONResponse({"error": "not authorized"}, status_code=403)
    content = await file.read()
    rows, errors = validate_workbook(content, file.filename or "", vendor_id or owner_id)
    if owner_type.strip().upper() == "VENDOR" and not errors:
        tenant_id = user.get("tenant_id") or "TEN-RENTA-GO"
        vendor_ids = sorted({str(row.get("company_id") or "").strip() for row in rows if row.get("company_id")})
        conn = get_connection(); cur = conn.cursor()
        if vendor_ids:
            marks = ",".join(f":{i + 2}" for i in range(len(vendor_ids)))
            cur.execute(f"SELECT vendor_id FROM vendors WHERE tenant_id=:1 AND vendor_id IN ({marks})",
                        (tenant_id,) + tuple(vendor_ids))
            found = {str(row[0]).strip() for row in cur.fetchall()}
            for missing in sorted(set(vendor_ids) - found):
                errors.append({"row": 0, "column": "Company Id", "value": missing,
                               "code": "INVALID_VENDOR", "message": "Vendor ID was not found in the tenant Vendor Master."})
        conn.close()
    if errors:
        return templates.TemplateResponse("masters/ratecard_import.html",
            {"request": request, "user": user, "message": "Import rejected", "errors": errors, "row_count": len(rows)})
    tenant_id = user.get("tenant_id") or "TEN-RENTA-GO"
    conn = get_connection()
    try:
        ids = import_rows(conn, rows, owner_type.strip().upper(), owner_id.strip() or None,
                          tenant_id, vendor_id.strip() or None, file.filename or "")
        audit(conn, user, "Rate Chart Imported", ids[0] if ids else "RATECARDS",
              f"rows={len(ids)}; owner_type={owner_type.strip().upper()}; file={file.filename}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return templates.TemplateResponse("masters/ratecard_import.html",
        {"request": request, "user": user, "message": f"Imported {len(ids)} rows", "errors": [], "row_count": len(ids)})


@router.get("/{key}/import")
def master_import_page(request: Request, key: str):
    user = current_user(request)
    cfg = _cfg(key)
    cfg = _effective_cfg(key, cfg, user)
    if not user or not _master_access_allowed(user) or not _tenant_id(user) or not cfg or cfg.get("readonly") or cfg.get("import_blocked") or cfg["table"] not in TENANT_MASTER_TABLES or module_level(user, cfg["sheet"]) != "F":
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    return templates.TemplateResponse("masters/import.html", {"request": request, "user": user, "cfg": cfg, "key": key})


@router.post("/{key}/import")
async def master_import_preview(request: Request, key: str, file: UploadFile = File(...), sheet: str = Form("")):
    user = current_user(request)
    cfg = _cfg(key)
    cfg = _effective_cfg(key, cfg, user)
    if not user or not _master_access_allowed(user) or not _tenant_id(user) or not cfg or cfg.get("readonly") or cfg.get("import_blocked") or cfg["table"] not in TENANT_MASTER_TABLES or module_level(user, cfg["sheet"]) != "F":
        return JSONResponse({"error": "not authorized"}, status_code=403)
    content = await file.read()
    filename = file.filename or "upload"
    digest = source_hash(content)
    tenant_id = _tenant_id(user)
    headers, rows, errors, mapping = parse_and_validate(content, filename, cfg, sheet.strip() or None, tenant_id)
    import_id = "IMP-" + uuid.uuid4().hex[:28].upper()
    preview_id = uuid.uuid4().hex
    plan = {"import_id": import_id, "preview_id": preview_id, "tenant_id": tenant_id,
            "user_id": user.get("user_id"), "master": key, "source_filename": filename,
            "source_hash": digest, "file_type": filename.rsplit(".", 1)[-1].lower(),
            "headers": headers, "mapping": mapping, "rows": rows}
    token = sign_preview(plan, settings.SECRET_KEY)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO master_import_history "
            "(import_id,preview_id,tenant_id,user_id,master_name,source_filename,source_file_hash,file_type,status,total_rows,valid_rows,rejected_rows,error_count) "
            "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,'PREVIEW',:9,:10,:11,:12)",
            (import_id, preview_id, tenant_id, user.get("user_id"), key, filename, digest,
             plan["file_type"], len(rows), len(rows) - len({e.get("row") for e in errors if e.get("row")}),
             len({e.get("row") for e in errors if e.get("row")}), len(errors)),
        )
        if errors:
            _record_import_errors(conn, import_id, errors)
        audit(conn, user, "MASTER_IMPORT_PREVIEW", import_id,
              f"master={key}; tenant={tenant_id}; file={filename}; hash={digest}")
        conn.commit()
    finally:
        conn.close()
    return templates.TemplateResponse("masters/import_preview.html", {
        "request": request, "user": user, "cfg": cfg, "key": key,
        "headers": headers, "rows": rows, "errors": errors, "mapping": mapping,
        "payload": token, "source_filename": filename,
    })


@router.post("/{key}/import/confirm")
async def master_import_confirm(request: Request, key: str, payload: str = Form(...), file: UploadFile = File(...)):
    user = current_user(request)
    cfg = _cfg(key)
    cfg = _effective_cfg(key, cfg, user)
    if not user or not _master_access_allowed(user) or not _tenant_id(user) or not cfg or cfg.get("readonly") or cfg.get("import_blocked") or cfg["table"] not in TENANT_MASTER_TABLES or module_level(user, cfg["sheet"]) != "F":
        return JSONResponse({"error": "not authorized"}, status_code=403)
    data, token_error = verify_preview(payload, settings.SECRET_KEY)
    if token_error:
        return RedirectResponse(url=f"/masters/{key}?msg={token_error}", status_code=303)
    try:
        rows = data["rows"]
        headers = data["headers"]
        if data["master"] != key or data["tenant_id"] != _tenant_id(user) or data.get("user_id") != user.get("user_id"):
            raise ValueError("preview context mismatch")
        content = await file.read()
        if source_hash(content) != data["source_hash"]:
            changed = get_connection()
            try:
                changed.cursor().execute("UPDATE master_import_history SET status='REJECTED',rejected_rows=total_rows,error_count=error_count+1,completed_at=SYSTIMESTAMP WHERE import_id=:1 AND status='PREVIEW'", (data["import_id"],))
                _record_import_errors(changed, data["import_id"], [{"row": 0, "code": "SOURCE_CHANGED", "message": "The confirmation file hash differs from the preview source."}])
                changed.commit()
            finally:
                changed.close()
            return RedirectResponse(url=f"/masters/{key}?msg=SOURCE_CHANGED", status_code=303)
        errors = validate_rows(headers, rows, cfg, _tenant_id(user))
    except Exception:
        return RedirectResponse(url=f"/masters/{key}?msg=invalid-import-preview", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT status,error_count FROM master_import_history WHERE import_id=:1 AND preview_id=:2 AND tenant_id=:3",
                (data["import_id"], data["preview_id"], _tenant_id(user)))
    history = cur.fetchone()
    if not history or history[0] != "PREVIEW":
        conn.close()
        return RedirectResponse(url=f"/masters/{key}?msg=PREVIEW_REPLAYED", status_code=303)
    if int(history[1] or 0) > 0:
        conn.close()
        return RedirectResponse(url=f"/masters/{key}?msg=validation-rejected", status_code=303)
    if errors:
        cur.execute("UPDATE master_import_history SET status='REJECTED', error_count=:1, rejected_rows=:2, completed_at=SYSTIMESTAMP WHERE import_id=:3",
                    (len(errors), len({e.get("row") for e in errors}), data["import_id"]))
        _record_import_errors(conn, data["import_id"], errors)
        conn.commit(); conn.close()
        return RedirectResponse(url=f"/masters/{key}?msg=validation-rejected", status_code=303)
    cur.execute("UPDATE master_import_history SET status='PROCESSING', confirmed_at=SYSTIMESTAMP WHERE import_id=:1",
                (data["import_id"],))
    conn.commit()
    custom_fields = [field for field in cfg.get("fields", []) if field.get("custom_field")]
    columns = [field["name"] for field in cfg.get("fields", []) if field["name"] in headers and not field.get("custom_field")]
    if cfg["pk"] not in columns:
        columns.insert(0, cfg["pk"])
    try:
        tenant_id = _tenant_id(user)
        inserted = updated = 0
        field_map = {field["name"]: field for field in cfg.get("fields", [])}
        for row in rows:
            values = [_import_value(field_map.get(column, {"type": "text"}), row.get(column)) for column in columns]
            cur.execute(f"SELECT {cfg['pk']} FROM {cfg['table']} WHERE tenant_id=:1 AND {cfg['pk']}=:2",
                        (tenant_id, row.get(cfg["pk"])))
            if cur.fetchone():
                updated += 1
                assignments = ",".join(f"{column}=:{index + 1}" for index, column in enumerate(columns[1:]))
                if assignments:
                    cur.execute(f"UPDATE {cfg['table']} SET {assignments} WHERE tenant_id=:{len(columns)} AND {cfg['pk']}=:{len(columns) + 1}",
                                tuple(values[1:]) + (tenant_id, values[0]))
                save_custom_values(conn, cfg.get("_metadata_master_id"), tenant_id, values[0], custom_fields, row, user.get("user_id"))
            else:
                inserted += 1
                import_columns = ["tenant_id"] + columns
                marks = ",".join(f":{index + 1}" for index in range(len(import_columns)))
                cur.execute(f"INSERT INTO {cfg['table']} ({','.join(import_columns)}) VALUES ({marks})",
                            (tenant_id,) + tuple(values))
                save_custom_values(conn, cfg.get("_metadata_master_id"), tenant_id, values[0], custom_fields, row, user.get("user_id"))
        audit(conn, user, "MASTER_IMPORT_CONFIRMED", data["import_id"],
              f"master={key}; tenant={tenant_id}; inserted={inserted}; updated={updated}")
        cur.execute("UPDATE master_import_history SET status='COMPLETED',completed_at=SYSTIMESTAMP,valid_rows=:1,inserted_rows=:2,updated_rows=:3 WHERE import_id=:4",
                    (len(rows), inserted, updated, data["import_id"]))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        failed = get_connection()
        try:
            failed.cursor().execute("UPDATE master_import_history SET status='FAILED',completed_at=SYSTIMESTAMP,error_count=error_count+1 WHERE import_id=:1", (data["import_id"],))
            failed.cursor().execute("INSERT INTO master_import_errors (error_id,import_id,error_code,message) VALUES (:1,:2,'TRANSACTION_FAILED',:3)", (uuid.uuid4().hex, data["import_id"], str(exc)[:1000]))
            failed.commit()
        finally:
            failed.close()
        raise
    finally:
        conn.close()
    return templates.TemplateResponse("masters/import_result.html", {
        "request": request, "user": user, "key": key, "import_id": data["import_id"],
        "total": len(rows), "inserted": inserted, "updated": updated,
        "rejected": 0, "errors": 0,
    })


@router.get("/imports/history")
def master_import_history(request: Request):
    user = current_user(request)
    if not user or not _master_access_allowed(user) or not _tenant_id(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT import_id,master_name,source_filename,status,total_rows,inserted_rows,updated_rows,rejected_rows,error_count,started_at FROM master_import_history WHERE tenant_id=:1 ORDER BY started_at DESC",
                (_tenant_id(user),))
    rows = cur.fetchall(); conn.close()
    return templates.TemplateResponse("masters/import_history.html", {"request": request, "user": user, "rows": rows})


@router.get("/imports/{import_id}/errors")
def master_import_errors(request: Request, import_id: str):
    user = current_user(request)
    if not user or not _master_access_allowed(user) or not _tenant_id(user):
        return JSONResponse({"error": "not authorized"}, status_code=403)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT row_number,source_field,source_value,canonical_field,error_code,message FROM master_import_errors WHERE import_id=:1 AND EXISTS (SELECT 1 FROM master_import_history h WHERE h.import_id=:2 AND h.tenant_id=:3) ORDER BY row_number,error_id",
                (import_id, import_id, _tenant_id(user)))
    rows = cur.fetchall(); conn.close()
    output = StringIO(); writer = csv.writer(output)
    writer.writerow(("row_number", "source_field", "source_value", "canonical_field", "error_code", "message"))
    writer.writerows([[_safe_csv_value(value) for value in row] for row in rows])
    return Response(output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{import_id}-errors.csv"'})


@router.get("/{key}/export")
def master_export(request: Request, key: str):
    user = current_user(request)
    cfg = _cfg(key)
    cfg = _effective_cfg(key, cfg, user)
    if not user or not _master_access_allowed(user) or not _tenant_id(user) or not cfg or module_level(user, cfg["sheet"]) is None:
        return JSONResponse({"error": "not authorized"}, status_code=403)
    if cfg["table"] not in TENANT_MASTER_TABLES:
        return JSONResponse({"error": "This master is not tenant-scoped."}, status_code=409)
    conn = get_connection()
    columns, rows = _export_rows(conn, cfg, _tenant_id(user))
    conn.close()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    writer.writerows(rows)
    return Response(output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{key}.csv"'})


@router.get("/{key}/export.xlsx")
def master_export_xlsx(request: Request, key: str):
    user = current_user(request)
    cfg = _cfg(key)
    cfg = _effective_cfg(key, cfg, user)
    if not user or not _master_access_allowed(user) or not _tenant_id(user) or not cfg or module_level(user, cfg["sheet"]) is None:
        return JSONResponse({"error": "not authorized"}, status_code=403)
    if cfg["table"] not in TENANT_MASTER_TABLES:
        return JSONResponse({"error": "This master is not tenant-scoped."}, status_code=409)
    conn = get_connection()
    columns, rows = _export_rows(conn, cfg, _tenant_id(user))
    conn.close()
    workbook = openpyxl.Workbook(write_only=True)
    sheet = workbook.create_sheet(title=cfg["title"][:31] or "Export")
    sheet.append(columns)
    for row in rows:
        sheet.append([_safe_csv_value(value) for value in row])
    stream = BytesIO()
    workbook.save(stream)
    return Response(stream.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{key}.xlsx"'})


@router.get("/designer")
def master_designer(request: Request):
    user = current_user(request)
    if not _designer_allowed(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT master_key,display_name,database_table,version,import_enabled,export_enabled,tenant_scoped FROM master_definitions WHERE active='Y' ORDER BY display_name")
    masters = cur.fetchall(); conn.close()
    return templates.TemplateResponse("masters/designer.html", {"request": request, "user": user, "masters": masters})


@router.get("/designer/{key}")
def master_designer_detail(request: Request, key: str):
    user = current_user(request)
    if not _designer_allowed(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    master_id = _designer_master_id(cur, key)
    if not master_id:
        conn.close()
        return RedirectResponse(url="/masters/designer", status_code=303)
    cur.execute("SELECT display_name,import_enabled,export_enabled,version FROM master_definitions WHERE master_id=:1", (master_id,))
    master = cur.fetchone()
    cur.execute("SELECT field_id,technical_name,display_label,excel_header,field_type,required,import_enabled,export_enabled,active,system_protected,custom_field,display_order FROM master_field_definitions WHERE master_id=:1 ORDER BY display_order,technical_name", (master_id,))
    fields = cur.fetchall(); conn.close()
    return templates.TemplateResponse("masters/designer_detail.html", {"request": request, "user": user, "key": key, "master": master, "fields": fields, "field_types": sorted(FIELD_TYPES)})


@router.post("/designer/{key}/fields")
async def master_designer_add_field(request: Request, key: str, technical_name: str = Form(...), display_label: str = Form(...), excel_header: str = Form(...), data_type: str = Form("TEXT"), required: str = Form("N"), import_enabled: str = Form("Y"), export_enabled: str = Form("Y"), aliases: str = Form(""), options: str = Form("")):
    user = current_user(request)
    if not _designer_allowed(user):
        return JSONResponse({"error": "not authorized"}, status_code=403)
    try:
        technical_name = validate_technical_name(technical_name)
        data_type = field_type(data_type)
    except ValueError as exc:
        return RedirectResponse(url=f"/masters/designer/{key}?msg={quote(str(exc))}", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    master_id = _designer_master_id(cur, key)
    if not master_id:
        conn.close(); return RedirectResponse(url="/masters/designer", status_code=303)
    cur.execute("SELECT COUNT(*) FROM master_field_definitions WHERE master_id=:1 AND technical_name=:2", (master_id, technical_name))
    if cur.fetchone()[0]:
        conn.close(); return RedirectResponse(url=f"/masters/designer/{key}?msg=field-exists", status_code=303)
    cur.execute("SELECT NVL(MAX(display_order),0)+1 FROM master_field_definitions WHERE master_id=:1", (master_id,))
    order = cur.fetchone()[0]
    field_id = "MF-" + uuid.uuid4().hex[:28].upper()
    cur.execute("INSERT INTO master_field_definitions (field_id,master_id,technical_name,display_label,excel_header,field_type,required,active,display_enabled,import_enabled,export_enabled,searchable,filterable,sortable,display_order,system_protected,generated_field,custom_field,created_at,created_by,updated_at,updated_by) VALUES (:1,:2,:3,:4,:5,:6,:7,'Y','Y',:8,:9,'N','N','N',:10,'N','N','Y',SYSTIMESTAMP,:11,SYSTIMESTAMP,:11)",
                (field_id, master_id, technical_name, display_label.strip(), excel_header.strip(), data_type, "Y" if required.upper() in {"Y", "YES"} else "N", "Y" if import_enabled.upper() in {"Y", "YES"} else "N", "Y" if export_enabled.upper() in {"Y", "YES"} else "N", order, user.get("user_id"), user.get("user_id")))
    for alias in [item.strip() for item in aliases.split(",") if item.strip()]:
        cur.execute("INSERT INTO master_field_aliases (alias_id,field_id,alias_value,normalized_alias) VALUES (:1,:2,:3,:4)", (uuid.uuid4().hex, field_id, alias, normalize_header(alias)))
    for number, option in enumerate([item.strip() for item in options.split(",") if item.strip()], 1):
        cur.execute("INSERT INTO master_field_options (option_id,field_id,option_value,display_label,display_order) VALUES (:1,:2,:3,:4,:5)", (uuid.uuid4().hex, field_id, option, option, number))
    _designer_audit(conn, user, master_id, "FIELD_CREATED", field_id, None, technical_name)
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/masters/designer/{key}?msg=field-created", status_code=303)


@router.post("/designer/{key}/publish")
def master_designer_publish(request: Request, key: str):
    user = current_user(request)
    if not _designer_allowed(user):
        return JSONResponse({"error": "not authorized"}, status_code=403)
    conn = get_connection(); cur = conn.cursor()
    master_id = _designer_master_id(cur, key)
    if not master_id:
        conn.close(); return RedirectResponse(url="/masters/designer", status_code=303)
    snapshot = snapshot_config(conn, master_id)
    cur.execute("SELECT NVL(MAX(version_no),0)+1 FROM master_configuration_versions WHERE master_id=:1", (master_id,))
    version = int(cur.fetchone()[0])
    cur.execute("UPDATE master_configuration_versions SET status='SUPERSEDED' WHERE master_id=:1 AND status='PUBLISHED'", (master_id,))
    version_id = "MCV-" + uuid.uuid4().hex[:28].upper()
    cur.execute("INSERT INTO master_configuration_versions (config_version_id,master_id,version_no,status,config_json,created_by,published_at,published_by) VALUES (:1,:2,:3,'PUBLISHED',:4,:5,SYSTIMESTAMP,:6)", (version_id, master_id, version, json.dumps(snapshot), user.get("user_id"), user.get("user_id")))
    cur.execute("UPDATE master_definitions SET version=:1,updated_at=SYSTIMESTAMP,updated_by=:2 WHERE master_id=:3", (version, user.get("user_id"), master_id))
    _designer_audit(conn, user, master_id, "CONFIG_PUBLISHED", None, None, f"version={version}", version_id)
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/masters/designer/{key}?msg=published", status_code=303)


@router.get("/designer/{key}/fields/{field_id}/edit")
def master_designer_edit_field(request: Request, key: str, field_id: str):
    user = current_user(request)
    if not _designer_allowed(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT field_id,technical_name,display_label,excel_header,field_type,required,import_enabled,export_enabled,system_protected FROM master_field_definitions WHERE field_id=:1", (field_id,))
    field = cur.fetchone(); conn.close()
    if not field:
        return RedirectResponse(url=f"/masters/designer/{key}?msg=not-found", status_code=303)
    return templates.TemplateResponse("masters/designer_field.html", {"request": request, "user": user, "key": key, "field": field, "field_types": sorted(FIELD_TYPES)})


@router.post("/designer/{key}/fields/{field_id}/edit")
def master_designer_update_field(request: Request, key: str, field_id: str, display_label: str = Form(...), excel_header: str = Form(...), data_type: str = Form("TEXT"), required: str = Form("N"), import_enabled: str = Form("Y"), export_enabled: str = Form("Y"), aliases: str = Form(""), options: str = Form("")):
    user = current_user(request)
    if not _designer_allowed(user):
        return JSONResponse({"error": "not authorized"}, status_code=403)
    try:
        data_type = field_type(data_type)
    except ValueError as exc:
        return RedirectResponse(url=f"/masters/designer/{key}/fields/{field_id}/edit?msg={quote(str(exc))}", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT master_id,technical_name,system_protected,display_label,excel_header FROM master_field_definitions WHERE field_id=:1", (field_id,))
    old = cur.fetchone()
    if not old:
        conn.close(); return RedirectResponse(url=f"/masters/designer/{key}?msg=not-found", status_code=303)
    if old[2] == "Y":
        conn.close(); return RedirectResponse(url=f"/masters/designer/{key}?msg=protected-field", status_code=303)
    cur.execute("UPDATE master_field_definitions SET display_label=:1,excel_header=:2,field_type=:3,required=:4,import_enabled=:5,export_enabled=:6,updated_at=SYSTIMESTAMP,updated_by=:7 WHERE field_id=:8",
                (display_label.strip(), excel_header.strip(), data_type, "Y" if required.upper() in {"Y", "YES"} else "N", "Y" if import_enabled.upper() in {"Y", "YES"} else "N", "Y" if export_enabled.upper() in {"Y", "YES"} else "N", user.get("user_id"), field_id))
    if old[3] != display_label.strip() or old[4] != excel_header.strip():
        _designer_audit(conn, user, old[0], "FIELD_UPDATED", field_id, f"label={old[3]};header={old[4]}", f"label={display_label.strip()};header={excel_header.strip()}")
    cur.execute("SELECT alias_id,normalized_alias FROM master_field_aliases WHERE field_id=:1 AND active='Y'", (field_id,))
    existing_aliases = {row[1]: row[0] for row in cur.fetchall()}
    requested_aliases = {item.strip() for item in aliases.split(",") if item.strip()}
    for alias in requested_aliases:
        normalized = normalize_header(alias)
        if normalized not in existing_aliases:
            cur.execute("INSERT INTO master_field_aliases (alias_id,field_id,alias_value,normalized_alias) VALUES (:1,:2,:3,:4)", (uuid.uuid4().hex, field_id, alias, normalized))
            _designer_audit(conn, user, old[0], "ALIAS_ADDED", field_id, None, alias)
    for normalized, alias_id in existing_aliases.items():
        if normalized not in {normalize_header(item) for item in requested_aliases}:
            cur.execute("UPDATE master_field_aliases SET active='N' WHERE alias_id=:1", (alias_id,))
            _designer_audit(conn, user, old[0], "ALIAS_REMOVED", field_id, normalized, None)
    cur.execute("SELECT option_id,option_value FROM master_field_options WHERE field_id=:1 AND active='Y'", (field_id,))
    existing_options = {row[1]: row[0] for row in cur.fetchall()}
    requested_options = {item.strip() for item in options.split(",") if item.strip()}
    for option in requested_options:
        if option not in existing_options:
            cur.execute("INSERT INTO master_field_options (option_id,field_id,option_value,display_label,display_order) VALUES (:1,:2,:3,:4,:5)", (uuid.uuid4().hex, field_id, option, option, len(existing_options) + 1))
            _designer_audit(conn, user, old[0], "OPTION_ADDED", field_id, None, option)
    for option, option_id in existing_options.items():
        if option not in requested_options:
            cur.execute("UPDATE master_field_options SET active='N' WHERE option_id=:1", (option_id,))
            _designer_audit(conn, user, old[0], "OPTION_DISABLED", field_id, option, None)
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/masters/designer/{key}?msg=field-updated", status_code=303)


@router.post("/designer/{key}/fields/{field_id}/toggle")
def master_designer_toggle_field(request: Request, key: str, field_id: str):
    user = current_user(request)
    if not _designer_allowed(user):
        return JSONResponse({"error": "not authorized"}, status_code=403)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT master_id,system_protected,active FROM master_field_definitions WHERE field_id=:1", (field_id,))
    row = cur.fetchone()
    if not row or row[1] == "Y":
        conn.close(); return RedirectResponse(url=f"/masters/designer/{key}?msg=protected-field", status_code=303)
    value = "N" if row[2] == "Y" else "Y"
    cur.execute("UPDATE master_field_definitions SET active=:1,updated_at=SYSTIMESTAMP,updated_by=:2 WHERE field_id=:3", (value, user.get("user_id"), field_id))
    _designer_audit(conn, user, row[0], "FIELD_ENABLED" if value == "Y" else "FIELD_DISABLED", field_id, row[2], value)
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/masters/designer/{key}?msg=field-updated", status_code=303)


@router.post("/designer/{key}/fields/{field_id}/move")
def master_designer_move_field(request: Request, key: str, field_id: str, direction: str = Form(...)):
    user = current_user(request)
    if not _designer_allowed(user):
        return JSONResponse({"error": "not authorized"}, status_code=403)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT master_id,display_order,system_protected FROM master_field_definitions WHERE field_id=:1", (field_id,))
    row = cur.fetchone()
    if not row:
        conn.close(); return RedirectResponse(url=f"/masters/designer/{key}?msg=not-found", status_code=303)
    step = -1 if direction.lower() == "up" else 1
    cur.execute("SELECT field_id,display_order FROM master_field_definitions WHERE master_id=:1 AND display_order=:2", (row[0], row[1] + step))
    other = cur.fetchone()
    if other:
        cur.execute("UPDATE master_field_definitions SET display_order=:1 WHERE field_id=:2", (row[1], other[0]))
        cur.execute("UPDATE master_field_definitions SET display_order=:1 WHERE field_id=:2", (other[1], field_id))
        _designer_audit(conn, user, row[0], "ORDER_CHANGED", field_id, row[1], other[1])
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/masters/designer/{key}?msg=order-updated", status_code=303)


@router.get("/designer/{key}/template")
def master_designer_template(request: Request, key: str):
    user = current_user(request)
    cfg = _effective_cfg(key, _cfg(key), user)
    if not _designer_allowed(user) or not cfg:
        return JSONResponse({"error": "not authorized"}, status_code=403)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = cfg["title"][:31] or "Import"
    fields = [field for field in cfg.get("fields", []) if field.get("import_enabled") and not field.get("system_protected") and not field.get("generated_field")]
    sheet.append([field.get("excel_header") or field.get("label") or field["name"] for field in fields])
    notes = workbook.create_sheet("Validation Notes")
    notes.append(["Excel Header", "Type", "Required", "Help"])
    for field in fields:
        notes.append([field.get("excel_header") or field.get("label"), field.get("type", "TEXT"), "Yes" if field.get("required") else "No", field.get("help_text") or ""])
    stream = BytesIO(); workbook.save(stream)
    return Response(stream.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{key}-import-template.xlsx"'})


@router.get("/{key}")
def master_list(request: Request, key: str, q: str = "", page: int = 1):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _master_access_allowed(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
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

    selected_cols = [cfg["pk"]] + [c for c, _ in cfg["list"] if c != cfg["pk"]]
    cols = ", ".join(selected_cols)
    dropdown_options = {}
    for dropdown_col in cfg.get("dropdown_filters") or []:
        dropdown_where = " WHERE tenant_id=:1 AND " if cfg["table"] in TENANT_MASTER_TABLES else " WHERE "
        dropdown_params = (_tenant_id(user),) if cfg["table"] in TENANT_MASTER_TABLES else ()
        cur.execute(
            f"SELECT DISTINCT {dropdown_col} FROM {cfg['table']} "
            f"{dropdown_where}{dropdown_col} IS NOT NULL ORDER BY {dropdown_col}", dropdown_params or None
        )
        dropdown_options[dropdown_col] = [str(row[0]) for row in cur.fetchall()]
    # Quick search (q): OR across the configured search columns.
    # Per-field filters (f_<col>): AND-ed together, so any one field alone
    # works and several fields narrow the result further.
    params, conds = [], []
    if cfg["table"] in TENANT_MASTER_TABLES:
        params.append(_tenant_id(user))
        conds.append("tenant_id=:1")
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
                               "value": val,
                               "options": dropdown_options.get(fcol, [])})
    active_date_filters = []
    for date_name, date_label in (cfg.get("date_filters") or []):
        value = (request.query_params.get(date_name) or "").strip()
        if value:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                value = ""
            else:
                params.append(value)
                if date_name == "from_date":
                    conds.append(f"audit_date>=TO_DATE(:{len(params)},'YYYY-MM-DD')")
                elif date_name == "to_date":
                    conds.append(f"audit_date<TO_DATE(:{len(params)},'YYYY-MM-DD')+1")
        active_date_filters.append({"name": date_name, "label": date_label,
                                    "value": value})
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
    for f in active_date_filters:
        if f["value"]:
            qs_parts.append(f["name"] + "=" + quote(f["value"]))
    qs = "&".join(qs_parts)
    return templates.TemplateResponse(
        "masters/list.html",
        {"request": request, "user": user,
         "cfg": {"key": key, "title": cfg["title"], "pk": cfg["pk"], "list": cfg["list"],
                   "filters": active_filters, "date_filters": active_date_filters,
                   "readonly": cfg.get("readonly", False),
                   "import_blocked": cfg.get("import_blocked", False)},
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
    if not _master_access_allowed(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
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
    if not _master_access_allowed(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    cfg = _cfg(key)
    if not cfg:
        return RedirectResponse(url="/masters", status_code=303)
    if not _editable(user, cfg):
        return RedirectResponse(url=f"/masters/{key}?msg=not-allowed", status_code=303)

    form = dict(await _form_pairs(request))
    values = _parse_form(cfg, form)
    values.update(cfg.get("defaults") or {})
    if key == "company-ratecards":
        values["owner_type"] = "COMPANY"
        values["owner_id"] = values.get("company_id")
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
    if not _master_access_allowed(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
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
    if not _master_access_allowed(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
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
    if key == "company-ratecards":
        values["owner_type"] = "COMPANY"
        values["owner_id"] = values.get("company_id")
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
    if not _master_access_allowed(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
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
    if not _master_access_allowed(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
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
