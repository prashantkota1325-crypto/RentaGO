from app.routes.masters import MASTERS
from fastapi.testclient import TestClient

from app.main import app
from app.routes import masters as master_routes


def test_generic_and_operational_ratecard_configurations_are_separate():
    assert MASTERS["ratecards"]["title"] == "Rate Cards"
    assert MASTERS["vendor-ratecards"]["title"] == "Vendor Rate Chart"
    assert MASTERS["company-ratecards"]["designer_title"] == "Company Rate Cards"
    assert MASTERS["individual-ratecards"]["designer_title"] == "Individual Rate Cards"
    assert MASTERS["vendor-ratecards"]["designer_title"] == "Vendor Rate Cards"
    assert MASTERS["company-ratecards"]["title"] == "Company Rate Chart"
    assert MASTERS["individual-ratecards"]["title"] == "Individual Rate Chart"


def test_vendor_ratecard_preserves_operational_configuration():
    vendor = MASTERS["vendor-ratecards"]
    assert vendor["table"] == "ratecards"
    assert vendor["pk"] == "rate_card_id"
    assert vendor["import_blocked"] is True
    assert vendor["base_where"] == "UPPER(NVL(owner_type,'VENDOR'))='VENDOR'"
    assert vendor["fields"] == MASTERS["ratecards"]["fields"]


def test_ratecard_import_remains_blocked_and_master_catalog_is_complete():
    for key in ("ratecards", "company-ratecards", "individual-ratecards", "vendor-ratecards"):
        assert MASTERS[key]["import_blocked"] is True
        assert MASTERS[key]["import_blocked_reason"] == "RATECARDS has no approved stable source business key."
    assert "base_where" not in MASTERS["ratecards"]
    expected = {"companies", "corporate-admin-contacts", "contacts", "employees", "rentago-employees",
                "vendors", "vehicles", "drivers", "individuals", "contracts", "ratecards", "leads", "settings",
                "company-ratecards", "individual-ratecards", "vendor-ratecards"}
    assert expected <= set(MASTERS)


def test_master_designer_landing_renders_all_rate_card_entries(monkeypatch):
    monkeypatch.setattr(master_routes, "current_user", lambda request: {
        "user_id": "LAB-RATECARD-REVIEW", "role": "super admin",
        "tenant_id": "TEN-RENTA-GO", "organization_type": "rentago",
    })
    response = TestClient(app).get("/masters/designer")
    assert response.status_code == 200
    for title in ("Rate Cards", "Company Rate Cards", "Individual Rate Cards", "Vendor Rate Cards", "Companies", "Vehicles", "Drivers"):
        assert title in response.text
