import os
import unittest
from pathlib import Path

from app.db import get_connection
from app.guest_access import create_access, validate_token, create_session, session_access


ROOT = Path(__file__).resolve().parents[1]


class GuestAccessSourceTests(unittest.TestCase):
    def test_no_qr_pairing_and_hashed_access_model(self):
        source = (ROOT / "app/routes/guest_access.py").read_text(encoding="utf-8")
        module = (ROOT / "app/guest_access.py").read_text(encoding="utf-8")
        self.assertIn("/guest/access/{token}", source)
        self.assertIn("rentago_guest_trip", source)
        self.assertIn("sha256", module)
        self.assertNotIn("/QR", source.upper())
        self.assertNotIn("DRIVER_QR", source.upper())

    def test_guest_access_permissions_are_separate_from_mobile_login(self):
        source = (ROOT / "app/routes/guest_access.py").read_text(encoding="utf-8")
        self.assertIn("module_level(user, \"Bookings\") == \"F\"", source)
        self.assertIn("/guest/trip", source)
        self.assertIn("guest_trip_access_id", source)


@unittest.skipUnless(os.environ.get("RENTAGO_RUN_LAB_INTEGRATION") == "1",
                     "Set RENTAGO_RUN_LAB_INTEGRATION=1 for Oracle LAB tests")
class GuestAccessLabTests(unittest.TestCase):
    def test_token_session_and_revoke_flow(self):
        conn = get_connection()
        access_id = None
        session_raw = None
        try:
            access_id, raw, _ = create_access(conn, {
                "trip_continuity_id": None, "booking_id": None,
                "tenant_id": "LAB-TENANT", "emp_guest_id": "LAB-GUEST",
            }, "LAB-USER")
            access = validate_token(conn.cursor(), raw)
            self.assertIsNotNone(access)
            session_raw, _ = create_session(conn, access)
            session = session_access(conn.cursor(), session_raw)
            self.assertEqual(session["access_id"], access_id)
            cur = conn.cursor()
            cur.execute("UPDATE guest_trip_access SET status='REVOKED', revoked_at=SYSTIMESTAMP WHERE guest_trip_access_id=:1", (access_id,))
            self.assertFalse(validate_token(cur, raw))
            self.assertIsNone(session_access(cur, session_raw))
            conn.commit()
        finally:
            cur = conn.cursor()
            if access_id:
                cur.execute("DELETE FROM guest_trip_sessions WHERE guest_trip_access_id=:1", (access_id,))
                cur.execute("DELETE FROM guest_trip_access WHERE guest_trip_access_id=:1", (access_id,))
            conn.commit()
            conn.close()


if __name__ == "__main__":
    unittest.main()
