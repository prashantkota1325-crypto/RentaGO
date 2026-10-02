"""Read-only/schema and rollback checks for the configured local LAB Oracle."""

from io import BytesIO

import openpyxl

from app.config import settings
from app.db import get_connection
from app.routes import masters as master_routes


def test_lab_connection_and_import_tables():
    assert settings.ENVIRONMENT != "production"
    assert settings.DB_HOST in {"localhost", "127.0.0.1", "::1"}
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT USER FROM dual")
    assert cur.fetchone()[0].upper() == settings.DB_USER.upper()
    cur.execute("SELECT table_name FROM user_tables")
    tables = {row[0] for row in cur.fetchall()}
    assert {"MASTER_IMPORT_HISTORY", "MASTER_IMPORT_ERRORS"} <= tables
    conn.close()


def test_lab_history_transaction_rolls_back_without_residue():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO master_import_history "
        "(import_id,preview_id,tenant_id,user_id,master_name,source_filename,source_file_hash,file_type,status) "
        "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9)",
        ("IMP-TEST-ROLLBACK", "PREVIEW-TEST-ROLLBACK", "TEN-RENTA-GO", "TEST-USER",
         "companies", "synthetic.csv", "0" * 64, "csv", "PROCESSING"),
    )
    conn.rollback()
    conn.close()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM master_import_history WHERE import_id=:1", ("IMP-TEST-ROLLBACK",))
    assert cur.fetchone()[0] == 0
    conn.close()


def test_lab_tenant_scoping_with_synthetic_records():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO companies (company_id,tenant_id,company_name,status) VALUES (:1,:2,:3,'Active')",
        ("TEST-COMPANY-A-001", "TEST-TENANT-A", "Synthetic A"),
    )
    cur.execute(
        "INSERT INTO companies (company_id,tenant_id,company_name,status) VALUES (:1,:2,:3,'Active')",
        ("TEST-COMPANY-B-001", "TEST-TENANT-B", "Synthetic B"),
    )
    cur.execute("SELECT company_id FROM companies WHERE tenant_id=:1", ("TEST-TENANT-A",))
    assert [row[0] for row in cur.fetchall()] == ["TEST-COMPANY-A-001"]
    cur.execute("UPDATE companies SET company_name='Wrong Tenant' WHERE tenant_id=:1 AND company_id=:2",
                ("TEST-TENANT-A", "TEST-COMPANY-B-001"))
    assert cur.rowcount == 0
    conn.rollback()
    conn.close()


def test_lab_error_report_route_reads_tenant_scoped_errors():
    import uuid
    import_id = "IMP-TEST-ERROR-" + uuid.uuid4().hex[:8].upper()
    preview_id = "PREVIEW-TEST-ERROR-" + uuid.uuid4().hex[:8].upper()
    error_id = uuid.uuid4().hex
    other_import_id = "IMP-TEST-OTHER-" + uuid.uuid4().hex[:8].upper()
    other_preview_id = "PREVIEW-TEST-OTHER-" + uuid.uuid4().hex[:8].upper()
    other_error_id = uuid.uuid4().hex
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO master_import_history (import_id,preview_id,tenant_id,user_id,master_name,source_filename,source_file_hash,file_type,status) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9)",
        (import_id, preview_id, "TEST-TENANT-A", "TEST-USER", "companies", "synthetic.csv", "1" * 64, "csv", "REJECTED"),
    )
    cur.execute(
        "INSERT INTO master_import_errors (error_id,import_id,row_number,source_field,canonical_field,error_code,message) VALUES (:1,:2,2,:3,:4,:5,:6)",
        (error_id, import_id, "Email", "booker_email", "INVALID_EMAIL", "Synthetic validation error"),
    )
    cur.execute(
        "INSERT INTO master_import_history (import_id,preview_id,tenant_id,user_id,master_name,source_filename,source_file_hash,file_type,status) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9)",
        (other_import_id, other_preview_id, "TEST-TENANT-B", "TEST-USER-B", "companies", "other.csv", "2" * 64, "csv", "REJECTED"),
    )
    cur.execute(
        "INSERT INTO master_import_errors (error_id,import_id,row_number,source_field,canonical_field,error_code,message) VALUES (:1,:2,2,:3,:4,:5,:6)",
        (other_error_id, other_import_id, "Email", "booker_email", "OTHER_TENANT_ERROR", "Must not be visible"),
    )
    conn.commit(); conn.close()
    original = master_routes.current_user
    master_routes.current_user = lambda request: {"user_id": "TEST-USER", "role": "super admin", "tenant_id": "TEST-TENANT-A", "organization_type": "rentago"}
    try:
        response = master_routes.master_import_errors(None, import_id)
        assert b"INVALID_EMAIL" in response.body
        assert b"Synthetic validation error" in response.body
        other_response = master_routes.master_import_errors(None, other_import_id)
        assert b"Must not be visible" not in other_response.body
    finally:
        master_routes.current_user = original
        cleanup = get_connection(); cleanup.cursor().execute("DELETE FROM master_import_errors WHERE import_id IN (:1,:2)", (import_id, other_import_id)); cleanup.cursor().execute("DELETE FROM master_import_history WHERE import_id IN (:1,:2)", (import_id, other_import_id)); cleanup.commit(); cleanup.close()


def test_lab_xlsx_export_is_tenant_scoped_and_valid_workbook():
    original = master_routes.current_user
    master_routes.current_user = lambda request: {"user_id": "TEST-USER", "role": "super admin", "tenant_id": "TEN-RENTA-GO", "organization_type": "rentago"}
    try:
        response = master_routes.master_export_xlsx(None, "companies")
        assert response.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        book = openpyxl.load_workbook(BytesIO(response.body), read_only=True, data_only=True)
        assert book.sheetnames == ["Companies"]
        assert list(book.active.iter_rows(values_only=True))[0][0] == "company_id"
    finally:
        master_routes.current_user = original
