# Vendor Ratecard Import Report

## Workbook

- File: `Rentago Rate Chart Format-Vendor.xlsx`
- Sheet: `Unique Vendors`
- Source rows: `4,432`
- Exact headers: `21`

## Validation

The LAB validator successfully read all `4,432` rows. Repeated package names
across vendors and vehicle/package rows are preserved as distinct source rows.
One genuine source error remains: row `940` contains `Da = -0.01`, which is
rejected as an invalid negative rate. The transaction is blocked until that
source value is corrected. The source workbook was not changed.

No production import was attempted. No production row count or reconciliation
claim is made.
