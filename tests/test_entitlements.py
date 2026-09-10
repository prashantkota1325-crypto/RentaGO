import unittest

from app.entitlements import feature_enabled


class Cursor:
    def cursor(self): return self
    def execute(self, *args): pass
    def fetchone(self): return ('Y', 50)


class EntitlementTests(unittest.TestCase):
    def test_enabled_feature_returns_limit(self):
        enabled, limit = feature_enabled(Cursor(), 'TEN-A', 'BOOKING')
        self.assertTrue(enabled)
        self.assertEqual(limit, 50)


if __name__ == '__main__':
    unittest.main()
