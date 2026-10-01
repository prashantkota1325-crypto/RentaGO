import unittest
from pathlib import Path

from app.scope import _matches_vendor


ROOT = Path(__file__).resolve().parents[1]


class VendorMobileSourceTests(unittest.TestCase):
    def test_vendor_mobile_surface_and_server_scope_exist(self):
        source = (ROOT / "app/routes/mobile.py").read_text(encoding="utf-8")
        template = (ROOT / "app/templates/mobile/vendor.html").read_text(encoding="utf-8")
        self.assertIn('/vendor-login', source)
        self.assertIn('vendor_mobile_home', source)
        self.assertIn('WHERE tenant_id=:1 AND vendor_id=:2', source)
        for label in ("My Bookings", "My Trips", "My Drivers", "My Vehicles", "My Live Tracking"):
            self.assertIn(label, template)

    def test_vendor_scope_matches_only_authenticated_vendor(self):
        booking = {"vendor_id": "VENDOR-A"}
        self.assertTrue(_matches_vendor(booking, {"organization_id": "VEND-VENDOR-A"}))
        self.assertFalse(_matches_vendor(booking, {"organization_id": "VEND-VENDOR-B"}))
        self.assertFalse(_matches_vendor(booking, {"organization_id": "CORP-CORP-A"}))


if __name__ == "__main__":
    unittest.main()
