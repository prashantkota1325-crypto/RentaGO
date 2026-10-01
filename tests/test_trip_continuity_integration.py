import os
import unittest

from app.config import settings
from app.db import get_connection
from app.trip_continuity import append_event, create_trip_continuity


@unittest.skipUnless(os.environ.get("RENTAGO_RUN_LAB_INTEGRATION") == "1",
                     "Set RENTAGO_RUN_LAB_INTEGRATION=1 for Oracle LAB tests")
class TripContinuityIntegrationTests(unittest.TestCase):
    def test_identity_and_event_idempotency(self):
        self.conn = get_connection()
        continuity_id, reference = create_trip_continuity(
            self.conn, "LAB-TENANT", "OFFLINE_EMERGENCY", status="AWAITING_BOOKING",
            source="LAB_TEST", offline_created="Y",
        )
        event_a, created_a = append_event(
            self.conn, continuity_id, "TRIP_STARTED", {"source": "lab"},
            "DRIVER", "LAB-DRIVER", idempotency_key="LAB-START-1",
        )
        event_b, created_b = append_event(
            self.conn, continuity_id, "TRIP_STARTED", {"source": "lab"},
            "DRIVER", "LAB-DRIVER", idempotency_key="LAB-START-1",
        )
        self.assertTrue(reference.startswith("RTT-"))
        self.assertTrue(created_a)
        self.assertFalse(created_b)
        self.assertEqual(event_a, event_b)
        cur = self.conn.cursor()
        cur.execute("SELECT trip_mode,status,offline_created FROM trip_continuity WHERE trip_continuity_id=:1",
                    (continuity_id,))
        self.assertEqual(cur.fetchone(), ("OFFLINE_EMERGENCY", "AWAITING_BOOKING", "Y"))
        cur.execute("SELECT COUNT(*) FROM trip_events WHERE trip_continuity_id=:1", (continuity_id,))
        self.assertEqual(int(cur.fetchone()[0]), 2)
        cur.execute("DELETE FROM trip_events WHERE trip_continuity_id=:1", (continuity_id,))
        cur.execute("DELETE FROM trip_continuity WHERE trip_continuity_id=:1", (continuity_id,))
        self.conn.commit()
        self.conn.close()


if __name__ == "__main__":
    unittest.main()
