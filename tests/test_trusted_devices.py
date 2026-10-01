import base64
import os
import unittest
import uuid
from datetime import datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.db import get_connection
from app.trusted_devices import provision_device, validate_device, revoke_device, device_state


class TrustedDeviceUnitTests(unittest.TestCase):
    def test_state_expiry_and_revocation(self):
        self.assertEqual(device_state(None), "DEVICE_NOT_PROVISIONED")
        self.assertEqual(device_state({"status": "REVOKED"}), "DEVICE_REVOKED")
        self.assertEqual(device_state({"status": "ACTIVE", "offline_authorized_until": datetime.now() - timedelta(seconds=1)}), "OFFLINE_EXPIRED")


@unittest.skipUnless(os.environ.get("RENTAGO_RUN_LAB_INTEGRATION") == "1",
                     "Set RENTAGO_RUN_LAB_INTEGRATION=1 for Oracle LAB tests")
class TrustedDeviceLabTests(unittest.TestCase):
    def test_provision_validate_signature_tamper_and_revoke(self):
        conn = get_connection()
        device_id = "LAB-DEVICE-" + uuid.uuid4().hex[:12]
        key = Ed25519PrivateKey.generate()
        public = base64.urlsafe_b64encode(key.public_key().public_bytes_raw()).decode().rstrip("=")
        try:
            provision_device(conn, device_id, "LAB-DRIVER", "LAB-TENANT", "LAB-VENDOR",
                             "LAB-KEY", public, "LAB-ADMIN", offline_days=7)
            payload = "trip-continuity=LAB;event=START"
            signature = base64.urlsafe_b64encode(key.sign(payload.encode())).decode().rstrip("=")
            cur = conn.cursor()
            self.assertEqual(validate_device(cur, device_id, "LAB-DRIVER", "LAB-TENANT", "LAB-VENDOR", "LAB-KEY", payload, signature), "OFFLINE_AUTHORIZED")
            self.assertEqual(validate_device(cur, device_id, "LAB-DRIVER", "LAB-TENANT", "LAB-VENDOR", "LAB-KEY", payload + "!", signature), "SIGNATURE_INVALID")
            self.assertEqual(validate_device(cur, device_id, "OTHER-DRIVER", "LAB-TENANT", "LAB-VENDOR", "LAB-KEY"), "DEVICE_IDENTITY_MISMATCH")
            self.assertTrue(revoke_device(conn, device_id, "LAB-ADMIN"))
            self.assertEqual(validate_device(cur, device_id, "LAB-DRIVER", "LAB-TENANT", "LAB-VENDOR", "LAB-KEY"), "DEVICE_REVOKED")
            conn.commit()
        finally:
            cur = conn.cursor()
            cur.execute("DELETE FROM trusted_driver_devices WHERE device_id=:1", (device_id,))
            conn.commit(); conn.close()


if __name__ == "__main__":
    unittest.main()
