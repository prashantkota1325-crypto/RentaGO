import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OfflineGuestPolicyTests(unittest.TestCase):
    def test_offline_guest_policy_is_explicitly_disabled(self):
        policy = (ROOT / "docs/OFFLINE_GUEST_ACCESS_DISABLED_POLICY.md").read_text(encoding="utf-8")
        self.assertIn("GUEST_OFFLINE_ACCESS = DISABLED", policy)
        self.assertIn("Driver QR", policy)

    def test_guest_access_requires_secure_token_or_session_routes(self):
        source = (ROOT / "app/routes/guest_access.py").read_text(encoding="utf-8")
        self.assertIn("/guest/access/{token}", source)
        self.assertIn("session_access", source)
        self.assertNotIn("/guest/{booking_id}", source)
        self.assertNotIn("/guest/{trip_continuity_id}", source)

    def test_no_driver_qr_pairing_path_exists(self):
        source = (ROOT / "app/routes/guest_access.py").read_text(encoding="utf-8").upper()
        self.assertNotIn("/QR", source)
        self.assertNotIn("DRIVER_QR", source)


if __name__ == "__main__":
    unittest.main()
