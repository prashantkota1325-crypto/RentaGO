# RentaGO Ideal Now Phase 1.9 — Final Approval Lock

## 1. FINAL APPROVED BUSINESS RULES

The following rules are locked for Phase 2:

- A Driver with an existing allocated booking/trip on the same calendar day is
  not eligible for Ideal Now.
- Future-calendar-day work does not by itself block Ideal Now.
- No additional Year-1 time buffer is introduced unless an existing RentaGO
  policy/configuration defines one.
- Only one active Ideal Now session is allowed per Driver.
- Driver can explicitly activate and deactivate Ideal Now.
- Thirty minutes without a valid session heartbeat expires Ideal Now.
- Ideal Now does not start continuous GPS.
- GPS remains governed by the existing trip/tracking lifecycle.
- Opportunities are limited to same-tenant, active, Vendor-assigned,
  Driver-unallocated, non-cancelled, non-completed, operationally eligible
  bookings.
- `booking.vendor_id` must equal the authenticated Driver’s authoritative
  `drivers.vendor_id`.
- Vendor authority is never client-controlled.
- The booking action is `ACCEPT`.
- Acceptance uses a transaction, row lock, full revalidation, allocation,
  audit, and commit.
- Exactly one of two concurrent acceptance attempts may succeed.
- Existing compliance/eligibility architecture is reused.
- Critical compliance failures block acceptance.
- Only operationally necessary booking information is exposed to Drivers.
- Existing RentaGO audit infrastructure is used.
- Concurrency testing is performed only in the isolated synthetic environment.

## 2. EXISTING ARCHITECTURE COMPATIBILITY

### Driver/Vendor authority

Compatible.

Existing fields:

```text
drivers.driver_id
drivers.tenant_id
drivers.vendor_id
vendors.vendor_id
vendors.tenant_id
vendors.status
```

### Tenant authorization

Compatible.

Existing helpers:

```text
authorization_tenant()
visible_booking_ids()
can_view()
```

### Booking allocation

Compatible.

Existing fields and routes support Vendor/Driver allocation:

```text
bookings.vendor_id
bookings.driver_name
bookings.driver_contact
bookings.vehicle_no
booking_status
status_reason
```

### Trip lifecycle

Compatible.

Existing Trip records reference bookings and contain trip status and actual
start/end fields.

### Compliance

Partially compatible.

Driver/Vendor/Vehicle compliance fields and expiry processing exist, but a
single reusable allocation eligibility gate is not yet present.

### Audit

Compatible.

`app/audit.py:audit()` exists and can record Ideal Now events without secrets.

### Database transaction/locking

Compatible with Oracle row locking, but no dedicated Ideal Now atomic claim
operation currently exists.

### Driver UI/API

Partially compatible.

The existing mobile Driver portal can host the workflow, but Ideal Now APIs and
UI controls do not currently exist.

## 3. REQUIRED PHASE 2 CHANGES

Phase 2 will require:

- Additive availability-session persistence.
- Ideal Now start/stop/status service logic.
- Thirty-minute stale-session handling.
- Shared Driver eligibility gate.
- Same-day conflict query.
- Vendor-scoped opportunity query.
- New atomic Accept endpoint.
- Row-lock/revalidation transaction.
- Driver mobile UI controls.
- Audit events.
- Authorization and concurrency tests.

These are planned changes only. No implementation was performed.

## 4. TECHNICAL BLOCKERS, IF ANY

No architectural incompatibility was found.

Operational prerequisites remain:

- Isolated synthetic authorization database for testing.
- Isolated concurrency-test environment.
- Owner approval of the final Driver-visible opportunity fields.
- Owner approval of the exact compliance warning/blocking interpretation.

These are implementation/testing gates, not incompatibilities with the current
RentaGO architecture.

## 5. PHASE 2 IMPLEMENTATION SEQUENCE

1. Database migration/design for availability sessions.
2. Availability-session persistence.
3. Ideal Now state/service.
4. Server-side Driver eligibility.
5. Booking opportunity query.
6. Driver/Vendor authorization.
7. Atomic Accept transaction with row lock and revalidation.
8. Vendor-bound Driver allocation.
9. APIs.
10. Driver UI.
11. Audit logging.
12. Automated authorization tests.
13. Concurrency tests in the isolated environment.
14. Rollback validation.
15. Production-readiness review.

## 6. ROLLBACK REQUIREMENTS

- Disable Ideal Now routes and UI without disabling existing booking allocation.
- Preserve all existing booking, Vendor, Driver, Trip, and GPS workflows.
- Roll back only new availability objects/data after feature disablement.
- Preserve audit records.
- Do not rewrite existing booking/vendor/Driver relationships.
- Validate existing allocation routes after rollback.

## 7. SECURITY/CONCURRENCY TEST REQUIREMENTS

Required tests:

- Driver activation eligibility.
- Inactive Driver/Vendor rejection.
- Missing/ambiguous tenant rejection.
- Same-day allocation conflict rejection.
- Cross-tenant opportunity rejection.
- Cross-Vendor opportunity rejection.
- Client Vendor/Driver/Tenant parameter tampering rejection.
- Compliance-blocked acceptance rejection.
- Cancelled/already allocated booking rejection.
- Expired/revoked session rejection.
- Driver/Vendor status change between display and acceptance.
- Duplicate acceptance rejection.
- Concurrent Driver A/Driver B acceptance with exactly one success.
- No partial database mutation after failed acceptance.
- Audit event correctness without secrets.

All live state-changing tests must use the isolated synthetic environment, not
the current production-like host/database.

## FINAL STATUS

PHASE 1.9 STATUS:
COMPLETE

PHASE 2 IMPLEMENTATION READY:
YES

The approved rules are technically compatible with the current RentaGO
architecture. Phase 2 may begin in a controlled development branch, while
isolated authorization/concurrency testing remains a required gate before
production use.

APPLICATION CHANGED: NO
DATABASE CHANGED: NO
CONFIGURATION CHANGED: NO
CREDENTIALS CHANGED: NO
PRODUCTION PROCESS CHANGED: NO
GIT COMMIT: NO
GIT PUSH: NO
