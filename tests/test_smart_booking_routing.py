import unittest
from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[1]


class SmartBookingRoutingTests(unittest.TestCase):
    def test_list_button_targets_new_workspace_without_booking_id(self):
        template = (ROOT / "app/templates/bookings/list.html").read_text(encoding="utf-8")
        self.assertIn('href="/bookings/smart"', template)
        self.assertNotIn('href="/bookings/smart?booking_id=', template)

    def test_static_route_precedes_dynamic_booking_detail(self):
        paths = [route.path for route in app.routes]
        smart_index = paths.index("/bookings/smart")
        detail_index = paths.index("/bookings/{booking_id}")
        self.assertLess(smart_index, detail_index)

    def test_workspace_template_is_new_booking_oriented(self):
        template = (ROOT / "app/templates/bookings/smart.html").read_text(encoding="utf-8")
        self.assertIn("Smart Booking Workspace", template)
        self.assertIn('action="/bookings/create"', template)
        self.assertIn("/bookings/late-entry", template)
        self.assertNotIn("booking_id required", template.lower())


if __name__ == "__main__":
    unittest.main()
