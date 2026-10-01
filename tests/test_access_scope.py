import unittest

from app.scope import _matches_driver, _matches_vendor, _matches_guest, _matches_company, user_scope
from app.routes.bookings import _authorized_vendor_id


class AccessScopeTests(unittest.TestCase):
    def setUp(self):
        self.booking = {
            "company_name": "Corporate A", "company_id": "C-A", "corporate_id": "C-A",
            "guest_name_1": "Guest A", "guest_email": "guest-a@example.com", "guest_contact": "1111111111",
            "vendor_id": "V-A", "vendor_name": "Vendor A", "driver_name": "Driver A", "driver_contact": "2222222222",
        }

    def test_driver_cannot_match_other_driver(self):
        self.assertTrue(_matches_driver(self.booking, {"name": "Driver A", "mobile": "2222222222", "role": "Driver"}))
        self.assertFalse(_matches_driver(self.booking, {"name": "Driver B", "mobile": "", "role": "Driver"}))

    def test_driver_single_identity_field_is_not_enough(self):
        self.assertFalse(_matches_driver(self.booking, {"name": "Driver A", "mobile": "", "role": "Driver"}))

    def test_vendor_cannot_match_other_vendor(self):
        self.assertTrue(_matches_vendor(self.booking, {"organization_id": "VEND-V-A", "role": "Vendor"}))
        self.assertFalse(_matches_vendor(self.booking, {"organization_id": "VEND-V-B", "role": "Vendor"}))

    def test_guest_cannot_match_other_guest(self):
        self.assertTrue(_matches_guest(self.booking, {"name": "Guest A", "email": "guest-a@example.com", "mobile": "", "role": "Guest"}))
        self.assertFalse(_matches_guest(self.booking, {"name": "Guest B", "email": "", "mobile": "", "role": "Guest"}))

    def test_guest_single_identity_field_is_not_enough(self):
        self.assertFalse(_matches_guest(self.booking, {"name": "Guest A", "email": "", "mobile": "", "role": "Guest"}))

    def test_corporate_company_scope_isolated(self):
        self.assertTrue(_matches_company(self.booking, {"organization_id": "CORP-C-A", "role": "Corporate Admin"}))
        self.assertFalse(_matches_company(self.booking, {"organization_id": "CORP-C-B", "role": "Corporate Admin"}))

    def test_external_user_without_tenant_fails_closed(self):
        self.assertEqual(user_scope({"role": "Corporate Admin", "organization_id": "CORP-C-A"})["mode"], "denied")

    def test_vendor_name_alone_is_not_authorization(self):
        self.assertFalse(_matches_vendor(self.booking, {"company_name": "Vendor A", "role": "Vendor"}))

    def test_vendor_allocation_requires_own_tenant_and_vendor(self):
        booking = {"tenant_id": "TEN-A", "vendor_id": "V-A"}
        self.assertEqual(
            _authorized_vendor_id(
                {"role": "Vendor", "tenant_id": "TEN-A", "organization_id": "VEND-V-A"},
                booking,
            ),
            "V-A",
        )
        self.assertFalse(
            _authorized_vendor_id(
                {"role": "Vendor", "tenant_id": "TEN-A", "organization_id": "VEND-V-B"},
                booking,
            )
        )

    def test_vendor_allocation_fails_closed_without_tenant_or_vendor_org(self):
        booking = {"tenant_id": "TEN-A", "vendor_id": "V-A"}
        self.assertFalse(_authorized_vendor_id({"role": "Vendor", "organization_id": "VEND-V-A"}, booking))
        self.assertFalse(_authorized_vendor_id({"role": "Vendor", "tenant_id": "TEN-A", "organization_id": "CORP-C-A"}, booking))

    def test_internal_allocation_keeps_existing_operator_scope(self):
        self.assertIsNone(_authorized_vendor_id({"role": "Operations", "organization_type": "RENTAGO"}, {}))


if __name__ == "__main__":
    unittest.main()
