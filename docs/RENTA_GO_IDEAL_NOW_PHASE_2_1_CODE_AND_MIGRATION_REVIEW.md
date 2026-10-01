# RentaGO Ideal Now Phase 2.1 — Code and Migration Review

## Scope

This was a read-only review of the Phase 2 source implementation and migration
definition. No database migration, application restart, deployment, commit, or
push was performed.

## 1. Source Change Inventory

| File | Change | Assessment |
|---|---|---|
| `app/ideal_now.py` | Eligibility, availability, opportunities, and acceptance service | Required/supporting |
| `app/routes/ideal_now.py` | Driver Ideal Now/status/opportunity/accept endpoints | Required |
| `app/main.py` | Registers Ideal Now router | Required |
| `app/templates/mobile/participant.html` | Driver Ideal Now controls | Required, incomplete UI |
| `scripts/migrate.py` | Defines availability-session table | Required, not applied |
| `db/schema/schema.sql` | Adds availability-session table/index definitions | Required, not applied |
| `docs/RENTA_GO_IDEAL_NOW_PHASE_2_IMPLEMENTATION_REPORT.md` | Implementation status report | Supporting |

No unrelated application module was intentionally changed in the Phase 2
implementation reviewed here.

## 2. Driver/Vendor Authority

The implementation derives Vendor authority through:

authenticated Driver
    -> users.emp_id / Driver lookup
    -> drivers.vendor_id
    -> vendors.tenant_id/status
```

`app/ideal_now.py` validates the Driver’s tenant and Vendor relationship.
Opportunity queries use the server-derived Vendor ID.

The acceptance path checks:

booking.tenant_id == Driver tenant
booking.vendor_id == Driver vendor_id
```

No client-supplied `vendor_id` is accepted as the authorization source.

Status: **PASS WITH LIMITATIONS**

Limitation: Driver identity fallback uses name/mobile when `users.emp_id` does
not directly resolve to `drivers.driver_id`.

## 3. Tenant Isolation

Ideal Now service operations obtain tenant context through the authenticated
user and `authorization_tenant()`/existing tenant fields.

The opportunity query filters by:

tenant_id
vendor_id
booking status/reason
unallocated Driver/Vehicle fields
```

Acceptance rechecks the locked booking tenant and Vendor.

Status: **PASS WITH LIMITATIONS**

Live cross-tenant integration testing was not performed.

## 4. Ideal Now Session

### Implemented

- `driver_availability_sessions` schema definition.
- One active-session lookup.
- `IDEAL_NOW` state.
- Stale-session check using 30 minutes.
- Start and stop operations.
- Allocation changes the session to `ALLOCATED`.

### Findings

- No dedicated heartbeat endpoint exists.
- `last_seen_at` is updated during activation/status operations, not through a
  periodic Driver heartbeat.
- Stale-session updates can occur during reads and are not consistently
  committed by every caller.
- The table has no database-level unique constraint preventing multiple active
  sessions.

Severity: **HIGH**

## 5. Same-Day Conflict

The eligibility logic checks:

- Active trips by Driver name.
- Same-day bookings by Driver name/contact.
- Non-terminal booking states.

It does not implement time-window overlap. It follows the approved conservative
same-day direction, but it does not fully distinguish all existing booking
relationships by authoritative Driver ID.

Severity: **MEDIUM**

## 6. Booking Opportunities

The opportunity query filters by:

- Driver tenant.
- Driver Vendor.
- `booking_status='1-Pending'`.
- `status_reason='Awaiting Driver & Vehicle Allocation'`.
- Empty Driver allocation.
- Empty Vehicle allocation.

Status: **PASS WITH LIMITATIONS**

Findings:

- Compliance is not fully rechecked as a dedicated shared gate for every
  vehicle/Driver condition.
- Same-day conflict logic depends on legacy Driver name/contact matching.
- Date/time eligibility is not fully enforced in the opportunity query itself.

Severity: **HIGH** before production use.

## 7. Atomic Accept

The acceptance path uses:


Status: **PARTIAL**

Findings:

- No isolated concurrent acceptance test was executed.
- The claim path does not clearly reproduce all existing Step 3 behavior,
  including the established notification and SLA event flow.
- The acceptance path uses a client-supplied `vehicle_no`, although it validates
  the vehicle under the authoritative Vendor and tenant.

Severity: **HIGH** until isolated concurrency and lifecycle tests pass.

## 8. Compliance

The service checks Driver status, Vendor status, licence expiry, police/background
fields, and Driver compliance status.

Vehicle compliance is not fully enforced as a shared acceptance gate. Vehicle
existence/status is checked, but all existing insurance/permit/fitness/PUC and
compliance rules are not centralized in the Ideal Now service.

Severity: **HIGH**

## 9. Audit

The implementation records `BOOKING_ACCEPTED` through the existing audit
mechanism.

Missing or incomplete events include:


Severity: **MEDIUM**

## 10. Database Migration Review

### New table

driver_availability_sessions
```

### Columns

availability_id VARCHAR2(40) PRIMARY KEY
tenant_id       VARCHAR2(40) NOT NULL
driver_id       VARCHAR2(40) NOT NULL
vendor_id       VARCHAR2(40) NOT NULL
status          VARCHAR2(30) NOT NULL
activated_at    TIMESTAMP NOT NULL
deactivated_at  TIMESTAMP
last_seen_at    TIMESTAMP
created_at      TIMESTAMP DEFAULT SYSTIMESTAMP
updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP
```

### Review

- Existing tables/data are not modified by the definition.
- Index definitions exist for tenant/Driver/status and tenant/Vendor/status.
- No foreign keys are defined to `drivers`, `vendors`, or `tenants`.
- No database constraint prevents multiple active sessions per Driver.
- No status check constraint exists.
- No rollback migration is supplied.

Migration status: **SAFE WITH CHANGES**

Required before application:

- Add reviewed foreign-key/index/active-session uniqueness strategy or document
  why application locking is sufficient.
- Provide an explicit rollback migration.
- Validate in the isolated Oracle environment.

The migration was not applied.

## 11. Migration Path

Existing migration command, not executed:

python scripts/migrate.py
```

It must only be run against the isolated test database after the migration has
been reviewed and validated.

## 12. UI Review

The Driver mobile template includes:

- Activate IDEAL NOW button.
- View Eligible Bookings link.
- Deactivate IDEAL NOW button.

Findings:

- The opportunities endpoint returns JSON, but the current UI does not render a
  booking opportunity list or an Accept form.
- No visible Ideal Now status/heartbeat indicator is implemented.
- No stale-session explanation is shown.
- No explicit eligibility failure display is implemented.

Severity: **HIGH** for feature completeness.

## 13. Regression Risk

Potential risks requiring testing:

- Acceptance path may not emit all existing Step 3 notifications/SLA events.
- Availability table is not present until migration application.
- Driver identity fallback may mismatch legacy Driver records.
- Existing mobile Driver UI has controls but no completed opportunity/Accept
  workflow.
- Existing allocation routes remain operational, but Ideal Now uses a parallel
  allocation path that must be reconciled with them.

## 14. Test Validation

Executed:

python -m compileall -q app tests
python -m unittest discover -s tests -q
```

Result:

33 tests passed
0 failed
```

The existing tests are not Ideal Now integration tests.

Not executed:

- Migration application.
- Database-backed Ideal Now tests.
- Atomic acceptance integration tests.
- Concurrent acceptance tests.
- Full Driver UI tests.
- Compliance scenario tests.
- Production-like database tests.

## 15. Final Review Table

| Area | Status | Evidence | Risk |
|---|---|---|---|
| Driver/Vendor authority | PASS WITH LIMITATIONS | `app/ideal_now.py`, `bookings.py` | Medium |
| Tenant isolation | PASS WITH LIMITATIONS | `authorization_tenant`, booking filters | High until integration-tested |
| Ideal Now session | PARTIAL | Availability service/table definition | High |
| Same-day conflict | PARTIAL | Name/contact-based same-day checks | Medium |
| Booking opportunities | PARTIAL | Vendor/tenant/status query | High |
| Atomic Accept | PARTIAL | Row lock and transaction present | High until concurrency-tested |
| Compliance | PARTIAL | Driver checks, incomplete vehicle gate | High |
| Audit | PARTIAL | Acceptance audit only | Medium |
| Migration | SAFE WITH CHANGES | Additive table, missing constraints/rollback | High |
| UI | PARTIAL | Controls present, opportunity UI incomplete | High |
| Tests | INCOMPLETE | Existing 33-test suite only | High |
| Regression | NOT VERIFIED | No end-to-end validation | High |
| Production safety | PASS | No migration/restart/deployment | Low |

## 16. Critical Findings

### HIGH — No completed Driver opportunity/Accept UI

The mobile page links to a JSON opportunities endpoint but does not provide a
usable booking list or Accept action.

### HIGH — No isolated concurrency validation

The atomic claim path has not been tested with simultaneous Driver requests.

### HIGH — Migration lacks explicit active-session uniqueness/rollback

The new table definition does not enforce one active session per Driver at the
database level and has no rollback migration.

### HIGH — Compliance gate is incomplete

Vehicle compliance is not fully centralized in the Ideal Now acceptance path.

### MEDIUM — Audit event coverage incomplete

Only acceptance auditing is present; activation, expiry, rejection, conflict,
and compliance events are not fully implemented.

### MEDIUM — Existing allocation event parity is uncertain

The new acceptance path may not emit every notification/SLA event performed by
the existing Step 3 allocation path.

## 17. Production Safety

- Production database changed: **NO**.
- Production configuration changed: **NO**.
- Credentials changed: **NO**.
- Supervisor changed: **NO**.
- Cloudflare changed: **NO**.
- Scheduled tasks changed: **NO**.
- Deployment performed: **NO**.
- Migration applied: **NO**.

