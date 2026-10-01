# RentaGO Ideal Now Final Specification

## 1. Executive Summary

RentaGO already has the authoritative Driver-to-Vendor relationship:

```text
drivers.vendor_id -> vendors.vendor_id
```

It also has tenant-aware booking, Vendor, Driver, Vehicle, Trip, session, and
allocation structures.

Ideal Now should be implemented as a small availability and booking-opportunity
layer above the existing booking/allocation workflow. It must not create a new
Vendor relationship or allow the client to select a Vendor.

Implementation is not approved yet because:

- Ideal Now persistence does not currently exist.
- Exact business time-conflict rules require owner approval.
- Compliance allocation gates are incomplete.
- Atomic concurrent booking claim behavior requires isolated testing.
- No isolated concurrency-test database is currently available.

## 2. Existing Architecture Findings

### Driver

Table: `drivers`

Relevant fields:

```text
driver_id
tenant_id
vendor_id
driver_name
mobile
license_expiry
police_verification
background_check
compliance_status
status
```

### Vendor

Table: `vendors`

Relevant fields:

```text
vendor_id
tenant_id
vendor_name
status
kyc_status
agreement_status
```

### Booking

Table: `bookings`

Relevant fields:

```text
booking_id
tenant_id
vendor_id
vendor_name
driver_name
driver_contact
vehicle_no
pickup_date
pickup_time
drop_date
drop_time
booking_status
status_reason
```

### Trips

Table: `trips`

Relevant fields:

```text
trip_id
tenant_id
booking_id
trip_status
actual_start_dt
actual_end_dt
driver_name
vehicle_no
```

### Existing routes

```text
POST /bookings/{booking_id}/allocate/vendor
POST /bookings/{booking_id}/allocate/driver
POST /mobile/{who}-login
GET  /mobile/{who}
```

## 3. Driver-Vendor Authority Model

The authoritative Vendor is derived from the authenticated Driver’s registered
Driver master record:

```text
authenticated Driver
    -> authenticated tenant
    -> drivers record
    -> drivers.vendor_id
    -> vendors record
```

The client must never provide the authoritative `vendor_id`.

The booking allocation must use the server-derived Driver Vendor and must
reject:

- A submitted Vendor ID that differs from `drivers.vendor_id`.
- A submitted Vendor name that differs from the authorized Vendor.
- A booking from another tenant.
- A booking already assigned to another Vendor.

## 4. Ideal Now Business Definition

Ideal Now means:

> The authenticated Driver is currently available to accept an eligible
> RentaGO booking through the Driver’s registered Vendor.

Ideal Now does not mean:

- Permanent availability.
- Permanent GPS tracking.
- Permission to access all bookings.
- Permission to choose a Vendor.
- Permission to bypass Driver compliance.

## 5. Eligibility Rules

### Mandatory blockers

- User is not authenticated.
- User role is not Driver.
- Driver user is inactive.
- Driver master record is missing.
- Driver tenant is missing or ambiguous.
- Driver Vendor relationship is missing.
- Vendor is inactive.
- Vendor tenant differs from Driver tenant.
- Driver is suspended or terminated.
- Driver has an active trip.
- Driver has a conflicting allocation.
- Mandatory Driver compliance is invalid.

### Non-blocking or warning conditions

These require product approval before implementation:

- Documents expiring soon but not expired.
- Missing optional profile information.
- Low rating.
- Missing language/profile metadata.

The same compliance gate used for ordinary Driver allocation should be reused.
The current allocation path does not yet enforce every Driver/Vehicle document
condition, so this gate must be defined before Ideal Now is enabled.

## 6. Current-Day / Time Conflict Rules

The current model provides pickup/drop dates and times, booking status, trip
status, and actual trip times, but no dedicated conflict engine.

Recommended rule:

- Exclude cancelled and completed bookings.
- Treat active trips as conflicts.
- Treat bookings with an assigned Driver as conflicts when their operational
  windows overlap.
- Treat missing end/drop time as an all-day or conservative conflict.
- Treat multi-day bookings as conflicts for every covered day.
- Include existing Driver reporting buffer and estimated travel time where
  available.
- Recheck the rule again during acceptance.

Example:

```text
Existing 14:00-16:00
New      15:00-17:00
Result   CONFLICT
```

```text
Existing 09:00-11:00
New      14:00-16:00
Result   Potentially available, subject to travel/reporting buffer
```

Product owners must approve the buffer and missing-time behavior before coding.

## 7. Compliance Gate

Reuse existing Driver and Vehicle fields:

- Driver `status`.
- Driver `license_expiry`.
- Driver `police_verification`.
- Driver `background_check`.
- Driver `compliance_status`.
- Vendor `status`.
- Vehicle status and compliance dates when a vehicle is already assigned.

Ideal Now should not be enabled when a mandatory Driver document is expired,
failed, or explicitly non-compliant.

The compliance worker’s expiry events are notifications/SLA signals; they are
not by themselves an allocation authorization gate.

## 8. State Machine

Recommended states:

```text
OFFLINE
   ↓
IDEAL_NOW
   ↓ booking accepted
ALLOCATED
   ↓ trip started
ON_TRIP
   ↓ trip completed
OFFLINE
```

Transitions:

- Driver login does not automatically enable Ideal Now.
- Driver explicitly starts Ideal Now after eligibility validation.
- Driver may stop Ideal Now while not allocated.
- Booking acceptance changes state to `ALLOCATED`.
- Trip start changes state to `ON_TRIP`.
- Trip completion changes state to `OFFLINE`.
- Logout/session expiry stops or invalidates availability.
- Vendor deactivation stops availability.
- Driver deactivation stops availability.
- Compliance failure prevents new acceptance and should end active availability.

## 9. Booking Opportunity Rules

An Ideal Now Driver may see only bookings that are:

- In an existing eligible unallocated state.
- In the Driver’s tenant.
- Not cancelled or completed.
- Not already assigned to a Vendor/Driver.
- Compatible with the allowed pickup window.
- Compatible with Driver capabilities where such data exists.
- Eligible under the current allocation/SLA rules.

Minimum Driver-visible information should be limited to:

- Booking reference.
- Pickup date/time.
- Pickup city/address as operationally required.
- Drop city/address as operationally required.
- Vehicle category/type.
- Package/duration information needed for acceptance.

Do not expose margins, internal rates, unrelated customer data, or other
Vendors’ confidential operational information.

## 10. Accept/Request/Claim Recommendation

Recommended terminology: **Accept**.

Flow:

```text
Driver sees eligible opportunity
    ↓
Driver taps Accept
    ↓
Server revalidates
    ↓
Server atomically claims booking
    ↓
Server derives Driver Vendor
    ↓
Booking is allocated to that Vendor and Driver
```

No separate approval workflow is required unless RentaGO operations policy
requires it.

## 11. Atomic Allocation Design

The future acceptance endpoint must use one transaction:

1. Authenticate Driver session.
2. Lock/retrieve booking row.
3. Recheck booking status and Vendor allocation.
4. Recheck Driver status, Vendor, tenant, compliance, and conflicts.
5. Derive Vendor from `drivers.vendor_id`.
6. Update booking Vendor/Driver allocation.
7. Create/update Trip state using existing workflow.
8. Audit success.
9. Commit.

If any validation fails, rollback and return a safe business message.

The current code does not expose a dedicated atomic Ideal Now claim operation;
concurrency behavior must be implemented and tested separately.

## 12. Vendor-Bound Security

For Vendor portal requests:

```text
authorization_tenant(user)
organization_id=VEND-<id>
drivers.vendor_id
booking.vendor_id
```

The browser must not control the authoritative Vendor.

Existing hardened allocation paths now validate the authenticated Vendor before
Vendor lookup/mutation and scope Driver/Vehicle lookup by booking tenant and
Vendor.

Ideal Now must reuse this exact authority model.

## 13. Tenant Isolation

External requests must fail closed when:

- Tenant context is missing.
- Tenant membership is ambiguous.
- Driver organization is missing or invalid.
- Vendor tenant does not match Driver tenant.
- Booking tenant does not match Driver tenant.

No request parameter may override the authenticated tenant or Vendor.

## 14. API Specification

Proposed paths, subject to existing mobile route conventions:

```text
POST /mobile/driver/ideal-now/start
POST /mobile/driver/ideal-now/stop
GET  /mobile/driver/ideal-now/opportunities
POST /mobile/driver/ideal-now/opportunities/{booking_id}/accept
```

### Start

- Authenticated Driver session required.
- No client tenant/vendor/driver ID trusted.
- Returns current availability state or a safe rejection reason.

### Opportunities

- Authenticated Driver session required.
- Returns only eligible bookings for the Driver’s tenant and business scope.
- Does not expose confidential commercial data.

### Accept

- Authenticated Driver session required.
- Booking ID is only an object selector, not authorization.
- Server derives Driver and Vendor.
- Revalidates all eligibility and conflict rules.
- Uses atomic claim behavior.

## 15. Database Specification

A dedicated availability table is recommended because no existing durable
Driver availability state was found.

Conceptual table only:

```text
driver_availability
    availability_id
    tenant_id
    driver_id
    vendor_id
    status
    started_at
    ended_at
    last_updated_at
    created_at
    updated_at
```

Recommended constraints/indexes:

- Primary key on `availability_id`.
- Index on `(tenant_id, driver_id, status)`.
- Index on `(tenant_id, vendor_id, status)`.
- Application/transaction rule allowing only one active Ideal Now session per
  Driver.
- Vendor ID must be server-derived from the Driver relationship.

No schema change was made.

## 16. UI Specification

Driver mobile UI should add:

- Current availability status.
- `IDEAL NOW` start action.
- Stop/offline action.
- Eligibility rejection reason.
- Eligible booking opportunities.
- Accept action.
- Allocation confirmation.
- Current trip/tracking status.

The UI must not contain a Vendor selector for Driver acceptance.

## 17. Audit Events

Recommended events:

```text
IDEAL_NOW_ENABLED
IDEAL_NOW_DISABLED
IDEAL_NOW_REJECTED
OPPORTUNITY_VIEWED
BOOKING_ACCEPT_ATTEMPTED
BOOKING_ACCEPTED
BOOKING_ACCEPT_REJECTED
BOOKING_ALLOCATION_CREATED
VENDOR_AUTHORIZATION_FAILED
CONFLICT_REJECTED
COMPLIANCE_REJECTED
RACE_CONDITION_LOST
```

Never log passwords, PINs, tokens, or secrets.

## 18. Security Threat Model

Threats:

- Vendor ID manipulation.
- Tenant ID manipulation.
- Driver ID manipulation.
- Booking ID substitution.
- Cross-tenant opportunity access.
- Cross-vendor opportunity access.
- Duplicate booking acceptance.
- Stale eligibility after opportunity display.
- Session expiry during acceptance.
- Vendor deactivation during acceptance.
- Compliance expiry during acceptance.
- Replay of an acceptance request.

Required controls:

- Server-derived identity.
- Tenant/object authorization.
- Atomic claim.
- Idempotency/replay protection.
- Revalidation at acceptance time.
- Audit events.
- Isolated concurrency testing.

## 19. Automated Test Matrix

Tests must cover:

- Active Driver enters Ideal Now.
- Inactive Driver rejected.
- Missing Vendor rejected.
- Inactive Vendor rejected.
- Missing/ambiguous tenant rejected.
- Active trip rejected.
- Conflicting trip rejected.
- Valid opportunity allowed.
- Cancelled/already allocated booking rejected.
- Cross-vendor and cross-tenant requests rejected.
- Vendor/Driver/Tenant parameter tampering rejected.
- Expired session rejected.
- Driver deactivated after opportunity display rejected at acceptance.
- Vendor deactivated after opportunity display rejected at acceptance.
- Compliance invalidated after display rejected at acceptance.
- Two Drivers accepting one booking: exactly one succeeds.
- Duplicate/replayed acceptance rejected safely.
- Logout/session expiry stops further actions.
- Audit event correctness.

## 20. Concurrency Test Strategy

Use only the isolated security-test database with synthetic data.

Scenario:

```text
Vendor A -> Driver A
Vendor B -> Driver B
Booking X -> OPEN/unallocated
```

Send two acceptance requests concurrently.

Expected:

- Exactly one transaction succeeds.
- The other receives “Booking is no longer available.”
- Booking has only one final Vendor/Driver allocation.
- No duplicate Trip/allocation record is created.
- Audit records identify the winner and rejected attempt.

## 21. GPS Integration Boundary

Ideal Now must not start continuous GPS.

Future relationship:

```text
Driver Login
    ↓
IDEAL NOW
    ↓
Booking Accepted
    ↓
Trip Started / Tracking Authorized
    ↓
Native Android Foreground Location Service
    ↓
Existing GPS API and storage
    ↓
Trip Completed
    ↓
Tracking Stopped
```

## 22. Implementation Sequence

1. Approve exact eligibility and time-conflict rules.
2. Approve availability persistence model.
3. Add server-side availability helpers/table if approved.
4. Add Driver Ideal Now start/stop endpoints.
5. Add opportunity query with tenant/Vendor scope.
6. Add atomic acceptance/allocation endpoint.
7. Add audit events.
8. Add Driver mobile UI.
9. Run isolated authorization tests.
10. Run isolated concurrency tests.
11. Run end-to-end booking/trip tests.
12. Integrate native locked-screen GPS later.

## 23. Rollback Strategy

- Disable Ideal Now routes/UI through the application release mechanism.
- Keep existing allocation routes unchanged.
- If a new availability table is introduced, remove only the new feature data
  after disabling the feature and after an approved rollback review.
- Do not alter existing booking/vendor/Driver relationships.
- Preserve existing GPS/trip workflows.

## 24. Risks

- No existing availability persistence exists.
- Time-conflict buffers are not finalized.
- Existing allocation compliance gates are incomplete.
- Atomic claim/locking is not currently implemented for Ideal Now.
- Native mobile GPS is a future dependency.
- Isolated concurrency environment is not yet available.
- Legacy Driver identity uses name/mobile fallback in some paths.

## 25. Final Decision

PHASE 1.5 STATUS:
COMPLETE

IDEAL NOW PERSISTENCE:
Add a dedicated tenant/Driver/Vendor-scoped availability-session model. Do not overload `drivers.status`.

CONFLICT RULE:
Use active-trip and time-window overlap checks with conservative handling for missing/end times. Product approval is required for travel/reporting buffers.

COMPLIANCE GATE:
Reuse existing Driver/Vendor/Vehicle compliance fields and make mandatory invalid/expired conditions block Ideal Now and acceptance.

BOOKING ACTION:
Use **Accept** for the Driver action, followed by server-side allocation.

ATOMIC CLAIM:
Use one transaction with booking row locking, availability revalidation, Driver/Vendor revalidation, and final allocation update.

VENDOR AUTHORITY:
Derive Vendor from authenticated Driver master `drivers.vendor_id`; reject all client-supplied Vendor overrides.

DATABASE CHANGE:
Likely required for durable availability state; additive only and not implemented.

API CHANGE:
New mobile availability/opportunity/acceptance endpoints will likely be required; not implemented.

UI CHANGE:
Driver mobile Ideal Now state, eligibility status, opportunity list, and Accept action required; not implemented.

TEST STRATEGY:
Isolated synthetic authorization, object-access, allocation-mutation, and concurrent-claim tests.

IMPLEMENTATION READY:
NO

IMPLEMENTATION BLOCKERS:

- Time-conflict policy requires business approval.
- Availability persistence model requires approval.
- Compliance gate must be finalized.
- Atomic acceptance design requires isolated concurrency testing.
- Current environment is not suitable for live attack/concurrency tests.

No application code, database schema/data, configuration, credentials, runtime process, scheduled task, Git history, commit, or deployment was modified.
