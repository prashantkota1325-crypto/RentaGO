import unittest
from unittest.mock import patch

import app.auth as auth


class Cursor:
    def __init__(self, activity):
        self.activity = activity
        self.result = None

    def execute(self, sql, params=None):
        if "COUNT(*) FROM user_sessions" in sql:
            self.result = (1,)
        elif "SELECT s.last_activity" in sql:
            self.result = self.activity
        elif "FROM users WHERE" in sql:
            self.result = ("so1025", "so1025", "Guest", "guest@example.test", "Individual Guest", "Guest", "IND-00992", "9999999999", None, None, "N")
        elif "SELECT tenant_id FROM tenant_memberships" in sql:
            self.result = [("TEN-RENTA-GO",)]
        else:
            self.result = None

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result or []


class Connection:
    def __init__(self, activity):
        self.activity = activity

    def cursor(self):
        return Cursor(self.activity)

    def close(self):
        pass

    def commit(self):
        pass


class Request:
    cookies = {}


class MobileSessionContextTests(unittest.TestCase):
    def setUp(self):
        auth._cache.clear()

    def test_mobile_booking_context_is_propagated_without_cache_pollution(self):
        with patch.object(auth, "read_session_token", return_value=("so1025", "SID-A")), \
             patch.object(auth, "get_connection", return_value=Connection((None, "Guest", "IN-900008", None))):
            user = auth.current_user(Request())
        self.assertEqual(user["mobile_booking_id"], "IN-900008")
        self.assertIsNone(auth._cache[("user", "so1025")][1].get("mobile_booking_id"))

    def test_non_mobile_session_has_empty_booking_context(self):
        with patch.object(auth, "read_session_token", return_value=("so1025", "SID-B")), \
             patch.object(auth, "get_connection", return_value=Connection((None, "Guest", None, None))):
            user = auth.current_user(Request())
        self.assertIsNone(user["mobile_booking_id"])
        self.assertIsNone(user["mobile_expires_at"])


if __name__ == "__main__":
    unittest.main()
