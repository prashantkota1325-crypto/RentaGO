import unittest

from app.templating import duration_clock_words


class DurationFormatTests(unittest.TestCase):
    def test_planned_route_minutes_carry(self):
        self.assertEqual(duration_clock_words(3.70), "4 hrs 10 mins")
        self.assertEqual(duration_clock_words(2.30), "2 hrs 30 mins")


if __name__ == "__main__":
    unittest.main()
