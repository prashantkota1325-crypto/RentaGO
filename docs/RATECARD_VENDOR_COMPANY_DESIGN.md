# Vendor / Company Ratecard Design

Both Vendor and Company/RentaGO charts use the same canonical `RATECARDS`
structure derived from `Unique Vendors`.

Ownership metadata distinguishes them:

- `owner_type = VENDOR`, `owner_id = vendor_id`, `vendor_id = vendor_id`
- `owner_type = COMPANY`, `owner_id = company_id`

Tenant, effective dates, service/trip metadata, status, approval status, and
source file are additive metadata. Existing legacy rate fields remain for
compatibility and are backfilled into canonical package/extra rates.

Vendor users remain restricted by existing Vendor/RBAC/tenant rules. The
current import surface is internal RentaGO administration only.
