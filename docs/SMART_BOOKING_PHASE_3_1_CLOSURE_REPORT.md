# RentaGO Phase 3.1 Closure Report

## Baseline

Phase 3.0 delivered the shared Smart Booking workspace, Normal/Late mode
integration, tenant-scoped lookup, duplicate detection, repeat lookup, and
server rate preview. Remaining status was UI partial, pricing partial, RBAC
partial, and authenticated/browser verification unavailable.

## Phase 3.1 Changes

- Added Booking module and `_can_modify_booking` enforcement to normal creation.
- Added the same authority checks to duplicate, repeat, and rate preview APIs.
- Allowed internal RentaGO broad-scope users to use Smart Booking without an
  external tenant ID, consistent with `authorization_tenant` behavior.
- Added Booking module checks to corporate, entity, guest, vendor, driver, and
  vehicle lookup routes.
- Kept external lookups tenant-scoped.
- Made commercial limitations explicit: base rate preview is available; taxes,
  additional charges, and total are calculated during confirmation.

## Pricing Architecture

The existing pricing function is `app/rates.py:customer_rate`. It selects the
best matching company/default `ratecards.package_rate` by vehicle category.
The booking creation route does not contain a unified tax, GST, discount, or
final-total calculation service. No second pricing engine was introduced and
no client-supplied commercial value is trusted by the workspace.

## RBAC Architecture

- Smart page: authenticated user, Booking module access, and valid internal
  scope or external tenant membership.
- Normal create: Booking module access plus `_can_modify_booking`.
- Late create: internal RentaGO user plus full Booking module access.
- Duplicate/repeat/rate APIs: Booking module access plus `_can_modify_booking`.
- Corporate, Vendor, Guest, and Driver users cannot create late entries under
  the existing policy.
- Vendor/Driver/Vehicle lookup routes retain role and tenant restrictions.

The LAB Roles Matrix currently contains `Bookings=F` rows for Corporate Admin
and Finance. Internal operator fallback behavior remains governed by the
existing `module_level` and `_can_allocate` implementation.

## Authenticated HTTP Boundary Testing

A temporary LAB Uvicorn server was started on `127.0.0.1:18003` and stopped
after checks. Unauthenticated requests produced:

- `/bookings/smart`: `303` to `/auth/login`
- Smart duplicate/rate/repeat APIs: `401`
- Corporate/Guest/Vendor lookup APIs: `401`
- Normal create: `303` to `/auth/login`
- Late create: denied and redirected to access-denied

Authenticated HTTP creation tests were not run because no valid LAB credentials
were supplied and credentials were not fabricated or extracted.

## Tenant, Duplicate, Repeat, and Late Entry

Tenant-scoped lookups, duplicate detection, and repeat lookup preserve the
authenticated external tenant. Internal users use the existing broad operator
scope. Late mode continues to use `/bookings/late-entry`, preserving historical
timestamps, mandatory reason, allocation validation, audit, and post-trip
restrictions. No GPS session is created.

## Test Results

- Unittest suite with LAB integration enabled: `52 passed`, `0 failed`.
- Python compilation: passed.
- Smart template loading: passed.
- Smart route registration: passed.
- LAB guest lookup execution: passed with tenant-scoped query.
- `pytest`: unavailable; `pytest` is not installed.
- Browser/device UI verification: unavailable.
- Database migration: not required.

## Performance Observations

Lookup endpoints cap suggestions at 20 rows; duplicate detection returns at
most 5 rows; repeat lookup returns one row. Rate-card lookup reads matching
categories without a result cap. No N+1 behavior was introduced and no index
was added without evidence.

## Production Safety

LAB only. Production database, APIs, DNS, secrets, services, and live records
were not touched. Production deployment was not performed.

## Remaining Limitations

- Full browser/device UI verification is unavailable.
- Full authenticated HTTP/RBAC integration requires valid LAB credentials.
- Unified tax/GST/discount/total pricing is not present in the existing engine.
- Contract/SLA/vendor recommendation APIs were not unified and are labeled
  unavailable rather than fabricated.

Production readiness remains **NO**.
