import os
import unittest
from pathlib import Path

from app.ratecard_import import CANONICAL, validate_workbook

ROOT = Path(__file__).resolve().parents[1]


class RatecardSourceTests(unittest.TestCase):
    def test_canonical_workbook_headers_are_defined(self):
        workbook = ROOT / "Rentago Rate Chart Format-Vendor.xlsx"
        self.assertTrue(workbook.is_file())
        self.assertEqual(len(CANONICAL), 21)
        self.assertEqual(CANONICAL[0][1], "Sr.No.")
        self.assertEqual(CANONICAL[-1][1], "Garage To Garage %")

    def test_importer_preserves_repeated_packages_as_distinct_source_rows(self):
        try:
            content = (ROOT / "Rentago Rate Chart Format-Vendor.xlsx").read_bytes()
        except PermissionError:
            self.skipTest("Source workbook is open/locked by another local process")
        rows, errors = validate_workbook(content, "Rentago Rate Chart Format-Vendor.xlsx")
        self.assertGreater(len(rows), 0)
        self.assertFalse(any(error["code"] == "DUPLICATE_SOURCE_ROW" for error in errors))
        self.assertTrue(all(error["code"] == "INVALID_RATE" for error in errors))

    def test_upload_path_is_canonical(self):
        source = (ROOT / "app/routes/masters.py").read_text(encoding="utf-8")
        template = (ROOT / "app/templates/masters/ratecard_import.html").read_text(encoding="utf-8")
        self.assertIn('/ratecards/import', source)
        self.assertIn("Unique Vendors", template)


@unittest.skipUnless(os.environ.get("RENTAGO_RUN_LAB_INTEGRATION") == "1",
                     "Set RENTAGO_RUN_LAB_INTEGRATION=1 for Oracle LAB tests")
class RatecardLabTests(unittest.TestCase):
    def test_canonical_query_and_legacy_fallback_columns_exist(self):
        from app.db import get_connection
        from app.rates import customer_rate
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT package_rate,price_1,garage_to_garage_pct FROM ratecards FETCH FIRST 1 ROWS ONLY")
        cur.fetchone()
        conn.close()
        self.assertGreater(customer_rate("DEFAULT", "Sedan"), 0)


if __name__ == "__main__":
    unittest.main()
