import re

from app.master_designer import FIELD_TYPES, PROTECTED_FIELDS, normalize_header, validate_technical_name
from app.master_import import map_headers, parse_and_validate
from app.db import get_connection


MASTER_KEYS = {
    "companies", "corporate-admin-contacts", "contacts", "employees", "rentago-employees",
    "vendors", "vehicles", "drivers", "individuals", "contracts", "ratecards", "leads", "settings",
}


def test_thirteen_master_definitions_are_seeded():
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT master_key FROM master_definitions WHERE active='Y'")
    assert MASTER_KEYS | {"company-ratecards", "individual-ratecards", "vendor-ratecards"} <= {row[0] for row in cur.fetchall()}
    conn.close()


def test_field_catalog_preserves_existing_employee_columns():
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT technical_name FROM master_field_definitions f JOIN master_definitions m ON m.master_id=f.master_id WHERE m.master_key='employees'")
    names = {row[0] for row in cur.fetchall()}
    assert {"emp_id", "company_name", "designation", "guest_name", "tenant_id"} <= names
    conn.close()


def test_display_labels_and_excel_headers_are_metadata():
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT display_label,excel_header FROM master_field_definitions f JOIN master_definitions m ON m.master_id=f.master_id WHERE m.master_key='companies' AND technical_name='company_name'")
    label, header = cur.fetchone()
    assert label and header
    conn.close()


def test_alias_normalization_and_ambiguity():
    cfg = {"table": "companies", "pk": "company_id", "fields": [{"name": "company_name", "aliases": ["Corporate Name"]}]}
    mapped, mapping, errors = map_headers(["Corporate Name", "Company Name"], cfg)
    assert mapping["Corporate Name"] == "company_name"
    assert any(error["code"] == "AMBIGUOUS_MAPPING" for error in errors)
    assert normalize_header("  Company__Name ") == "company_name"


def test_custom_technical_name_and_protected_field_rules():
    assert validate_technical_name("customer_priority") == "customer_priority"
    assert re.fullmatch(r"^[a-z][a-z0-9_]*$", "customer_priority")
    for name in ("TENANT_ID", "password", "api_key"):
        try:
            validate_technical_name(name)
        except ValueError:
            pass
        else:
            raise AssertionError(f"protected field accepted: {name}")
    assert "tenant_id" in PROTECTED_FIELDS


def test_supported_field_types_are_closed_list():
    assert {"TEXT", "NUMBER", "DATE", "DROPDOWN", "COMPANY_LOOKUP", "FILE"} <= FIELD_TYPES


def test_required_optional_regex_and_length_validation():
    cfg = {"table": "companies", "pk": "company_id", "fields": [
        {"name": "company_name", "required": True, "type": "text", "min_length": 3, "max_length": 10, "regex_pattern": r"[A-Za-z ]+"},
    ]}
    _, _, errors, _ = parse_and_validate(b"Company ID,Company Name\nTEST-1,1\n", "x.csv", cfg)
    codes = {error.get("code") for error in errors}
    assert {"REGEX_MISMATCH", "MIN_LENGTH"} <= codes


def test_dropdown_options_are_seeded_and_disabled_options_are_absent_from_active_list():
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM master_field_options WHERE active='Y'")
    assert cur.fetchone()[0] > 0
    conn.close()


def test_field_order_and_configuration_flags_exist():
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*),COUNT(DISTINCT display_order) FROM master_field_definitions")
    total, ordered = cur.fetchone()
    assert total > 0 and ordered > 0
    cur.execute("SELECT COUNT(*) FROM master_field_definitions WHERE system_protected='Y' AND technical_name='tenant_id'")
    assert cur.fetchone()[0] > 0
    conn.close()


def test_versions_are_published_and_rate_cards_disabled():
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM master_configuration_versions WHERE status='PUBLISHED'")
    assert cur.fetchone()[0] == 16
    cur.execute("SELECT import_enabled FROM master_definitions WHERE master_key='ratecards'")
    assert cur.fetchone()[0] == "N"
    conn.close()


def test_custom_values_and_configuration_audit_tables_are_empty_without_business_seed():
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM master_custom_values")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM master_configuration_audit")
    assert cur.fetchone()[0] == 0
    conn.close()
