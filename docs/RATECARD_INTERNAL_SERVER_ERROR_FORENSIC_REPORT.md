# Ratecard Internal Server Error Forensic Report

## Symptom

The Ratecards page fails with an Internal Server Error.

## Route / Request

The page is the generic internal master route:

```text
GET /masters/ratecards
```

The route is implemented by `app/routes/masters.py:master_list` with the
`ratecards` configuration.

## Actual Exception

The LAB query reproduced:

```text
ORA-00904: "GARAGE_TO_GARAGE_PCT": invalid identifier
```

The configured list query requests canonical fields including `sr_no`,
`legal_name`, `package_rate`, and `garage_to_garage_pct`.

## Root Cause

The active LAB `RATECARDS` table was the legacy imported shape:

```text
RATE_CARD_ID, CATEGORY, PRICE_1, PRICE_2, PRICE_3, MULTIPLIER, SOURCE, COMPANY_ID
```

The application configuration expected the newer canonical Ratecards shape.
This schema/code mismatch caused the 500 before the template could render.

## Fix

An additive LAB migration adds the canonical workbook-compatible fields and
backfills package/extra rates from legacy `PRICE_1/2/3` values. No existing
rate rows were deleted.

## Regression Risk

The migration is additive and repeatable. Pricing now reads canonical
`PACKAGE_RATE` with fallback to legacy `PRICE_1`. Production was not touched.
