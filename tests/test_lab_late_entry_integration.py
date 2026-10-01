import os
import unittest
import uuid
from datetime import datetime, timedelta

from app.config import settings
from app.db import get_connection
from app.audit import _parse_oracle_dt


@unittest.skipUnless(os.environ.get("RENTAGO_RUN_LAB_INTEGRATION") == "1",
                     "Set RENTAGO_RUN_LAB_INTEGRATION=1 for Oracle LAB tests")
class LabLateEntryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if settings.ENVIRONMENT == "production":
            raise RuntimeError("Refusing integration tests in production")
        if settings.DB_HOST not in ("localhost", "127.0.0.1"):
            raise RuntimeError("LAB integration requires a local database host")
        if settings.DB_SERVICE.upper() != "XEPDB1":
            raise RuntimeError("LAB integration requires XEPDB1")
        cls.conn = get_connection()
        cls.booking_id = "ZZ-LAB-" + uuid.uuid4().hex[:20].upper()
        cls.normal_id = "ZZ-LAB-N-" + uuid.uuid4().hex[:16].upper()
        cls.trip_id = "ZT-LAB-" + uuid.uuid4().hex[:20].upper()
        cls.normal_start = datetime.now() - timedelta(hours=3)
        cls.actual_start = datetime.now() - timedelta(hours=5)
        cls.actual_end = datetime.now() - timedelta(hours=2)
        cur = cls.conn.cursor()
        cur.execute(
            "INSERT INTO bookings (booking_id, tenant_id, booking_date, guest_name_1, "
            "vendor_name, driver_name, vehicle_no, "
            "booking_status, status_reason, is_late_entry, entry_mode, post_trip_reason, "
            "actual_start_at, actual_end_at, booking_punched_at) "
            "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13,:14,:15)",
            (cls.normal_id, "LAB-TENANT", cls.normal_start, "LAB Normal",
             "LAB Vendor", "LAB Driver", "LAB Vehicle", "2-Confirmed",
             "Booking Confirmed - Driver & Vehicle Allocated", "N", None, None,
             cls.normal_start, None, cls.normal_start),
        )
        cur.execute(
            "INSERT INTO bookings (booking_id, tenant_id, booking_date, guest_name_1, "
            "vendor_name, driver_name, vehicle_no, "
            "booking_status, status_reason, is_late_entry, late_entry_reason, "
            "late_entry_entered_by, late_entry_entered_at, booking_punched_at, entry_mode, "
            "post_trip_reason, actual_start_at, actual_end_at) "
            "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13,:14,:15,:16,:17,:18)",
            (cls.booking_id, "LAB-TENANT", cls.actual_start, "LAB Guest",
             "LAB Vendor", "LAB Driver", "LAB Vehicle", "3-Completed", "Trip Completed",
             "Y", "SYSTEM_OUTAGE", "LAB-USER", cls.actual_start, cls.actual_start,
             "OFFLINE_SYSTEM_DOWNTIME", "SYSTEM_OUTAGE", cls.actual_start, cls.actual_end),
        )
        cur.execute(
            "INSERT INTO trips (trip_id, tenant_id, booking_id, guest_name, booking_status, "
            "trip_status, actual_start_dt, actual_end_dt) VALUES (:1,:2,:3,:4,:5,:6,:7,:8)",
            (cls.trip_id, "LAB-TENANT", cls.booking_id, "LAB Guest", "Trip Completed",
             "Trip Completed", cls.actual_start, cls.actual_end),
        )

    @classmethod
    def tearDownClass(cls):
        cur = cls.conn.cursor()
        cur.execute("DELETE FROM trips WHERE booking_id=:1", (cls.booking_id,))
        cur.execute("DELETE FROM bookings WHERE booking_id IN (:1,:2)",
                    (cls.booking_id, cls.normal_id))
        cls.conn.commit()
        cls.conn.close()

    def test_normal_booking_is_not_late(self):
        cur = self.conn.cursor()
        cur.execute("SELECT is_late_entry FROM bookings WHERE booking_id=:1", (self.normal_id,))
        self.assertEqual(cur.fetchone()[0], "N")

    def test_late_booking_preserves_timestamps_and_reason(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT is_late_entry, entry_mode, post_trip_reason, actual_start_at, "
            "actual_end_at, booking_punched_at FROM bookings WHERE booking_id=:1",
            (self.booking_id,),
        )
        row = cur.fetchone()
        self.assertEqual(row[0], "Y")
        self.assertEqual(row[1], "OFFLINE_SYSTEM_DOWNTIME")
        self.assertEqual(row[2], "SYSTEM_OUTAGE")
        self.assertEqual(_parse_oracle_dt(row[3]).replace(microsecond=0),
                         self.actual_start.replace(microsecond=0))
        self.assertEqual(_parse_oracle_dt(row[4]).replace(microsecond=0),
                         self.actual_end.replace(microsecond=0))
        self.assertIsNotNone(row[5])

    def test_late_booking_preserves_vendor_driver_vehicle(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT vendor_name, driver_name, vehicle_no FROM bookings WHERE booking_id=:1",
            (self.booking_id,),
        )
        self.assertEqual(cur.fetchone(), ("LAB Vendor", "LAB Driver", "LAB Vehicle"))

    def test_booking_punch_is_separate_from_actual_drop(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT actual_end_at, booking_punched_at FROM bookings WHERE booking_id=:1",
            (self.booking_id,),
        )
        actual_end, punched = cur.fetchone()
        self.assertNotEqual(str(actual_end), str(punched))

    def test_signatures_feedback_and_tenant_scope(self):
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE trips SET customer_signature=:1, customer_signature_source=:2, "
            "customer_signature_at=SYSTIMESTAMP, customer_signature_by=:3, "
            "driver_signature=:4, driver_signature_source=:5, driver_signature_at=SYSTIMESTAMP, "
            "driver_signature_by=:6, driver_feedback=:7, driver_safety_status=:8, "
            "driver_feedback_submitted_on=SYSTIMESTAMP, driver_feedback_by=:9 "
            "WHERE booking_id=:10",
            ("Captured", "Guest Mobile", "LAB-GUEST", "Captured", "Driver Mobile",
             "LAB-DRIVER", "Guest was assisted", "Yes", "LAB-DRIVER", self.booking_id),
        )
        cur.execute(
            "SELECT customer_signature_source, driver_signature_source, driver_feedback, "
            "driver_safety_status FROM trips WHERE booking_id=:1 AND tenant_id=:2",
            (self.booking_id, "LAB-TENANT"),
        )
        self.assertEqual(cur.fetchone(), ("Guest Mobile", "Driver Mobile", "Guest was assisted", "Yes"))
        cur.execute("SELECT COUNT(*) FROM bookings WHERE booking_id=:1 AND tenant_id=:2",
                    (self.booking_id, "OTHER-TENANT"))
        self.assertEqual(int(cur.fetchone()[0]), 0)


if __name__ == "__main__":
    unittest.main()
