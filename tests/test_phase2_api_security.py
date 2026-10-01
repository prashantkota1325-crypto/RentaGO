import unittest
from pathlib import Path

from app.routes.bookings import _is_post_trip_booking_row


ROOT = Path(__file__).resolve().parents[1]


class Phase2ApiSecuritySourceTests(unittest.TestCase):
    def test_all_live_action_routes_use_post_trip_guard(self):
        source = (ROOT / "app/routes/bookings.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("_is_post_trip_booking_row(b)"), 6)
        for endpoint in (
            'trip/start-driver', 'trip/start-guest', 'trip/end-driver',
            'trip/end-guest', 'share-live-tracking', '/sos',
        ):
            self.assertIn(endpoint, source)

    def test_post_trip_state_predicate(self):
        self.assertTrue(_is_post_trip_booking_row({"is_late_entry": "Y"}))
        self.assertTrue(_is_post_trip_booking_row({"entry_mode": "OFFLINE_SYSTEM_DOWNTIME"}))
        self.assertTrue(_is_post_trip_booking_row({"booking_status": "3-Completed"}))
        self.assertFalse(_is_post_trip_booking_row({"status_reason": "Trip In Progress"}))

    def test_driver_feedback_is_role_and_state_bound(self):
        source = (ROOT / "app/routes/mobile.py").read_text(encoding="utf-8")
        self.assertIn('def driver_participant_feedback', source)
        self.assertIn('not _is_post_trip_booking(booking)', source)
        self.assertIn('feedback_kind not in ("guest", "safety")', source)
        self.assertIn('user, booking = _load_current(request, "driver")', source)

    def test_post_trip_template_contains_no_live_controls(self):
        template = (ROOT / "app/templates/mobile/participant.html").read_text(encoding="utf-8")
        post_trip = template.split("{% if post_trip_mode %}", 1)[1].split("{% else %}", 1)[0]
        for prohibited in ("share-live-tracking", "trip/start", "trip/end", "gps-trail", "/sos"):
            self.assertNotIn(prohibited, post_trip)
        for permitted in ("participant-feedback", "signature_type\" value=\"guest", "signature_type\" value=\"driver"):
            self.assertIn(permitted, template)


if __name__ == "__main__":
    unittest.main()
