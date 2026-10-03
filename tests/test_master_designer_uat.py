"""Browser-style LAB UAT for Master Designer; metadata changes are cleaned up."""

from io import BytesIO

import openpyxl
from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app
from app.routes import masters as master_routes
from app.master_designer import load_published_config
from app.routes.masters import MASTERS
from app.master_import import parse_and_validate


MASTER_KEYS = [
    "companies", "corporate-admin-contacts", "contacts", "employees", "rentago-employees",
    "vendors", "vehicles", "drivers", "individuals", "contracts", "ratecards", "leads", "settings",
]


def _user(role="super admin", tenant="TEN-RENTA-GO"):
    return {"user_id": "LAB-UAT-ADMIN", "role": role, "tenant_id": tenant, "organization_type": "rentago"}


def test_browser_designer_and_all_master_pages(monkeypatch):
    monkeypatch.setattr(master_routes, "current_user", lambda request: _user())
    client = TestClient(app)
    assert client.get("/masters/designer").status_code == 200
    for key in MASTER_KEYS:
        response = client.get(f"/masters/designer/{key}")
        assert response.status_code == 200, key
        assert "SYSTEM PROTECTED" in response.text or "Master Designer" in response.text


def test_designer_requires_authenticated_authorized_user(monkeypatch):
    monkeypatch.setattr(master_routes, "current_user", lambda request: None)
    client = TestClient(app)
    response = client.get("/masters/designer", follow_redirects=False)
    assert response.status_code == 303
    monkeypatch.setattr(master_routes, "current_user", lambda request: _user("vendor"))
    response = client.get("/masters/designer", follow_redirects=False)
    assert response.status_code == 303


def test_lab_edit_alias_custom_field_publish_template_and_import(monkeypatch):
    monkeypatch.setattr(master_routes, "current_user", lambda request: _user())
    client = TestClient(app)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT master_id FROM master_definitions WHERE master_key=:1", ("companies",))
    master_id = cur.fetchone()[0]
    cur.execute("SELECT field_id,display_label,excel_header FROM master_field_definitions WHERE master_id=:1 AND technical_name='company_name'", (master_id,))
    field_id, old_label, old_header = cur.fetchone()
    # Remove only a prior synthetic run, never business data.
    cur.execute("SELECT field_id FROM master_field_definitions WHERE master_id=:1 AND technical_name=:2", (master_id, "lab_test_priority"))
    old_custom = cur.fetchone()
    if old_custom:
        cur.execute("DELETE FROM master_field_options WHERE field_id=:1", (old_custom[0],))
        cur.execute("DELETE FROM master_field_aliases WHERE field_id=:1", (old_custom[0],))
        cur.execute("DELETE FROM master_field_definitions WHERE field_id=:1", (old_custom[0],))
    conn.commit(); conn.close()
    try:
        response = client.post(f"/masters/designer/companies/fields/{field_id}/edit", data={
            "display_label": "LAB Corporate Name", "excel_header": "LAB Company Header",
            "data_type": "TEXT", "required": "Y", "import_enabled": "Y", "export_enabled": "Y",
            "aliases": "Test Company Name", "options": "",
        }, follow_redirects=False)
        assert response.status_code == 303
        response = client.post("/masters/designer/companies/fields", data={
            "technical_name": "lab_test_priority", "display_label": "LAB Test Priority",
            "excel_header": "LAB Test Priority", "data_type": "DROPDOWN", "required": "N",
            "import_enabled": "Y", "export_enabled": "Y", "aliases": "LAB Priority",
            "options": "Low,Medium,High",
        }, follow_redirects=False)
        assert response.status_code == 303
        response = client.post("/masters/designer/companies/publish", follow_redirects=False)
        assert response.status_code == 303
        response = client.get("/masters/designer/companies/template")
        assert response.status_code == 200
        workbook = openpyxl.load_workbook(BytesIO(response.content), read_only=True)
        headers = list(workbook.active.iter_rows(values_only=True))[0]
        assert "LAB Company Header" in headers and "LAB Test Priority" in headers
        conn = get_connection(); effective = load_published_config(conn, "companies", MASTERS["companies"]); conn.close()
        content = b"company_id,LAB Company Header,LAB Test Priority\nTEST-COMPANY-UAT-001,RentaGO LAB Test Company,Medium\n"
        _, rows, errors, _ = parse_and_validate(content, "uat.csv", effective, tenant_id="TEN-RENTA-GO")
        assert not errors and rows[0]["lab_test_priority"] == "Medium"
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM master_configuration_audit WHERE user_id=:1", ("LAB-UAT-ADMIN",))
        assert cur.fetchone()[0] > 0
        cur.execute("SELECT COUNT(*) FROM master_configuration_versions WHERE master_id=:1 AND version_no >= 2", (master_id,))
        assert cur.fetchone()[0] > 0
        conn.close()
    finally:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SELECT field_id FROM master_field_definitions WHERE master_id=:1 AND technical_name=:2", (master_id, "lab_test_priority"))
        custom = cur.fetchone()
        if custom:
            cur.execute("DELETE FROM master_field_options WHERE field_id=:1", (custom[0],))
            cur.execute("DELETE FROM master_field_aliases WHERE field_id=:1", (custom[0],))
            cur.execute("DELETE FROM master_field_definitions WHERE field_id=:1", (custom[0],))
        cur.execute("UPDATE master_field_definitions SET display_label=:1,excel_header=:2 WHERE field_id=:3", (old_label, old_header, field_id))
        cur.execute("DELETE FROM master_configuration_audit WHERE user_id=:1", ("LAB-UAT-ADMIN",))
        cur.execute("DELETE FROM master_configuration_versions WHERE master_id=:1 AND version_no>1", (master_id,))
        cur.execute("UPDATE master_configuration_versions SET status='PUBLISHED' WHERE master_id=:1 AND version_no=1", (master_id,))
        cur.execute("UPDATE master_definitions SET version=1 WHERE master_id=:1", (master_id,))
        conn.commit(); conn.close()


def test_protected_tenant_field_and_rate_card_block(monkeypatch):
    monkeypatch.setattr(master_routes, "current_user", lambda request: _user())
    client = TestClient(app)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT field_id FROM master_field_definitions f JOIN master_definitions m ON m.master_id=f.master_id WHERE m.master_key='companies' AND f.technical_name='tenant_id'")
    field_id = cur.fetchone()[0]; conn.close()
    response = client.post(f"/masters/designer/companies/fields/{field_id}/edit", data={"display_label":"Changed","excel_header":"Changed","data_type":"TEXT"}, follow_redirects=False)
    assert response.status_code == 303 and "protected-field" in response.headers["location"]
    response = client.get("/masters/ratecards")
    assert "/masters/ratecards/import" not in response.text
