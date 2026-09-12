import unittest
from unittest.mock import patch

import app.auth as auth
from app.scope import _matches_company, _matches_vendor, _matches_guest, visible_booking_ids


class Cursor:
    def __init__(self, memberships, user_row=None):
        self.memberships = memberships
        self.user_row = user_row
        self.result = None

    def execute(self, sql, params=None):
        if "FROM users WHERE" in sql:
            self.result = self.user_row
        elif "tenant_memberships" in sql:
            self.result = [(tenant,) for tenant in self.memberships]
        else:
            self.result = None

    def fetchone(self):
        return self.result

    def fetchall(self):
        return [(tenant,) for tenant in self.memberships]


class Connection:
    def __init__(self, memberships):
        self.memberships = memberships

    def cursor(self):
        return Cursor(self.memberships, ("guest-a", "guest-a", "Guest A", "guest@example.test", "C-A", "Guest", "IND-A", "9999999999", None, None, "N"))

    def close(self):
        pass


class Request:
    cookies = {}


class CurrentUserTenantCacheTests(unittest.TestCase):
    def setUp(self):
        auth._cache.clear()

    def test_cached_user_receives_membership_added_after_cache_creation(self):
        base = {"user_id": "guest-a", "role": "Guest", "emp_id": "IND-A"}
        auth._cache_put(("user", "guest-a"), base)
        with patch.object(auth, "read_session_token", return_value=("guest-a", "")), \
             patch.object(auth, "get_connection", return_value=Connection(["TEN-A"])):
            user = auth.current_user(Request())
        self.assertEqual(user["tenant_id"], "TEN-A")

    def test_cache_miss_user_receives_active_membership_tenant(self):
        with patch.object(auth, "read_session_token", return_value=("guest-a", "")), \
             patch.object(auth, "get_connection", return_value=Connection(["TEN-A"])):
            user = auth.current_user(Request())
        self.assertEqual(user["tenant_id"], "TEN-A")

    def test_mobile_context_is_not_cached(self):
        base = {"user_id": "guest-a", "role": "Guest", "emp_id": "IND-A"}
        auth._cache_put(("user", "guest-a"), base)
        refreshed = auth._refresh_cached_tenant(base, Connection(["TEN-A"]))
        refreshed["mobile_booking_id"] = "IN-A"
        cached = auth._cache_get(("user", "guest-a"), 60)
        self.assertNotIn("mobile_booking_id", cached)
        self.assertEqual(refreshed["mobile_booking_id"], "IN-A")

    def test_zero_memberships_omits_tenant(self):
        refreshed = auth._refresh_cached_tenant({"user_id": "guest-a", "tenant_id": "OLD"}, Connection([]))
        self.assertNotIn("tenant_id", refreshed)

    def test_multiple_memberships_omits_tenant(self):
        refreshed = auth._refresh_cached_tenant({"user_id": "guest-a", "tenant_id": "OLD"}, Connection(["TEN-A", "TEN-B"]))
        self.assertNotIn("tenant_id", refreshed)

    def test_corporate_vendor_and_guest_scopes_use_refreshed_tenant_context(self):
        self.assertTrue(_matches_company({"company_id": "C-A", "corporate_id": "C-A"}, {"organization_id": "CORP-C-A"}))
        self.assertTrue(_matches_vendor({"vendor_id": "V-A"}, {"organization_id": "VEND-V-A"}))
        self.assertTrue(_matches_guest({"emp_guest_id": "IND-A", "guest_name_1": "Guest A"}, {"emp_id": "IND-A", "role": "Guest"}))

    def test_guest_booking_becomes_visible_with_refreshed_tenant(self):
        class BookingCursor:
            def execute(self, sql, params=None):
                pass

            def fetchall(self):
                return [("IN-900008", "", "RG-22625", None, None, "IND-00992",
                         "Soniya Kota", None, None, None, None, "", "", "", "", "",
                         "", "", "")]

        user = {"role": "Guest", "tenant_id": "TEN-RENTA-GO", "emp_id": "IND-00992"}
        self.assertIn("IN-900008", visible_booking_ids(user, BookingCursor()))


if __name__ == "__main__":
    unittest.main()
