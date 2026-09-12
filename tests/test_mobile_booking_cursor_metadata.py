import unittest


class Cursor:
    def __init__(self):
        self.description = []
        self._row = None

    def execute(self, query, params=None):
        if "FROM bookings" in query:
            self.description = [
                ("BOOKING_ID",), ("TENANT_ID",), ("EMP_GUEST_ID",),
                ("BOOKING_STATUS",), ("STATUS_REASON",),
            ]
            self._row = ("IN-TEST", "TEN-TEST", "IND-TEST", "1-Pending", "Vehicle & Driver Allocation Pending")
        else:
            self.description = [("TENANT_ID",)]

    def fetchone(self):
        return self._row


class MobileBookingCursorMetadataTests(unittest.TestCase):
    def test_booking_metadata_survives_subsequent_cursor_query(self):
        cur = Cursor()
        cur.execute("SELECT * FROM bookings WHERE booking_id=:1")
        booking_row = cur.fetchone()
        booking_cols = [d[0].lower() for d in cur.description]

        cur.execute("SELECT tenant_id FROM tenant_memberships WHERE user_id=:1")
        booking = dict(zip(booking_cols, booking_row))

        self.assertEqual(booking["tenant_id"], "TEN-TEST")
        self.assertEqual(booking["emp_guest_id"], "IND-TEST")
        self.assertEqual(booking["booking_status"], "1-Pending")
        self.assertEqual(booking["status_reason"], "Vehicle & Driver Allocation Pending")


if __name__ == "__main__":
    unittest.main()
