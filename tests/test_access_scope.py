import unittest
from unittest.mock import patch

from app.scope import _matches_driver, _matches_vendor, _matches_guest, _matches_company


class AccessScopeTests(unittest.TestCase):
    def setUp(self):
        self.booking = {
            "company_name": "Corporate A", "company_id": "C-A", "corporate_id": "C-A",
            "guest_name_1": "Guest A", "guest_email": "guest-a@example.com", "guest_contact": "1111111111",
            "vendor_id": "V-A", "vendor_name": "Vendor A", "driver_name": "Driver A", "driver_contact": "2222222222",
        }

    def test_driver_cannot_match_other_driver(self):
        self.assertTrue(_matches_driver(self.booking, {"name": "Driver A", "mobile": "", "role": "Driver"}))
        self.assertFalse(_matches_driver(self.booking, {"name": "Driver B", "mobile": "", "role": "Driver"}))

    def test_vendor_cannot_match_other_vendor(self):
        self.assertTrue(_matches_vendor(self.booking, {"company_name": "Vendor A", "name": "", "role": "Vendor"}))
        self.assertFalse(_matches_vendor(self.booking, {"company_name": "Vendor B", "name": "", "role": "Vendor"}))

    def test_guest_cannot_match_other_guest(self):
        self.assertTrue(_matches_guest(self.booking, {"name": "Guest A", "email": "", "mobile": "", "role": "Guest"}))
        self.assertFalse(_matches_guest(self.booking, {"name": "Guest B", "email": "", "mobile": "", "role": "Guest"}))

    def test_corporate_company_scope_isolated(self):
        with patch("app.scope.resolve_company", side_effect=lambda user: {"id": "C-A" if user["company_name"] == "Corporate A" else "C-B", "name": user["company_name"]}):
            self.assertTrue(_matches_company(self.booking, {"company_name": "Corporate A", "organization_id": ""}))
            self.assertFalse(_matches_company(self.booking, {"company_name": "Corporate B", "organization_id": ""}))


if __name__ == "__main__":
    unittest.main()
