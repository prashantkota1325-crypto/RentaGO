# RentaGO Ideal Now Phase 1.6 — Final Decision Lock

## 1. Executive Summary

Ideal Now should be implemented as a Driver availability and booking-claim
layer over the existing RentaGO booking/allocation model.

The authoritative Vendor relationship remains:

```text
authenticated Driver
    -> drivers.driver_id
    -> drivers.vendor_id
    -> vendors.vendor_id
    -> booking.vendor_id
```

The current system does not contain a durable Driver availability state or a
Driver booking-claim endpoint. Both are required.

Phase 2 implementation is **not yet ready** because:

- The isolated concurrency-test environment is not available.
- The production-like host must not be used for concurrency testing.
- Product approval is still required for the conservative current-day conflict
  rule and any travel-time buffer.
- Compliance eligibility is present in fields/profile logic but is not a single
  reusable allocation gate.

## 2. Existing Architecture Findings

- Driver master: `drivers` table.
- Vendor master: `vendors` table.
- Driver/Vendor relationship: `drivers.vendor_id`.
- Tenant relationship: `tenant_id` plus `tenant_memberships` and organization IDs.
- Booking Vendor: `bookings.vendor_id` and related display fields.
- Booking Driver: `bookings.driver_name`, `driver_contact`, `vehicle_no`.
- Trip relationship: `trips.booking_id`.
- Driver mobile authentication: `/mobile/driver-login` with PIN and booking ID.
- Driver session binding: `user_sessions.mobile_booking_id`.
- Booking visibility: `visible_booking_ids()` and `can_view()` in `app/scope.py`.
- Vendor authorization: `authorization_tenant()` and `VEND-*` organization ID.
- Existing allocation routes:
  - `POST /bookings/{booking_id}/allocate/vendor`.
  - `POST /bookings/{booking_id}/allocate/driver`.
- Existing audit: `app/audit.py:audit()`.
- Existing database transaction pattern: one connection, commit after mutation.
- Existing row-lock/atomic claim mechanism: **not identified**.
- Existing Driver availability state: **not identified**.

## 3. Driver-Vendor Authority Model

The server must derive Vendor identity from:

```text
authenticated Driver user
    -> Driver master record
    -> drivers.vendor_id
    -> Vendor record
```

The following are never authoritative:

- Browser `vendor_id`.
- Browser Vendor name.
- Browser tenant ID.
- Driver-supplied organization ID.

The accepted booking must satisfy:

```text
booking.tenant_id = authenticated Driver tenant
booking.vendor_id = authenticated Driver drivers.vendor_id
```

## 4. Ideal Now Business Definition

Ideal Now means the authenticated Driver is currently available to accept an
eligible booking through the Driver’s registered Vendor.

It does not start GPS and does not imply continuous tracking.

## 5. Eligibility Rules

### Blocking conditions

- No authenticated Driver session.
- User role is not Driver.
- User is inactive.
- Driver master record is missing.
- Driver tenant membership is missing or ambiguous.
- Driver `vendor_id` is missing.
- Vendor is missing, inactive, or in another tenant.
- Driver is suspended, terminated, or inactive.
- Driver has an active trip.
- Driver has a blocking allocated booking.
- Driver licence is expired where licence validity is mandatory.
- Driver police/background verification is explicitly failed.
- Driver compliance status is explicitly invalid.

### Non-blocking conditions

- Documents approaching expiry but still valid, unless existing RentaGO policy
  marks them as blocking.
- Missing optional profile metadata.
- Missing optional rating/language data.

The implementation must centralize the eligibility decision so the Ideal Now
button and final booking acceptance use the same server-side rule.

## 6. Current-Day / Time Conflict Rules

### Final recommended rule

A Driver cannot enter Ideal Now or accept a booking when the Driver has any
non-cancelled, non-completed allocated booking or active trip covering the
current service day, unless the existing data contains reliable non-overlapping
start/end windows and the approved operational buffer confirms no conflict.

Because the current model does not guarantee a reliable completed end time for
every future booking, the safe initial Year-1 rule is conservative:

- Active trip: blocking.
- Allocated, non-cancelled booking on the same service date: blocking.
- Multi-day booking covering the current date: blocking.
- Completed/cancelled/no-show records: non-blocking after their terminal state
  is authoritative.
- Future bookings on later dates: not a current-day block, but must be checked
  at acceptance time for the accepted booking’s service window.
- Missing end/drop time: treat the allocation as all-day for conflict purposes.

An exact travel/deadhead buffer remains an owner decision. Until approved, no
additional optimistic buffer should be assumed.

## 7. Compliance Gate

Reuse existing Driver/Vendor/Vehicle fields and existing compliance worker
data. Do not create a second compliance engine.

The shared eligibility gate should evaluate:

- Driver status.
- Vendor status.
- Licence expiry.
- Police verification.
- Background check.
- Driver compliance status.
- Vehicle compliance when a vehicle is already required or assigned.

Expiry warnings may be non-blocking only where current RentaGO policy permits.
Explicit expired, failed, inactive, suspended, or invalid states are blocking.

## 8. State Machine

Recommended persisted states:

```text
OFFLINE
IDEAL_NOW
ALLOCATED
ON_TRIP
```

Transitions:

```text
OFFLINE -> IDEAL_NOW       after server eligibility succeeds
IDEAL_NOW -> OFFLINE      Driver stops, logs out, expires, or becomes invalid
IDEAL_NOW -> ALLOCATED    booking claim succeeds
ALLOCATED -> ON_TRIP      existing trip start succeeds
ON_TRIP -> OFFLINE        existing trip completion succeeds
```

Invalidation events:

- Driver deactivation.
- Vendor deactivation.
- Tenant membership loss.
- Compliance becoming blocking.
- Session expiry/revocation.
- Booking cancellation.
- Application-controlled stale availability timeout.

## 9. Booking Opportunity Rules

The first implementation should offer only bookings satisfying all conditions:

- `booking_status = '1-Pending'`.
- `status_reason = 'Awaiting Driver & Vehicle Allocation'`.
- `vendor_id` is present.
- `vendor_id` equals the authenticated Driver’s registered Vendor.
- Booking tenant equals Driver tenant.
- Driver/vehicle allocation fields are not already populated.
- Booking is not cancelled or completed.
- Pickup/service time is eligible under the conflict rule.
- Existing lead-time/SLA rules permit allocation or an authorized override exists.

This intentionally excludes unassigned Vendor bookings because a Driver must
accept through a registered Vendor.

Driver-visible fields should be limited to operational decision data:

- Booking reference.
- Pickup date/time.
- Pickup/drop city/address as required.
- Vehicle category/type.
- Package/service duration.
- Relevant operational instructions.

Do not expose margins, internal rates, unrelated customer data, or other Vendor
information.

## 10. Accept/Request/Claim Recommendation

Use the term **Accept**.

```text
Driver views opportunity
    -> taps Accept
    -> server revalidates
    -> server atomically claims booking
    -> server derives Vendor
    -> server assigns Driver/Vendor
```

No separate approval workflow is required for the first Year-1 version.

## 11. Atomic Claim Design

Create a focused acceptance endpoint that performs one transaction:

1. Authenticate Driver.
2. Resolve tenant, Driver, and Vendor from server-side data.
3. Lock the booking row with `SELECT ... FOR UPDATE` or an equivalent Oracle
   row-locking strategy.
4. Recheck booking status and Vendor assignment.
5. Recheck Driver eligibility and conflict state.
6. Update booking Vendor/Driver fields.
7. Create/update Trip state using existing helpers.
8. Write audit events.
9. Commit.

If another Driver wins the lock first, return a controlled “Booking is no
longer available” response and make no partial mutation.

The current allocation routes do not provide a dedicated Ideal Now atomic claim
operation. Reuse existing allocation business helpers inside the new atomic
transaction rather than duplicating calculation logic.

## 12. Vendor-Bound Security

For every Driver acceptance:

```text
authorized_vendor_id = drivers.vendor_id
```

Reject when:

- `drivers.vendor_id` is absent.
- Vendor does not exist or is inactive.
- Vendor tenant differs from Driver tenant.
- Booking Vendor differs from Driver Vendor.
- Any client-submitted Vendor value differs from the server-derived value.

No Vendor ID should be accepted as an authorization input from the mobile UI.

## 13. Tenant Isolation

Every opportunity and acceptance query must include the authenticated Driver’s
tenant context. Missing or ambiguous tenant membership must fail closed.

No query parameter, form field, URL field, or mobile payload may override the
tenant.

## 14. API Specification

### Start Ideal Now

```text
POST /mobile/driver/ideal-now/start
```

- Authenticated Driver session.
- No request tenant/vendor/driver ID accepted.
- Returns state or eligibility rejection.
- Audit: `IDEAL_NOW_ENABLED` or `IDEAL_NOW_REJECTED`.

### Stop Ideal Now

```text
POST /mobile/driver/ideal-now/stop
```

- Authenticated Driver session.
- Stops only the current Driver’s availability.
- Audit: `IDEAL_NOW_DISABLED`.

### Opportunities

```text
GET /mobile/driver/ideal-now/opportunities
```

- Authenticated Driver session.
- Server derives tenant, Driver, and Vendor.
- Returns only eligible booking opportunities.

### Accept

```text
POST /mobile/driver/ideal-now/opportunities/{booking_id}/accept
```

- Authenticated Driver session.
- Booking ID is only an object selector.
- Vendor, tenant, and Driver are server-derived.
- Uses atomic claim transaction.
- Audit: attempted, accepted, rejected, race-lost, or authorization-failed.

## 15. Database Specification

A dedicated table is recommended:

```text
driver_availability_sessions
    availability_id       VARCHAR2(40) PRIMARY KEY
    tenant_id             VARCHAR2(40) NOT NULL
    driver_id             VARCHAR2(40) NOT NULL
    vendor_id             VARCHAR2(40) NOT NULL
    status                VARCHAR2(30) NOT NULL
    activated_at          TIMESTAMP NOT NULL
    deactivated_at        TIMESTAMP
    last_seen_at          TIMESTAMP
    created_at            TIMESTAMP DEFAULT SYSTIMESTAMP
    updated_at            TIMESTAMP DEFAULT SYSTIMESTAMP
```

Recommended indexes:

- `(tenant_id, driver_id, status)`.
- `(tenant_id, vendor_id, status)`.

The application must enforce one active session per Driver. A reviewed Oracle
unique strategy or transaction lock is required before implementation.

No schema change was made.

## 16. Driver UI

Add to the existing Driver mobile experience:

- Availability status.
- `IDEAL NOW` button.
- Stop/offline action.
- Eligibility rejection reason.
- Eligible booking opportunity list.
- Booking detail view.
- Accept action.
- Allocation result.
- Current allocation/trip status.

No Vendor selector should be shown to the Driver.

## 17. Audit Events

Use the existing audit framework for:

```text
IDEAL_NOW_ENABLED
IDEAL_NOW_DISABLED
IDEAL_NOW_ELIGIBILITY_FAILED
BOOKING_OPPORTUNITY_VIEWED
BOOKING_ACCEPT_ATTEMPTED
BOOKING_ACCEPTED
BOOKING_ACCEPT_REJECTED
BOOKING_ALREADY_CLAIMED
VENDOR_MISMATCH_REJECTED
TENANT_MISMATCH_REJECTED
DRIVER_ALLOCATION_COMPLETED
COMPLIANCE_BLOCKED
RACE_CONDITION_LOST
```

Never log credentials, PINs, tokens, or secrets.

## 18. Security Threat Model

Required protections:

- Server-derived Driver/Vendor identity.
- Tenant/object authorization on list and accept endpoints.
- Row locking or equivalent atomic claim.
- Revalidation at acceptance time.
- Session expiry/revocation checks.
- Compliance and conflict rechecks.
- Duplicate/replay protection.
- Minimal Driver-visible data.
- Audit events for rejected and successful actions.

## 19. Automated Test Matrix

| Test | Expected result |
|---|---|
| Active eligible Driver enables Ideal Now | Allow |
| Inactive Driver | Deny |
| Missing Vendor relationship | Deny |
| Inactive Vendor | Deny |
| Missing/ambiguous tenant | Deny |
| Active trip | Deny |
| Conflicting allocation | Deny |
| Valid Vendor booking | Show/allow |
| Cancelled booking | Deny |
| Already allocated booking | Deny |
| Cross-vendor booking | Deny |
| Cross-tenant booking | Deny |
| Submitted `vendor_id` manipulation | Deny |
| Submitted `driver_id` manipulation | Deny |
| Submitted `tenant_id` manipulation | Deny |
| Expired session | Deny |
| Driver deactivated after display | Deny acceptance |
| Vendor deactivated after display | Deny acceptance |
| Compliance expires after display | Deny acceptance |
| Two Drivers accept same booking | Exactly one succeeds |
| Duplicate acceptance | Safe conflict/no duplicate |
| Replay acceptance | Safe conflict/no duplicate |
| Invalid booking ID | Deny |
| Unauthenticated request | Deny |
| Audit event integrity | Correct event, no secrets |

## 20. Concurrency Test Strategy

Concurrency tests must use the isolated environment defined in:

```text
docs/RENTA_GO_SECURITY_TEST_ENVIRONMENT_PLAN.md
```

They must not run against the current populated `RENTAGO` schema or current
XEPDB1.

Phase 2 implementation should not be considered production-ready until the
two-Driver acceptance race has passed against synthetic data.

## 21. GPS Integration Boundary

Ideal Now is an availability state, not a GPS permission.

```text
Driver Login
    -> IDEAL NOW
    -> Booking Accepted
    -> Trip Started / Tracking Authorized
    -> Native Android/iOS GPS
    -> Trip Completed
    -> GPS Stopped
```

No GPS changes are required in this specification phase.

## 22. Implementation Sequence

1. Obtain owner approval for the conservative conflict rule.
2. Approve the availability persistence model.
3. Add the availability migration in an isolated environment.
4. Add reusable Driver eligibility service/helper.
5. Add server-side Ideal Now start/stop endpoints.
6. Add scoped opportunity query.
7. Add atomic acceptance/claim transaction.
8. Add Vendor-derived allocation.
9. Add audit events.
10. Add Driver mobile UI.
11. Add authorization tests.
12. Add isolated concurrency tests.
13. Add end-to-end synthetic booking/trip tests.
14. Validate rollback.
15. Plan native GPS integration separately.

## 23. Rollback Strategy

- Disable Ideal Now routes/UI through the application release mechanism.
- Leave existing booking and allocation routes unchanged.
- Roll back only new availability objects and data after disabling the feature.
- Preserve all existing Driver/Vendor relationships and bookings.
- Preserve audit history.
- Do not delete or rewrite existing allocation records.

## 24. Risks

- Exact business time-conflict buffer is not approved.
- Existing compliance fields are not yet one reusable allocation gate.
- No current availability persistence exists.
- Atomic booking claim mechanism is not yet implemented.
- Isolated concurrency environment is not available.
- Legacy Driver identity uses name/mobile fallback in some flows.

## 25. Final Decision

PHASE 1.6 STATUS:
COMPLETE

IMPLEMENTATION READY:
NO

IDEAL NOW PERSISTENCE:
Dedicated `driver_availability_sessions` table with one active session per Driver.

CONFLICT RULE:
Conservative same-day allocated/non-cancelled conflict rule, with approved time-window evaluation where reliable times exist.

COMPLIANCE GATE:
Reuse existing Driver/Vendor/Vehicle compliance fields in one shared server-side eligibility gate.

BOOKING ACTION:
Accept.

ATOMIC CLAIM:
Single transaction with booking row lock, full revalidation, server-derived Vendor, allocation update, audit, and commit.

VENDOR AUTHORITY:
`drivers.vendor_id` plus authenticated tenant; never client-supplied Vendor data.

DATABASE CHANGE:
Additive availability-session table required; not implemented.

API CHANGE:
New Driver availability, opportunity, and acceptance endpoints required; not implemented.

UI CHANGE:
Driver mobile Ideal Now state, opportunity list, and Accept action required; not implemented.

TEST STRATEGY:
Isolated synthetic authorization, mutation, and concurrency testing only.

IMPLEMENTATION BLOCKERS:

- Owner approval of the conservative conflict rule and buffer policy.
- Approved availability persistence migration.
- Reusable compliance gate definition.
- Isolated security/concurrency database environment.
- Final acceptance of API/UI terminology and response fields.

No application code, database schema/data, configuration, credentials,
production process, commit, or push was modified.
