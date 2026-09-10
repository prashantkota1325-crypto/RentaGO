"""
RentaGO Web - xlsm -> Oracle import tool.

Reads RentaGO_Prototype_new.xlsm with openpyxl (values only) and loads the
master/transaction data into Oracle. Uses the app DB layer (native oracledb
when available, otherwise the SQL*Plus fallback) and streams INSERT statements
in bulk so it works even in restricted environments.

Usage:
    python import/import_xlsm.py [path_to_xlsm] [--apply]
    --apply  actually run against the DB; otherwise only write import/import_data.sql
"""

import argparse
import os
import sys
from datetime import date, datetime, time

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

# ---------------------------------------------------------------------------
# Value -> SQL literal helpers
# ---------------------------------------------------------------------------
def clean(v):
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return v


def lit(v, kind="text"):
    """Return a SQL literal for a value."""
    if v is None:
        return "NULL"
    if kind == "number":
        try:
            return str(float(v))
        except Exception:
            return "NULL"
    if kind == "date":
        return fmt_date(v)
    if kind == "dt":
        return fmt_dt(v)
    # text
    s = str(v).replace("'", "''")
    return "'" + s + "'"


def fmt_date(v):
    if isinstance(v, datetime):
        return f"TO_DATE('{v:%Y-%m-%d}','YYYY-MM-DD')"
    if isinstance(v, date):
        return f"TO_DATE('{v:%Y-%m-%d}','YYYY-MM-DD')"
    return "NULL"


def fmt_dt(v):
    if isinstance(v, datetime):
        return f"TO_TIMESTAMP('{v:%Y-%m-%d %H:%M:%S}','YYYY-MM-DD HH24:MI:SS')"
    return "NULL"


# ---------------------------------------------------------------------------
# Table definitions: (sheet, header_row, oracle_table, [(db_col, sheet_header, kind)])
#   kind: text | number | date | dt
# ---------------------------------------------------------------------------
TABLES = []


def def_table(sheet, header_row, table, cols):
    TABLES.append((sheet, header_row, table, cols))


def_t = def_table

# Users: The Users sheet data is misaligned with its header (values sit one
# column left of the header names), so map by explicit column index:
#   1 user no, 2 user id, 3 name, 4 email, 6 office/hq, 5 role,
#   7 designation, 8 status, 9 mobile, 10 password hash, 11 password vault
def_t("Users", 1, "users", [
    ("user_no", 1, "number"),
    ("user_id", 2, "text"),
    ("name", 3, "text"),
    ("email", 4, "text"),
    ("company_name", 6, "text"),
    ("role", 5, "text"),
    ("emp_id", 7, "text"),
    ("department", 7, "text"),
    ("status", 8, "text"),
    ("mobile", 9, "text"),
    ("password_hash", 10, "text"),
    ("password_vault", 11, "text"),
])

# Bookings (69 cols)
def_t("Bookings", 1, "bookings", [
    ("booking_id", "Booking ID", "text"),
    ("booking_date", "Booking Date", "date"),
    ("booking_type", "Booking Type", "text"),
    ("company_name", "Company Name", "text"),
    ("entity_name", "Entity Name", "text"),
    ("company_id", "Company ID", "text"),
    ("guest_name_1", "Guest Name 1", "text"),
    ("guest_name_2", "Guest Name 2", "text"),
    ("guest_name_3", "Guest Name 3", "text"),
    ("guest_name_4", "Guest Name 4", "text"),
    ("guest_name_5", "Guest Name 5", "text"),
    ("guest_email", "Guest Email", "text"),
    ("guest_contact", "Guest Contact", "text"),
    ("emp_guest_id", "Emp/Guest ID", "text"),
    ("admin_name", "Admin Name", "text"),
    ("admin_email", "Admin Email", "text"),
    ("admin_contact", "Admin Contact", "text"),
    ("pickup_1", "Guest Pickup", "text"),
    ("pickup_2", "Pickup 2", "text"),
    ("pickup_address", "Pickup Address", "text"),
    ("pickup_city", "Pickup City", "text"),
    ("pickup_state", "Pickup State", "text"),
    ("pickup_date", "Pickup Date", "date"),
    ("pickup_time", "Pickup Time", "text"),
    ("no_of_pickups", "No. of Pickups", "text"),
    ("drop_2", "Drop 2", "text"),
    ("drop_3", "Drop 3", "text"),
    ("drop_4", "Drop 4", "text"),
    ("drop_5", "Drop 5", "text"),
    ("drop_address", "Drop Address", "text"),
    ("drop_city", "Drop City", "text"),
    ("drop_state", "Drop State", "text"),
    ("drop_date", "Drop Date", "date"),
    ("drop_time", "Drop Time", "text"),
    ("vehicle_type", "Vehicle Type", "text"),
    ("vehicle_reg_no", "Vehicle Reg No", "text"),
    ("package_type", "Package Type", "text"),
    ("area_code", "Area", "text"),
    ("vendor_name", "Vendor Name", "text"),
    ("vendor_contact", "Vendor Contact", "text"),
    ("vendor_email", "Vendor Email", "text"),
    ("vendor_pkg_type", "Vendor Pkg Type", "text"),
    ("driver_name", "Driver Name", "text"),
    ("driver_contact", "Driver Contact", "text"),
    ("vehicle_no", "Vehicle No.", "text"),
    ("driver_reporting_time", "Driver Reporting Time", "text"),
    ("pickup_start_time", "Pickup Start Time", "text"),
    ("pickup_start_km", "Pickup Start Km", "number"),
    ("driver_instructions", "Instructions", "text"),
    ("step1_time", "Step1 Time", "dt"),
    ("booking_status", "Booking Status", "text"),
    ("status_reason", "Status Reason", "text"),
    ("done_by_booking", "Done By Booking", "text"),
    ("done_by_vendor", "Done By Vendor", "text"),
    ("done_by_driver", "Done By Driver&Vehicle", "text"),
    ("driver_live_location", "Driver Live Location", "text"),
    ("guest_live_location", "Guest Live Location", "text"),
    ("location_sync", "Location Sync Status", "text"),
    ("cancellation_reason", "Cancellation Reason", "text"),
    ("cancellation_date", "Cancellation Date", "date"),
    ("flight_details", "Flight Details", "text"),
])

# Companies
def_t("Companies", 2, "companies", [
    ("company_id", "Company ID", "text"),
    ("company_name", "Company Name", "text"),
    ("legal_name", "Legal Name", "text"),
    ("gst", "GST", "text"),
    ("pan", "PAN", "text"),
    ("industry", "Industry", "text"),
    ("city", "City", "text"),
    ("state", "State", "text"),
    ("booker_name", "Booker Name", "text"),
    ("booker_email", "Email", "text"),
    ("booker_phone", "Phone", "text"),
    ("guest_name", "Guest Name", "text"),
    ("guest_email", "Email", "text"),
    ("guest_phone", "Phone", "text"),
    ("credit_limit", "Credit Limit", "number"),
    ("credit_days", "Credit Days", "number"),
    ("account_manager", "Account Manager", "text"),
    ("status", "Status", "text"),
])

# Employees
def_t("Employees", 1, "employees", [
    ("emp_id", "Employee/Guest ID", "text"),
    ("company_name", "Company Name", "text"),
    ("company_id", "Company ID", "text"),
    ("emp_code", "Emp Code", "text"),
    ("guest_name", "Guest Name", "text"),
    ("guest_mobile", "Guest Mobile No.", "text"),
    ("guest_email", "Guest Email", "text"),
    ("admin_name", "Admin Name", "text"),
    ("admin_mobile", "Admin Mobile No.", "text"),
    ("admin_email", "Admin Email", "text"),
    ("pickup_location", "Pickup Location", "text"),
    ("drop_location", "Drop Location", "text"),
    ("shift_timing", "Shift Timing", "text"),
    ("emergency_contact", "Emergency Contact", "text"),
    ("status", "Status", "text"),
])

# Drivers
def_t("Drivers", 2, "drivers", [
    ("driver_id", "Driver ID", "text"),
    ("vendor_id", "Vendor ID", "text"),
    ("driver_name", "Name", "text"),
    ("mobile", "Mobile", "text"),
    ("license_no", "License No", "text"),
    ("license_expiry", "License Expiry", "date"),
    ("aadhaar_ref", "Aadhaar Ref", "text"),
    ("police_verification", "Police Verification", "text"),
    ("background_check", "Background Check", "text"),
    ("rating", "Rating", "text"),
    ("status", "Status", "text"),
])

# Vendors
def_t("Vendors", 3, "vendors", [
    ("vendor_id", "Vendor ID", "text"),
    ("vendor_name", "Vendor Name", "text"),
    ("company_name", "Company Name", "text"),
    ("pan", "PAN", "text"),
    ("gst", "GST", "text"),
    ("mobile", "Mobile", "text"),
    ("email", "Email", "text"),
    ("address", "Address", "text"),
    ("bank_account", "Bank Account", "text"),
    ("ifsc", "IFSC", "text"),
    ("kyc_status", "KYC Status", "text"),
    ("agreement_status", "Agreement Status", "text"),
    ("grade", "Grade", "text"),
    ("rating", "Rating", "text"),
    ("status", "Status", "text"),
])

# Vehicles
def_t("Vehicles", 2, "vehicles", [
    ("vehicle_id", "Vehicle ID", "text"),
    ("reg_number", "Reg Number", "text"),
    ("make", "Make", "text"),
    ("model", "Model", "text"),
    ("variant", "Variant", "text"),
    ("fuel", "Fuel", "text"),
    ("ev_ice", "EV/ICE", "text"),
    ("v_year", "Year", "text"),
    ("seats", "Seats", "number"),
    ("category", "Category", "text"),
    ("vendor_id", "Vendor ID", "text"),
    ("insurance_exp", "Insurance Exp", "date"),
    ("permit_exp", "Permit Exp", "date"),
    ("fitness_exp", "Fitness Exp", "date"),
    ("puc_exp", "PUC Exp", "date"),
    ("status", "Status", "text"),
])

# Individual
def_t("Individual", 1, "individuals", [
    ("individual_id", "Individual ID", "text"),
    ("company_name", "Company Name", "text"),
    ("company_id", "Company ID", "text"),
    ("booking_id", "Booking ID", "text"),
    ("guest_name", "Guest Name", "text"),
    ("guest_contact", "Guest Contact", "text"),
    ("guest_email", "Guest Email", "text"),
    ("admin_name", "Admin Name", "text"),
    ("admin_contact", "Admin Contact", "text"),
    ("admin_email", "Admin Email", "text"),
    ("pickup_location", "Pickup Location", "text"),
    ("drop_location", "Drop Location", "text"),
    ("created_date", "Created Date", "date"),
    ("status", "Status", "text"),
    ("done_by", "Done By", "text"),
    ("booking_type", "Booking Type", "text"),
])

# Leads
def_t("Leads", 3, "leads", [
    ("lead_id", "Lead ID", "text"),
    ("company", "Company", "text"),
    ("industry", "Industry", "text"),
    ("city", "City", "text"),
    ("contact", "Contact", "text"),
    ("phone", "Phone", "text"),
    ("requirement", "Requirement", "text"),
    ("est_vehicles", "Est Vehicles", "number"),
    ("est_monthly_rev", "Est Monthly Revenue", "number"),
    ("est_contribution", "Est Contribution %", "number"),
    ("sales_owner", "Sales Owner", "text"),
    ("stage", "Stage", "text"),
    ("probability", "Probability", "text"),
    ("expected_close", "Expected Close", "date"),
    ("next_followup", "Next Follow-up", "date"),
    ("notes", "Notes", "text"),
    ("weighted_value", "Weighted Value", "number"),
    ("funnel_status", "Funnel Status", "text"),
])

# Contacts
def_t("Contacts", 2, "contacts", [
    ("contact_id", "Contact ID", "text"),
    ("company_id", "Company ID", "text"),
    ("contact_name", "Name", "text"),
    ("designation", "Designation", "text"),
    ("department", "Department", "text"),
    ("email", "Email", "text"),
    ("mobile", "Mobile", "text"),
    ("approval_authority", "Approval Authority", "text"),
    ("status", "Status", "text"),
])

# Contracts
def_t("Contracts", 2, "contracts", [
    ("contract_id", "Contract ID", "text"),
    ("company_id", "Company ID", "text"),
    ("contract_no", "Contract No", "text"),
    ("start_date", "Start Date", "date"),
    ("end_date", "End Date", "date"),
    ("service_type", "Service Type", "text"),
    ("min_commitment", "Min Commitment", "text"),
    ("credit_days", "Credit Days", "number"),
    ("sla_pct", "SLA %", "text"),
    ("status", "Status", "text"),
])

# RateCards
def_t("RateCards", 3, "ratecards", [
    ("rate_card_id", "Rate ID", "text"),
    ("company_id", "Company ID", "text"),
    ("category", "Vehicle Category", "text"),
    ("price_1", "Customer Rate", "number"),
    ("price_2", "Vendor Cost", "number"),
    ("price_3", "Contribution", "number"),
    ("multiplier", "Contribution %", "number"),
])

# Trips (real header at row 3; rows 1-2 are junk/blank)
def_t("Trips", 3, "trips", [
    ("trip_id", "Trip ID", "text"),
    ("booking_id", "Booking ID", "text"),
    ("guest_name", "Guest Name", "text"),
    ("pickup_date", "Pickup Date", "date"),
    ("pickup_address", "Pickup Address", "text"),
    ("drop_address", "Drop Address", "text"),
    ("driver_name", "Driver Name", "text"),
    ("vehicle_no", "Vehicle No.", "text"),
    ("booking_status", "Booking Status", "text"),
    ("customer_signature", "Customer Signature (Y/N)", "text"),
    ("feedback_form", "Feedback Google Form", "text"),
    ("google_maps_link", "Google Maps Link", "text"),
    ("trip_status", "Trip Status", "text"),
    ("driver_mobile", "Driver Mobile No.", "text"),
    ("driver_reporting_time", "Driver Reporting Time", "text"),
    ("pickup_start_time", "Pickup Start Time", "text"),
    ("pickup_start_km", "Pickup Start Km", "number"),
    ("drop_end_time", "Drop End Time", "text"),
    ("drop_end_km", "Drop End Km", "number"),
    ("extra_kms", "Extra Kms", "number"),
    ("extra_hrs", "Extra Hrs", "number"),
    ("outstation_extra_kms", "Outstation Extra Kms", "number"),
    ("outstation_extra_hrs", "Outstation Extra Hrs", "number"),
    ("garage_kms", "Garage Kms", "number"),
    ("drivers_allowance", "Drivers Allowance", "number"),
    ("night_halt", "Night Halt", "number"),
    ("toll", "Toll", "number"),
    ("parking", "Parking", "number"),
    ("trip_remarks", "Trip Remarks", "text"),
])

# Invoices
def_t("Invoices", 1, "invoices", [
    ("invoice_id", "Invoice ID", "text"),
    ("booking_id", "Booking ID", "text"),
    ("guest_name", "Guest Name", "text"),
    ("company_name", "Company Name", "text"),
    ("pickup_address", "Pickup Address", "text"),
    ("drop_address", "Drop Address", "text"),
    ("pickup_date", "Pickup Date", "date"),
    ("pickup_time", "Pickup Time", "text"),
    ("vehicle_type", "Vehicle Type", "text"),
    ("package_type", "Package Type", "text"),
    ("cancellation_reason", "Cancellation Reason", "text"),
    ("cancellation_date", "Cancellation Date", "date"),
    ("cancellation_policy", "Cancellation Policy", "text"),
    ("original_amount", "Original Amount", "number"),
    ("cancellation_charges", "Cancellation Charges", "number"),
    ("refund_amount", "Refund Amount", "number"),
    ("invoice_status", "Invoice Status", "text"),
    ("payment_status", "Payment Status", "text"),
    ("trip_end_date", "Trip End Date", "date"),
    ("vendor_expense_deadline", "Vendor Expense Deadline", "date"),
    ("final_bill_deadline", "Final Bill Deadline", "date"),
    ("toll", "Toll", "number"),
    ("parking", "Parking", "number"),
    ("extra_kms", "Extra Kms", "number"),
    ("extra_hours", "Extra Hours", "number"),
    ("other_expenses", "Other Expenses", "number"),
    ("total_vendor_expenses", "Total Vendor Expenses", "number"),
    ("final_amount", "Final Amount", "number"),
    ("vendor_submitted_on", "Vendor Submitted On", "date"),
    ("final_invoice_sent_on", "Final Invoice Sent On", "date"),
])

# Payments
def_t("Payments", 3, "payments", [
    ("payment_id", "Payment ID", "text"),
    ("pay_type", "Type", "text"),
    ("pay_date", "Date", "date"),
    ("ref_id", "Ref ID (Invoice/Trip)", "text"),
    ("counterparty", "Counterparty", "text"),
    ("amount", "Amount", "number"),
    ("pay_method", "Method", "text"),
    ("pay_status", "Status", "text"),
    ("notes", "Notes", "text"),
])

# Login log (only log rows already present)
def_t("LoginLogout Log", 1, "login_log", [
    ("log_id", "Log ID", "text"),
    ("user_id", "User ID", "text"),
    ("emp_id", "Emp ID", "text"),
    ("user_name", "User Name", "text"),
    ("role", "Role", "text"),
    ("login_dt", "Login Date/Time", "dt"),
    ("logout_dt", "Logout Date/Time", "dt"),
    ("hours_worked", "Hours Worked", "number"),
    ("log_date", "Date", "date"),
])


# ---------------------------------------------------------------------------
# Roles matrix (wide format -> long roles table)
# ---------------------------------------------------------------------------
ROLE_COLS = ["Super Admin", "CEO", "Sales", "Operations", "Finance", "Vendor Manager",
             "HR", "Customer Service", "Compliance", "Corporate Admin", "Vendor",
             "Driver", "Investor", "HQ"]


def import_roles(ws, out, table="roles"):
    hr = 5
    hdr = next(ws.iter_rows(min_row=hr, max_row=hr, max_col=30, values_only=True))
    # map role name -> column index
    idx = {}
    for c, v in enumerate(hdr, start=1):
        if v is not None and str(v).strip() in ROLE_COLS:
            idx[str(v).strip()] = c
    for row_vals in ws.iter_rows(min_row=hr + 1, max_col=30, values_only=True):
        sheetname = row_vals[0]
        if sheetname is None or str(sheetname).strip() == "":
            continue
        sheetname = str(sheetname).strip()
        for role, col in idx.items():
            val = row_vals[col - 1] if col <= len(row_vals) else None
            # SOP 2.2: F = full, V = view, blank = NO access (NULL).
            if val is None or str(val).strip() == "":
                out.append(
                    f"INSERT INTO {table} (sheet, role_code, access_level) VALUES "
                    f"({lit(sheetname)}, {lit(role)}, NULL);"
                )
                continue
            a = str(val).strip().upper()[:1]
            if a not in ("F", "V"):
                a = "V"
            out.append(
                f"INSERT INTO {table} (sheet, role_code, access_level) VALUES "
                f"({lit(sheetname)}, {lit(role)}, {lit(a)});"
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
# Collapse sheets that stack duplicate blocks by dropping repeat primary keys.
# Implemented as a record of (key value) previously emitted for the table.
DEDUPE_KEYS = {
    "companies": "company_id",
    "drivers": "driver_id",
    "vendors": "vendor_id",
    "vehicles": "vehicle_no",
}


def write_sql(wb, path):
    chunks = []
    total = 0
    for sheet, header_row, table, cols in TABLES:
        if sheet not in wb.sheetnames:
            print(f"[skip] {sheet} not in workbook")
            continue
        ws = wb[sheet]
        # Read header row as a streamed row.
        hdr_vals = next(ws.iter_rows(min_row=header_row, max_row=header_row,
                                     max_col=120, values_only=True))
        hm = {}
        for c in range(len(hdr_vals)):
            v = hdr_vals[c]
            if v is not None and str(v).strip() != "":
                hm[str(v).strip().lower()] = c + 1
        need_col = max(hm.values()) if hm else 120
        seen = set()
        key_col = DEDUPE_KEYS.get(table)
        first_col = cols[0][0]
        first_header = cols[0][1] if isinstance(cols[0][1], str) else None
        n = 0
        empty_streak = 0
        seq = 0
        for row_vals in ws.iter_rows(min_row=header_row + 1, max_col=need_col,
                                     values_only=True):
            if row_vals is None or not any(v is not None and str(v).strip() != "" for v in row_vals):
                empty_streak += 1
                if empty_streak >= 15:
                    break
                continue
            empty_streak = 0
            db_cols = []
            vals = []
            skip = None
            key_raw = None
            for db_col, header, kind in cols:
                if isinstance(header, int):
                    col = header if header <= len(row_vals) else None
                else:
                    col = hm.get(header.lower())
                v = clean(row_vals[col - 1]) if col else None
                if db_col == "user_no":
                    seq += 1
                    v = seq
                if key_col and db_col == key_col:
                    skip = v
                    key_raw = row_vals[col - 1] if col and col <= len(row_vals) else None
                db_cols.append(db_col)
                vals.append(lit(v, kind))
            if key_col and skip is not None:
                if skip in seen:
                    n += 1
                    continue
                seen.add(skip)
            if first_col == "user_no":
                chunks.append(
                    f"INSERT INTO {table} ({', '.join(db_cols)}) VALUES ({', '.join(vals)});"
                )
                n += 1
                continue
            if first_header:
                fc = hm.get(first_header.lower())
                fv = row_vals[fc - 1] if fc and fc <= len(row_vals) else None
                if fv is not None and str(fv).strip().lower() == first_header.strip().lower():
                    n += 1
                    continue
            chunks.append(
                f"INSERT INTO {table} ({', '.join(db_cols)}) VALUES ({', '.join(vals)});"
            )
            n += 1
        print(f"[{table}] {n} rows")
        total += n

    # Roles matrix (long form)
    if "Roles" in wb.sheetnames:
        before = len(chunks)
        import_roles(wb["Roles"], chunks, "roles")
        print(f"[roles] {len(chunks)-before} rows")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(chunks))
        f.write("\nCOMMIT;\n")
    print(f"\nWrote {total} data rows to {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=settings.WORKBOOK_PATH)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    wb = openpyxl.load_workbook(args.path, data_only=True, read_only=True)
    out_sql = os.path.join(os.path.dirname(os.path.abspath(__file__)), "import_data.sql")
    write_sql(wb, out_sql)
    wb.close()

    if args.apply:
        from app.db import run_script
        print("Applying to database...")
        with open(out_sql, encoding="utf-8") as f:
            sql = f.read()
        run_script(sql)
        print("Done.")


if __name__ == "__main__":
    main()
