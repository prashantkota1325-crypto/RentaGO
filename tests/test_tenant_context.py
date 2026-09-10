import unittest

from app.tenant_context import TenantContextError, select_membership


class TenantContextTests(unittest.TestCase):
    def test_selects_single_active_membership(self):
        context = select_membership([("TEN-A", "A", "Tenant A", "ACTIVE", "ADMIN")], "user-a")
        self.assertEqual(context.tenant_id, "TEN-A")
        self.assertEqual(context.membership_role, "ADMIN")

    def test_ambiguous_membership_fails_closed(self):
        rows = [("TEN-A", "A", "Tenant A", "ACTIVE", "ADMIN"),
                ("TEN-B", "B", "Tenant B", "ACTIVE", "ADMIN")]
        with self.assertRaises(TenantContextError):
            select_membership(rows, "user-a")

    def test_inactive_membership_fails_closed(self):
        with self.assertRaises(TenantContextError):
            select_membership([("TEN-A", "A", "Tenant A", "SUSPENDED", "ADMIN")], "user-a")
