import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SmartBookingWorkspaceSourceTests(unittest.TestCase):
    def test_shared_workspace_and_authoritative_flows_exist(self):
        source = (ROOT / "app/routes/bookings.py").read_text(encoding="utf-8")
        template = (ROOT / "app/templates/bookings/smart.html").read_text(encoding="utf-8")
        self.assertIn('def smart_booking_page', source)
        self.assertIn('def smart_booking_duplicates', source)
        self.assertIn('def smart_repeat_booking', source)
        self.assertIn('def smart_rate_preview', source)
        self.assertIn('action="/bookings/create"', template)
        self.assertIn("form.action = isLate ? '/bookings/late-entry' : '/bookings/create'", template)

    def test_workspace_uses_server_lookups_and_no_fake_pricing(self):
        template = (ROOT / "app/templates/bookings/smart.html").read_text(encoding="utf-8")
        for endpoint in (
            "/bookings/companies?q=", "/bookings/guests?q=", "/bookings/vendors?q=",
            "/bookings/drivers?q=", "/bookings/vehicles?q=", "/bookings/geocode?q=",
            "/bookings/smart/rate?",
        ):
            self.assertIn(endpoint, template)
        self.assertNotIn("₹1000", template)
        self.assertIn("existing server rate-card logic", template)

    def test_lookup_routes_are_tenant_scoped_for_tenant_users(self):
        source = (ROOT / "app/routes/bookings.py").read_text(encoding="utf-8")
        self.assertIn('scope = " AND tenant_id=:2" if tenant_id else ""', source)
        self.assertIn('scope = " AND tenant_id=:3"', source)
        self.assertIn('entity_scope = " AND tenant_id=:2"', source)
        self.assertIn("entry_mode", source)

    def test_progressive_late_fields_and_duplicate_warning_exist(self):
        template = (ROOT / "app/templates/bookings/smart.html").read_text(encoding="utf-8")
        for label in ("Late / Post-Trip Entry", "actual trip timestamps", "Late Entry Reason", "Possible duplicate booking"):
            self.assertIn(label, template)

    def test_pricing_is_explicitly_server_authoritative(self):
        template = (ROOT / "app/templates/bookings/smart.html").read_text(encoding="utf-8")
        source = (ROOT / "app/routes/bookings.py").read_text(encoding="utf-8")
        self.assertIn("Taxes: Calculated during confirmation", template)
        self.assertIn("Total: Server-authoritative at confirmation", template)
        self.assertIn('return JSONResponse({\n        "base_rate": customer_rate', source)
        self.assertNotIn("innerHTML = price", template)

    def test_creation_and_preview_endpoints_require_booking_authority(self):
        source = (ROOT / "app/routes/bookings.py").read_text(encoding="utf-8")
        self.assertIn('if module_level(user, "Bookings") is None or not _can_modify_booking(user):', source)
        self.assertIn('or module_level(user, "Bookings") is None or not _can_modify_booking(user)', source)


if __name__ == "__main__":
    unittest.main()
