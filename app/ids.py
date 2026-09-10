"""Record ID generators shared by the booking flow and the masters CRUD.

All generators continue the conventions found in the imported workbook data:
  companies   C0xx (C001...)
  employees   AKP-<n> (emp_id) / RG-<n> (emp_code)
  individuals IND-<nnnnn>
  vendors     V<nnn> (V001...)
  drivers     D<nnn> (D001...)
  vehicles    VH-<nnn> (VH-001...)
"""

import re


def max_numeric_suffix(cur, table, col, regex, where=""):
    """Largest integer captured by `regex` across matching column values."""
    cur.execute(f"SELECT {col} FROM {table} WHERE 1=1 {where}")
    pat = re.compile(regex, re.IGNORECASE)
    maxn = 0
    for (raw,) in cur.fetchall():
        s = str(raw or "").strip()
        m = pat.search(s)
        if m:
            try:
                n = int(m.group(1))
                if n > maxn:
                    maxn = n
            except Exception:
                pass
    return maxn


def next_company_id(cur):
    """Next company ID matching the existing 'C0xx' convention (e.g. C091)."""
    maxn = max_numeric_suffix(cur, "companies", "company_id", r"^C(\d+)$")
    return f"C{maxn + 1:03d}"


def next_employee_ids(cur):
    """(emp_id, emp_code) with the AKP-<n> / RG-<n> counters.

    The RG- code continues the SYSTEM-WIDE sequence: +1 over the last RG-
    number anywhere in the database (employees.emp_code and
    individuals.company_id), so a new Corporate guest never reuses a number
    already issued to an Individual guest.
    """
    akp = max_numeric_suffix(cur, "employees", "emp_id", r"^AKP-?(\d+)$")
    cur.execute("SELECT rentago_rg_seq.NEXTVAL FROM dual")
    rg = int(cur.fetchone()[0])
    return f"AKP-{akp + 1}", f"RG-{rg}"


def next_rentago_employee_ids(cur):
    """Return distinct internal Employee ID and Code values."""
    cur.execute("SELECT rentago_emp_seq.NEXTVAL, rentago_rg_seq.NEXTVAL FROM dual")
    emp_no, code_no = cur.fetchone()
    return f"RG-E-{int(emp_no)}", f"RG-{int(code_no)}"


def next_rentago_employee_id(cur):
    """Compatibility helper returning the next internal Employee ID."""
    return next_rentago_employee_ids(cur)[0]


def next_guest_company_id(cur):
    """Next 'RG-<n>' Company ID for a new Individual guest: +1 over the last
    RG- number in the system database (individuals.company_id and
    employees.emp_code share one sequence)."""
    cur.execute("SELECT rentago_rg_seq.NEXTVAL FROM dual")
    return f"RG-{int(cur.fetchone()[0])}"


def next_individual_id(cur, company_id=None):
    """Next individual ID 'IND-<n>' (5-digit).

    Always continues the GLOBAL sequence: individual_id is the table's primary
    key, so per-company scoping would collide with ids issued under other
    companies. (company_id is accepted for backward compatibility and ignored.)
    """
    maxn = max_numeric_suffix(cur, "individuals", "individual_id", r"^IND-?(\d+)$")
    return f"IND-{maxn + 1:05d}"


def next_company_entity_id(cur):
    maxn = max_numeric_suffix(cur, "company_entities", "entity_id", r"^ENT-?(\d+)$")
    return f"ENT-{maxn + 1:05d}"


def next_vendor_id(cur):
    """Next vendor ID 'V<nnn>' (V001...)."""
    maxn = max_numeric_suffix(cur, "vendors", "vendor_id", r"^V(\d+)$")
    return f"V{maxn + 1:03d}"


def next_driver_id(cur):
    """Next driver ID 'D<nnn>' (D001...)."""
    maxn = max_numeric_suffix(cur, "drivers", "driver_id", r"^D(\d+)$")
    return f"D{maxn + 1:03d}"


def next_vehicle_id(cur):
    """Next vehicle ID 'VH-<nnn>' (VH-001...)."""
    maxn = max_numeric_suffix(cur, "vehicles", "vehicle_id", r"^VH-?(\d+)$")
    return f"VH-{maxn + 1:03d}"


def next_ratecard_id(cur):
    """Next ratecard ID 'R<nnn>' (R001...)."""
    maxn = max_numeric_suffix(cur, "ratecards", "rate_card_id", r"^R(\d+)$")
    return f"R{maxn + 1:03d}"


def next_contact_id(cur):
    """Next company-contact ID 'CT-<nnnn>' (CT-0001...)."""
    maxn = max_numeric_suffix(cur, "contacts", "contact_id", r"^CT-(\d+)$")
    return f"CT-{maxn + 1:04d}"


def next_contract_id(cur):
    """Next contract ID 'CT-<nnn>' (CT-001...)."""
    maxn = max_numeric_suffix(cur, "contracts", "contract_id", r"^CT-(\d+)$")
    return f"CT-{maxn + 1:03d}"


def next_lead_id(cur):
    """Next sales lead ID 'L-<nnn>' (L-001...)."""
    maxn = max_numeric_suffix(cur, "leads", "lead_id", r"^L-(\d+)$")
    return f"L-{maxn + 1:03d}"
