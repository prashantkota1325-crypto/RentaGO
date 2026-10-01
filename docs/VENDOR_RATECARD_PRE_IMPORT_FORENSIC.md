# Vendor Ratecard Pre-Import Forensic

## LAB Architecture

- Page: `/masters/ratecards`
- Route: generic `master_list` in `app/routes/masters.py`
- Table: `RATECARDS`
- Pricing lookup: `app/rates.py:customer_rate`
- Existing import source: legacy XLSM importer/schema

## Root Cause of 500

The LAB table had legacy columns `PRICE_1`, `PRICE_2`, `PRICE_3`, and
`MULTIPLIER`, while the page requested canonical columns including
`GARAGE_TO_GARAGE_PCT`. The query failed with `ORA-00904`.

## LAB Repair

An additive canonical migration added the workbook-compatible columns and
backfilled package/extra rates from the legacy price fields. The canonical
query now executes successfully and `customer_rate('DEFAULT','Sedan')` returns
the LAB rate.

## Production Gate

Production connection details were not available and production was not
accessed. No production backup, deletion, import, or deployment was performed.
