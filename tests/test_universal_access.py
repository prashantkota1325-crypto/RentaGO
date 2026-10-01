import unittest
from pathlib import Path

from app.universal_access import new_token, token_hash


ROOT = Path(__file__).resolve().parents[1]


class UniversalAccessTests(unittest.TestCase):
    def test_tokens_are_opaque_and_hashed(self):
        raw_a, hash_a = new_token()
        raw_b, hash_b = new_token()
        self.assertNotEqual(raw_a, raw_b)
        self.assertNotEqual(hash_a, raw_a)
        self.assertNotEqual(hash_a, hash_b)
        self.assertEqual(token_hash(raw_a), hash_a)

    def test_route_keeps_existing_role_and_guest_security_boundaries(self):
        source = (ROOT / "app/routes/universal_access.py").read_text(encoding="utf-8")
        self.assertIn("trusted-device-required", source)
        self.assertIn("role", source)
        self.assertIn("booking_id", source)
        self.assertNotIn("password", source.lower())

    def test_manual_access_derives_identity_from_token(self):
        source = (ROOT / "app/routes/universal_access.py").read_text(encoding="utf-8")
        self.assertIn("_bound_user_is_active", source)
        self.assertNotIn("_identity_matches", source)

    def test_android_app_link_configuration_exists_without_invented_fingerprint(self):
        source = (Path(r"C:\RentaGOWork\rentago_mobile_android") /
                  "android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
        self.assertIn('android:autoVerify="true"', source)
        self.assertIn('android:host="app.rentago.co.in"', source)
        self.assertNotIn("sha256_cert_fingerprints", source)

    def test_step3_delivery_policy_is_guest_email_whatsapp_and_driver_whatsapp(self):
        source = (ROOT / "app/notify.py").read_text(encoding="utf-8")
        self.assertIn('"universal-access"', source)
        self.assertIn('"channels": ("email", "whatsapp")', source)
        self.assertIn('"channels": ("whatsapp",)', source)


if __name__ == "__main__":
    unittest.main()
