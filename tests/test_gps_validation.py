import unittest

from app.gps_validation import validate_point


class GpsValidationTests(unittest.TestCase):
    def _point(self, **overrides):
        value = {
            "gps_event_id": "GPS-1", "sequence_number": 1,
            "lat": 18.5204, "lon": 73.8567,
            "captured_at": "2026-09-26T10:00:00Z",
        }
        value.update(overrides)
        return value

    def test_valid_point(self):
        point = validate_point(self._point())
        self.assertEqual(point["sequence_number"], 1)

    def test_invalid_coordinate_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_point(self._point(lat=91))

    def test_missing_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_point(self._point(captured_at=""))

    def test_non_finite_coordinate_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_point(self._point(lon=float("nan")))


if __name__ == "__main__":
    unittest.main()
