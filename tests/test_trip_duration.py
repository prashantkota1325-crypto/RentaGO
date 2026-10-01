import unittest
from datetime import datetime


class TripDurationTests(unittest.TestCase):
    def test_actual_trip_duration_uses_actual_start(self):
        start = datetime(2026, 9, 24, 23, 15, 26)
        end = datetime(2026, 9, 25, 3, 40, 21)
        hours = (end - start).total_seconds() / 3600
        self.assertEqual(round(hours, 2), 4.42)


if __name__ == "__main__":
    unittest.main()
