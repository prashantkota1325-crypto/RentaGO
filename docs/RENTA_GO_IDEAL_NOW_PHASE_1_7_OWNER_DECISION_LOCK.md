# RentaGO Ideal Now Phase 1.7 — Owner Decision Lock

## Technically Locked

The following decisions remain locked from Phase 1.6:

- Driver Vendor authority comes from `drivers.vendor_id`.
- Tenant isolation is server-side and fail-closed.
- Driver cannot submit or select an authoritative Vendor.
- Booking acceptance is `Accept`.
- Acceptance requires a transaction, row lock/equivalent, and full revalidation.
- Ideal Now is not continuous GPS.
- GPS begins only through the existing authorized trip/tracking lifecycle.
- Concurrency testing uses an isolated synthetic environment.

## Owner Business Decision Required

The remaining decisions are listed explicitly in Section 6 and Section 24.

## 1. Existing Architecture Findings

- Driver master: `drivers`.
- Vendor master: `vendors`.
- Driver Vendor relationship: `drivers.vendor_id`.
- Tenant relationship: `tenant_id`, `tenant_memberships`, and organization IDs.
- Booking Vendor relationship: `bookings.vendor_id`.
- Booking Driver fields: `driver_name`, `driver_contact`, `vehicle_no`.
- Trip relationship: `trips.booking_id`.
- Driver login: `/auth/driver-login` and `/mobile/driver-login`.
- Driver mobile session: `user_sessions.mobile_booking_id`.
- Existing allocation routes:
  - `POST /bookings/{booking_id}/allocate/vendor`.
  - `POST /bookings/{booking_id}/allocate/driver`.
- Existing scope: `app/scope.py`.
- Existing audit: `app/audit.py:audit()`.
- Existing Driver availability state: **none identified**.
- Existing atomic Ideal Now claim endpoint: **none identified**.

## 2. Driver-Vendor Authority

```text
Authenticated Driver
    -> users identity/session
    -> drivers.driver_id
    -> drivers.vendor_id
    -> vendors.vendor_id
    -> booking.vendor_id
```

Required validation:

```text
Driver tenant = Vendor tenant = Booking tenant
Driver vendor_id = Booking vendor_id
Vendor status = Active
```

Client-supplied `vendor_id`, `tenant_id`, `driver_id`, or organization values
must never establish authorization.

## 3. Ideal Now Business Definition

Ideal Now means:

> An authenticated eligible Driver is available to accept an eligible RentaGO
> booking through the Driver’s registered Vendor.

It does not start GPS, create a trip, or grant access to all bookings.

## 4. Eligibility Rules

### Blocking

- No authenticated Driver session.
- User role is not Driver.
- User inactive.
- Driver master missing.
- Tenant membership missing or ambiguous.
- `drivers.vendor_id` missing.
- Vendor missing, inactive, or cross-tenant.
- Driver inactive, suspended, or terminated.
- Active trip exists.
- Blocking allocation conflict exists.
- Mandatory compliance is invalid or expired.

### Non-blocking

- Valid documents approaching expiry, unless policy marks them blocking.
- Missing optional profile metadata.
- Missing non-operational rating/language information.

The compliance gate must reuse existing Driver/Vendor/Vehicle fields and any
future shared eligibility helper. A second compliance engine must not be built.

## 5. Availability Persistence Decision

### Recommendation

A dedicated table is required for durable availability and stale-session
handling. Existing `drivers.status` is a master-record status, not a live
availability session.


```text
driver_availability_sessions
    availability_id       VARCHAR2(40) PRIMARY KEY
    tenant_id              VARCHAR2(40) NOT NULL
    driver_id              VARCHAR2(40) NOT NULL
    vendor_id              VARCHAR2(40) NOT NULL
    status                 VARCHAR2(30) NOT NULL
    activated_at           TIMESTAMP NOT NULL
    deactivated_at         TIMESTAMP
    last_seen_at           TIMESTAMP
    created_at             TIMESTAMP DEFAULT SYSTIMESTAMP
    updated_at             TIMESTAMP DEFAULT SYSTIMESTAMP
```

### Status values

```text
OFFLINE
IDEAL_NOW
ALLOCATED
ON_TRIP
```

`COMPLETED` is represented by the existing Trip/Booking terminal states and
does not need to be a persistent availability state.


- One active availability session per Driver.
- A new activation closes/rejects an existing active session according to the
  approved session policy; it must not create multiple active sessions.
- Logout/session expiry makes the session unavailable for new acceptance.
- A stale `last_seen_at` must transition the session to `OFFLINE`.
- The exact stale timeout requires owner approval.
- Allocation changes the state to `ALLOCATED`.
- Trip start changes it to `ON_TRIP`.
- Trip completion, cancellation, deactivation, Vendor invalidation, or
  compliance failure ends availability.

## 6. Current-Day / Time-Conflict Rule

### Recommended initial Year-1 rule

Use a conservative rule:

- Active trip blocks Ideal Now.
- Any non-cancelled, non-completed allocated booking on the current service day
  blocks Ideal Now.
- Multi-day allocation covering the current day blocks Ideal Now.
- Missing end/drop time is treated as an all-day conflict.
- Future-date bookings do not block current Ideal Now activation, but are checked
  during acceptance.
- Completed, cancelled, and authoritative no-show terminal records do not block.

This is safer than optimistic overlap calculations because the current model does
not guarantee reliable end times for every booking.


Year 1 or whether a later time-window engine should be introduced.

invented silently.



