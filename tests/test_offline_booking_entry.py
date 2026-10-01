import unittest
from pathlib import Path

from app.routes.mobile import _is_post_trip_booking


ROOT = Path(__file__).resolve().parents[1]


class OfflineBookingEntrySourceTests(unittest.TestCase):
    def test_design_and_migration_controls_exist(self):
        self.assertTrue((ROOT / "docs/OFFLINE_SYSTEM_DOWNTIME_BOOKING_ENTRY.md").is_file())
        migration = (ROOT / "db/migrations/late_post_trip_entry.sql").read_text()
        self.assertIn("ENTRY_MODE", migration)
        self.assertIn("ACTUAL_START_AT", migration)
        self.assertTrue((ROOT / "db/migrations/rollback.sql").is_file())
        self.assertTrue((ROOT / "db/migrations/verification.sql").is_file())

    def test_completed_and_explicit_post_trip_states_are_recognized(self):
        self.assertTrue(_is_post_trip_booking({"status_reason": "Trip Completed"}))
        self.assertTrue(_is_post_trip_booking({"booking_status": "3-Completed"}))
        self.assertFalse(_is_post_trip_booking({"status_reason": "Trip In Progress"}))

    def test_server_owned_metadata_is_used(self):
        source = (ROOT / "app/routes/bookings.py").read_text()
        self.assertIn("late_entry_entered_at, booking_punched_at", source)
        self.assertIn("SYSTIMESTAMP,SYSTIMESTAMP", source)
        self.assertIn("OFFLINE_SYSTEM_DOWNTIME", source)

    def test_mobile_post_trip_surface_does_not_offer_gps_controls(self):
        template = (ROOT / "app/templates/mobile/participant.html").read_text()
        post_trip = template.split("{% if post_trip_mode %}", 1)[1].split("{% else %}", 1)[0]
        self.assertNotIn("share-live-tracking", post_trip)
        self.assertNotIn("trip/start", post_trip)
        self.assertIn("/feedback", post_trip)

    def test_active_late_entry_state_and_lifecycle_hooks_exist(self):
        route = (ROOT / "app/routes/bookings.py").read_text()
        migration = (ROOT / "db/migrations/late_post_trip_entry.sql").read_text()
        template = (ROOT / "app/templates/bookings/smart.html").read_text()
        self.assertIn("CURRENT_TRIP_ACTIVE", route)
        self.assertIn("Late Entry - Active", route)
        self.assertIn("pickup_start_km", route)
        self.assertIn("LATE_ENTRY_TYPE", migration)
        self.assertIn("IS_LATE_ENTRY_ACTIVATED", migration)
        self.assertIn("Current Trip / Active Late Entry", template)


if __name__ == "__main__":
    unittest.main()
