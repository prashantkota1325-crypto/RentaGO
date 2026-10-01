# Ratecard Import Validation

The import endpoint is:

```text
GET/POST /masters/ratecards/import
```

Validation is all-or-nothing:

- `.xlsx` extension only
- `Unique Vendors` worksheet required
- exact canonical headers required
- required legal name/category/model/package fields
- numeric values must be non-negative
- duplicate canonical rules rejected
- optional selected owner mismatch rejected
- no row is inserted when any validation error exists

The original workbook is read only and never modified. Imports are transactional
and use the existing Ratecards table.
