from app.routes.masters import MASTERS


def test_generic_and_operational_ratecard_configurations_are_separate():
    assert MASTERS["ratecards"]["title"] == "Rate Cards"
    assert MASTERS["vendor-ratecards"]["title"] == "Vendor Rate Chart"
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
    assert MASTERS["ratecards"]["import_blocked"] is True
    assert MASTERS["ratecards"]["import_blocked_reason"] == "RATECARDS has no approved stable source business key."
    expected = {"companies", "corporate-admin-contacts", "contacts", "employees", "rentago-employees",
                "vendors", "vehicles", "drivers", "individuals", "contracts", "ratecards", "leads", "settings",
                "company-ratecards", "individual-ratecards", "vendor-ratecards"}
    assert expected <= set(MASTERS)
