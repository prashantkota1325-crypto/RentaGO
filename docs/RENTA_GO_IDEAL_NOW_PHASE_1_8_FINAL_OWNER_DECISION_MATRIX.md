# RentaGO Ideal Now Phase 1.8 — Final Owner Decision Matrix

## Decision 1 — Same-Day Conflict

### Recommended RentaGO rule

For the initial Year-1 release:

> Any non-cancelled, non-completed allocated booking or active trip covering
> the current service day blocks Ideal Now.

Specific behavior:

- Any allocated booking today: blocks.
- Any active trip today: blocks.
- Any future booking later today: blocks.
- Any trip ending later today: blocks.
- Multi-day booking covering today: blocks.
- Cancelled/completed/no-show terminal records: do not block once terminal
  status is authoritative.
- A booking tomorrow does not block today’s Ideal Now activation, but is
  rechecked at acceptance.
- Missing end/drop time is treated conservatively as all-day conflict.

No new travel/deadhead buffer is defined because no approved existing buffer
was identified in the current RentaGO configuration.

Owner approval required: **YES**.

Implementation consequence: one shared server-side conflict helper must be used
both when entering Ideal Now and when accepting a booking.

## Decision 2 — Ideal Now Session

Recommended state transitions:

```text
OFFLINE
  -> IDEAL_NOW       explicit Driver activation after eligibility succeeds
IDEAL_NOW
  -> OFFLINE         manual deactivation, logout, expiry, invalidation
IDEAL_NOW
  -> ALLOCATED       booking acceptance succeeds
ALLOCATED
  -> ON_TRIP         existing trip start succeeds
ON_TRIP
  -> OFFLINE         existing trip completion succeeds
```

Rules:

- One active Ideal Now session per Driver.
- New activation is rejected or closes the previous session according to the
  approved implementation policy; multiple active sessions are not allowed.
- Logout ends availability.
- Session expiry ends availability.
- Closing the application does not immediately prove the Driver is offline;
  `last_seen_at` becomes stale and the server expires the session.
- Driver deactivation, Vendor deactivation, tenant loss, or compliance failure
  ends availability.
- Booking acceptance changes state to `ALLOCATED`.
- Trip start changes state to `ON_TRIP`.
- Trip completion returns the Driver to `OFFLINE`.
- Manual deactivation is available while in `IDEAL_NOW`.

Recommended stale timeout: **15 minutes without a heartbeat**.

Owner approval required: **YES** for the 15-minute stale timeout and behavior
when a second activation is attempted.

## Decision 3 — Booking Opportunity

The final opportunity filter is:

```text
booking.tenant_id == authenticated_driver.tenant_id
booking.vendor_id == authenticated_driver.drivers.vendor_id
booking.booking_status == '1-Pending'
booking.status_reason == 'Awaiting Driver & Vehicle Allocation'
booking.driver_name IS NULL or empty
booking.vehicle_no IS NULL or empty
booking is not cancelled
booking is not completed
booking passes time/conflict rules
booking passes existing eligibility/SLA rules
Driver remains active and eligible
Vendor remains active
```

The Driver must not see unassigned Vendor bookings because acceptance must be
Vendor-bound.

Driver-visible information should be limited to booking reference, pickup/drop
operational information, date/time, vehicle category, package, and required
instructions. Internal rates, margins, confidential notes, and unrelated
customer data remain hidden.

Owner approval required: **YES** only for the final visible-field list. The
authorization filter itself is technically locked.

## Decision 4 — Acceptance

Action: **ACCEPT**.

Final sequence:

1. Authenticate Driver session.
2. Resolve Driver from the authenticated session.
3. Resolve tenant from active membership.
4. Resolve Vendor from `drivers.vendor_id`.
5. Verify Vendor status and tenant.
6. Lock and load the booking.
7. Verify booking tenant.
8. Verify booking Vendor.
9. Verify booking remains eligible and unallocated.
10. Verify Driver eligibility and conflict rules again.
11. Update Vendor/Driver allocation using server-derived values.
12. Create/update the Trip through existing helpers.
13. Write audit events.
14. Commit the transaction.
15. Return success.

If another Driver wins first, return a controlled booking-unavailable response
with no partial mutation.

Owner approval required: **NO** for the technical sequence; **YES** for final
Driver-facing wording.

## Decision 5 — Atomic Claim

Recommended mechanism:

- One database transaction.
- `SELECT ... FOR UPDATE` on the booking row.
- Recheck status, Vendor, Driver, tenant, compliance, and conflict state after
  acquiring the lock.
- Perform allocation updates in the same transaction.
- Commit only after all changes and audit records succeed.
- Rollback on any failure.

Expected concurrent result:

```text
Driver A + Driver B -> same booking
Driver A wins row lock -> one success
Driver B rechecks -> booking unavailable -> no mutation
```

Owner approval required: **NO** for the technical locking approach; isolated
concurrency testing is mandatory before production use.

## Decision 6 — Compliance

### Blocks Ideal Now activation

- Driver inactive, suspended, or terminated.
- Driver master missing.
- Vendor inactive.
- Driver Vendor relationship missing.
- Licence expired where licence validity is mandatory.
- Police verification explicitly failed.
- Background check explicitly failed.
- Driver compliance status explicitly invalid.
- Missing or ambiguous tenant membership.

### Blocks booking acceptance

All Ideal Now activation blockers, plus:

- Vehicle compliance failure where a vehicle is required for the booking.
- Vehicle document expiry where existing RentaGO rules treat it as blocking.
- Booking-specific operational or vehicle-category incompatibility.

Existing fields in `drivers`, `vehicles`, and `vendors` should be reused. No
duplicate compliance engine should be created.

Owner approval required: **YES** for which “expiring soon but not expired”
conditions are warnings versus blockers.

## Decision 7 — API

### New APIs required

```text
POST /mobile/driver/ideal-now/start
POST /mobile/driver/ideal-now/stop
GET  /mobile/driver/ideal-now/opportunities
POST /mobile/driver/ideal-now/opportunities/{booking_id}/accept
```

### Shared requirements

- Authentication: existing authenticated Driver mobile session.
- Role: Driver only.
- Tenant: server-derived active membership.
- Driver: server-derived session user and Driver master.
- Vendor: server-derived `drivers.vendor_id`.
- Client-controlled tenant/vendor/Driver IDs: rejected or ignored.
- Acceptance: atomic transaction and audit.

Existing `/mobile/{who}-login`, booking visibility, and allocation helpers
should be reused. Existing allocation URLs should not be repurposed as a
Driver-facing claim API without the full acceptance transaction.

Owner approval required: **YES** for final endpoint naming and response wording.

## Decision 8 — Database

Recommended additive table:

```text
driver_availability_sessions
```

Proposed fields:

```text
availability_id       VARCHAR2(40) PRIMARY KEY
tenant_id              VARCHAR2(40) NOT NULL
driver_id              VARCHAR2(40) NOT NULL
vendor_id              VARCHAR2(40) NOT NULL
status                 VARCHAR2(30) NOT NULL
activated_at           TIMESTAMP NOT NULL
last_seen_at           TIMESTAMP
created_at             TIMESTAMP DEFAULT SYSTIMESTAMP
updated_at             TIMESTAMP DEFAULT SYSTIMESTAMP
```

Indexes:

```text
(tenant_id, driver_id, status)
(tenant_id, vendor_id, status)
```

Business uniqueness:

```text
Only one active Ideal Now session per Driver.
```

The exact Oracle constraint/index implementation must be finalized during
Phase 2 migration design. No schema change was made.

Owner approval required: **YES** for table name, stale-session policy, and
active-session uniqueness implementation.

## Decision 9 — Driver UI

Minimum flow:

```text
Driver Login
  -> Driver Dashboard
  -> IDEAL NOW
  -> eligibility result
  -> booking opportunities
  -> booking details
  -> ACCEPT
  -> success/failure
  -> allocation/trip state
```

The UI must not expose:

- Vendor selector.
- Tenant selector.
- Internal rates or margins.
- Confidential Vendor information.
- Unnecessary customer contact information.
- Unrelated bookings.

Owner approval required: **YES** for final Driver-visible booking fields.

## Decision 10 — Audit

Required audit events:

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

Use the existing `app/audit.py` pattern. No PINs, passwords, tokens, or
secrets may be recorded.

Owner approval required: **NO** for the event categories; **YES** for final
operational reporting requirements.

## Decision 11 — Concurrency Test

Concurrency testing must use the isolated synthetic environment described in:

```text
```

Minimum test:

```text
Driver A + Driver B
        -> same booking
        -> simultaneous ACCEPT
        -> exactly one success
```

The current production-like environment must not be used.

Owner approval required: **NO**; this is a mandatory safety condition.

## Final Owner Decision Table

| # | Decision | Recommended RentaGO Rule | Owner Approval Required |
|---:|---|---|---|
| 1 | Same-day conflict | Any non-terminal allocated booking/active trip covering the current service day blocks Ideal Now | YES |
| 2 | Travel/deadhead buffer | No new buffer until an operational value is approved | YES |
| 3 | Stale availability timeout | 15 minutes without heartbeat | YES |
| 4 | Multiple active sessions | One active session per Driver | NO |
| 5 | Booking action | ACCEPT | NO |
| 6 | Opportunity pool | Same-tenant, same-Vendor, Vendor-assigned, Driver-unallocated, eligible bookings | NO |
| 7 | Compliance expiry warning | Warning unless existing policy marks the condition blocking | YES |
| 8 | Driver-visible fields | Minimum operational fields only | YES |
| 9 | Availability table | `driver_availability_sessions` | YES |
| 10 | API route naming | `/mobile/driver/ideal-now/*` convention | YES |

## Final Status

PHASE 1.8 STATUS:
COMPLETE

PHASE 2 IMPLEMENTATION READY:
NO

Remaining owner decisions:

- Approve the same-day conflict rule.
- Approve any travel/deadhead buffer.
- Approve the 15-minute stale-session timeout.
- Approve the final Driver-visible opportunity fields.
- Approve the availability table and one-active-session constraint.
- Approve final API route names.
- Approve compliance warning-versus-blocking behavior.

No application, database, configuration, credential, production process, Git,
commit, or push changes were made.
