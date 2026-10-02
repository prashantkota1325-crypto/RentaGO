import io

import openpyxl

from app.master_import import MAX_BYTES, parse_and_validate, sign_preview, verify_preview, source_hash


CFG = {
    "pk": "company_id",
    "fields": [
        {"name": "company_name", "required": True, "type": "text"},
        {"name": "booker_email", "required": False, "type": "email"},
    ],
}


def test_csv_normalizes_headers_and_detects_duplicate_keys():
    content = b"Company ID,Company Name\nC-1,Acme\nC-1,Duplicate\n"
    headers, rows, errors, mapping = parse_and_validate(content, "companies.csv", CFG)
    assert headers == ["company_id", "company_name"]
    assert len(rows) == 2
    assert any("Duplicate primary key" in error["message"] for error in errors)


def test_xlsx_uses_values_only_and_validates_email():
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Companies"
    sheet.append(["Company ID", "Company Name", "Booker Email"])
    sheet.append(["C-1", "Acme", "not-an-email"])
    stream = io.BytesIO()
    book.save(stream)
    headers, rows, errors, mapping = parse_and_validate(stream.getvalue(), "companies.xlsx", CFG, "Companies")
    assert rows[0]["company_name"] == "Acme"
    assert any("Invalid email" in error["message"] for error in errors)


def test_unknown_columns_are_rejected():
    headers, rows, errors, mapping = parse_and_validate(
        b"Company ID,Company Name,Secret\nC-1,Acme,do-not-import\n", "companies.csv", CFG
    )
    assert any("Unknown column" in error["message"] for error in errors)


def test_alias_mapping_and_ambiguity_are_explicit():
    cfg = {"pk": "emp_id", "table": "employees", "fields": [{"name": "guest_name", "required": True, "type": "text"}]}
    headers, rows, errors, mapping = parse_and_validate(
        b"Employee ID,Name,Guest Name\nTEST-EMP-001,Alice,Alice B\n", "employees.csv", cfg
    )
    assert any(error.get("code") == "AMBIGUOUS_MAPPING" for error in errors)
    assert mapping["employee_id"] == "emp_id"


def test_signed_preview_expiry_tamper_and_replay_material():
    token = sign_preview({"preview_id": "p1", "tenant_id": "T", "source_hash": "abc"}, "secret", ttl=1)
    body, error = verify_preview(token, "secret", now=body_time(token) + 2)
    assert body is None and error == "PREVIEW_EXPIRED"
    altered = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert verify_preview(altered, "secret")[1] == "SIGNATURE_INVALID"


def test_xlsm_is_read_as_data_only():
    book = openpyxl.Workbook()
    book.active.append(["Company ID", "Company Name"])
    book.active.append(["TEST-COMPANY-001", "Synthetic Company"])
    stream = io.BytesIO()
    book.save(stream)
    headers, rows, errors, mapping = parse_and_validate(stream.getvalue(), "synthetic.xlsm", CFG)
    assert rows[0]["company_id"] == "TEST-COMPANY-001"
    assert not errors


def test_required_date_number_and_tenant_validation():
    cfg = {"pk": "company_id", "table": "companies", "fields": [
        {"name": "company_name", "required": True, "type": "text"},
        {"name": "credit_limit", "required": False, "type": "number"},
        {"name": "created_date", "required": False, "type": "date"},
    ]}
    headers, rows, errors, mapping = parse_and_validate(
        b"Company ID,Company Name,Credit Limit,Created Date,Tenant ID\nTEST-COMPANY-001,,bad,not-a-date,OTHER-TENANT\n",
        "companies.csv", cfg, tenant_id="LAB-TENANT"
    )
    codes = {error.get("code") for error in errors}
    assert {"REQUIRED_FIELD_MISSING", "INVALID_NUMBER", "INVALID_DATE", "TENANT_MISMATCH"} <= codes


def test_source_hash_changes_when_source_changes():
    assert source_hash(b"synthetic-a") != source_hash(b"synthetic-b")


def test_empty_header_only_malformed_and_invalid_workbooks_are_controlled_errors():
    for filename, content in (
        ("empty.csv", b""),
        ("header.csv", b"Company ID,Company Name\n"),
        ("malformed.csv", b'Company ID,Company Name\n"broken,Acme\n'),
        ("invalid.xlsx", b"not-an-xlsx"),
        ("invalid.xlsm", b"not-an-xlsm"),
        ("large.csv", b"x" * (MAX_BYTES + 1)),
    ):
        headers, rows, errors, mapping = parse_and_validate(content, filename, CFG)
        assert errors, filename


def test_invalid_status_is_rejected():
    cfg = {"pk": "company_id", "table": "companies", "fields": [
        {"name": "company_name", "required": True, "type": "text"},
        {"name": "status", "required": False, "type": "select", "options": ("Active", "Inactive")},
    ]}
    headers, rows, errors, mapping = parse_and_validate(
        b"Company ID,Company Name,Status\nTEST-COMPANY-001,Synthetic,UNKNOWN\n", "companies.csv", cfg
    )
    assert any(error.get("code") == "INVALID_STATUS" for error in errors)


def body_time(token):
    import base64
    import json
    encoded = token.split(".", 1)[0]
    return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))["issued_at"]
