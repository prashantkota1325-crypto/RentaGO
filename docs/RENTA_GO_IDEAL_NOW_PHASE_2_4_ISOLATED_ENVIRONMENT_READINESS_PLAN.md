# RentaGO Ideal Now Phase 2.4 — Isolated Environment Readiness Plan

## 1. Executive Summary

The current machine is not suitable for the Ideal Now integration/concurrency
environment because it is production-like and has limited free memory.

The future environment must be a separate company-controlled host or VM with:

- Dedicated Oracle test instance.
- Dedicated test credentials.
- Fresh schema.
- Synthetic data only.
- Localhost-only application.
- Disabled external delivery.
- Repeatable reset capability.

No environment was created during this phase.

## 2. Current Environment Assessment

Observed current system:

- Windows 11 Pro, 64-bit.
- Oracle XE 21c.
- Existing `XE` database and `XEPDB1` PDB.
- Populated `RENTAGO` schema.
- RentaGO application on port `8000`.
- Oracle listener on port `1521`.
- Cloudflare Tunnel active.
- Supervisor, backup, health-monitor, and permanent-service tasks active.
- Current `.env` and production-like credentials intentionally not used.

The current environment must not be used for live Ideal Now testing.

## 3. Current Resource Assessment

Observed current host:

- CPU: Intel i7-4930K, 12 logical processors.
- RAM: approximately 11.94 GB total.
- Free RAM: approximately 1.17 GB during inspection.
- Disk: sufficient free space, but memory is the limiting resource.

The current PC should not host another Oracle instance while the existing
RentaGO environment remains active.

## 4. Recommended Isolated Environment

Use a separate physical host or Windows VM:

```text
Separate Test Host / VM
    |
    +-- Oracle test instance
    |     +-- RGOQA database/PDB/service
    |     +-- RGOQA_APP schema
    |
    +-- RentaGO test application
          +-- 127.0.0.1:18000
          +-- Synthetic data only
          +-- External delivery disabled
```

The current Oracle, application, Supervisor, Cloudflare, backup, and health
systems remain untouched.

## 5. Hardware Requirements

Minimum:

- 4 vCPU.
- 8 GB RAM.
- 100 GB SSD.
- Windows 10/11 Pro or approved equivalent.

Preferred:

- 4 vCPU.
- 12 GB or more RAM.
- 100 GB or more SSD.

## 6. Software Requirements

- Python 3.12.
- Packages from `requirements.txt`.
- Oracle XE 21c or approved isolated Oracle test instance.
- SQL*Plus/Data Pump tools where required.
- No production Cloudflare client/configuration.
- No production backup or restore paths.

## 7. Database Requirements

Proposed isolated identity:

```text
SID: RGOQA
Database: RGOQA
PDB/service: RGOQA_PDB
Listener: RGOQA_LISTENER
Port: 1522
Administrator: RGOQA_ADMIN
Application user/schema: RGOQA_APP
```

Required properties:

- Separate database instance or isolated host.
- `RGOQA_APP` has access only to the test schema.
- No access to `RENTAGO` or production `XEPDB1`.
- Fresh schema from `db/schema/schema.sql`.
- Reviewed migrations only.
- No production import data.

## 8. Synthetic Data Design

### Tenants

```text
TEN-TEST-A
TEN-TEST-B
```

### Vendors

```text
VEND-TEST-A -> TEN-TEST-A
VEND-TEST-B -> TEN-TEST-B
VEND-TEST-A2 -> TEN-TEST-A
```

### Drivers

```text
Driver A1 -> VEND-TEST-A
Driver A2 -> VEND-TEST-A
Driver A3 -> VEND-TEST-A2
Driver B1 -> VEND-TEST-B
```

### Vehicles

```text
Vehicle A1 -> VEND-TEST-A
Vehicle A2 -> VEND-TEST-A
Vehicle A3 -> VEND-TEST-A2
Vehicle B1 -> VEND-TEST-B
```

### Bookings

Create synthetic scenarios for:

- Valid Driver A1 booking.
- Already allocated booking.
- Cross-Vendor booking.
- Cross-tenant booking.
- Same-day conflict.
- Future-day booking.
- Invalid Driver compliance.
- Invalid Vehicle compliance.
- Concurrent acceptance.

No real names, emails, mobile numbers, bookings, vehicles, payments, or
documents may be used.

## 9. Ideal Now Session Test Matrix

| Scenario | Expected result |
|---|---|
| Fresh eligible Driver | Ideal Now active |
| Missing Vendor | Rejected |
| Inactive Vendor | Rejected |
| Missing tenant | Rejected |
| Active trip | Rejected |
| Same-day conflict | Rejected |
| Fresh heartbeat | `last_seen_at` updated |
| Stale heartbeat over 30 minutes | Session inactive |
| Duplicate active session | Rejected or existing session reused |
| Logout/session expiry | No further acceptance |
| Wrong Driver | Rejected |
| Wrong Vendor | Rejected |

## 10. Compliance Test Matrix

### Driver cases

- Active and valid: allow.
- Inactive: reject.
- Suspended: reject.
- Expired licence: reject.
- Failed police/background check: reject.
- Invalid compliance status: reject.
- Near-expiry but still valid: warning or allow according to approved policy.

### Vehicle cases

- Active and compliant: allow.
- Inactive/scrapped: reject.
- Failed compliance: reject.
- Expired insurance/permit/fitness/PUC: reject where policy requires.
- Missing required document: reject where policy requires.

## 11. Tenant/Vendor Security Matrix

| Attempt | Expected |
|---|---|
| Driver A1 → Vendor A booking | Allow if eligible |
| Driver A1 → Vendor A2 booking | Deny |
| Driver A1 → Vendor B booking | Deny |
| Driver A1 → Tenant B booking | Deny |
| Driver A1 submits Vendor B ID | Deny |
| Driver A1 submits Tenant B ID | Deny |
| Driver A1 submits Driver B ID | Deny |
| Driver A1 submits Vehicle B ID | Deny |
| Unauthenticated acceptance | Deny |
| Expired session acceptance | Deny |

## 12. Concurrency Test Design

Setup:

- Driver A1 and Driver A2.
- Same Tenant A.
- Same Vendor A.
- Same active Ideal Now eligibility.
- Same eligible booking.

Execution:

- Submit two Accept requests simultaneously from separate sessions.
- Observe HTTP/API responses.
- Inspect final booking, Vendor, Driver, Trip, and audit state.

Expected:

- Exactly one success.
- Exactly one Driver allocation.
- Exactly one Vendor allocation.
- One controlled conflict response.
- No partial transaction.
- No duplicate Trip/allocation record.

This test must not run against the current production-like database.

## 13. Migration Test Plan

Future isolated sequence:

1. Create fresh synthetic test database.
2. Apply baseline schema.
3. Apply reviewed migrations.
4. Verify availability table, indexes, and uniqueness behavior.
5. Load synthetic fixtures.
6. Run Ideal Now integration tests.
7. Run isolated concurrency tests.
8. Test rollback/reversal if supported.
9. Verify no unrelated schema changes.
10. Destroy and recreate the isolated test database.

No migration was applied.

## 14. Database Reset Strategy

Preferred strategy:

- Destroy and recreate the isolated test database/schema.
- Reapply baseline schema and reviewed migrations.
- Reload synthetic fixtures.

Individual-record deletion is not preferred because it is harder to guarantee
complete cleanup and repeatability.

## 15. External Integration Isolation

Disable or omit:

- SMTP.
- WhatsApp.
- SMS.
- Payment gateways.
- Production webhooks.
- Production maps keys.
- Cloudflare Tunnel.
- Production backup directories.

Use a local test sink or no transport for notification testing.

## 16. Network/Port Isolation

Recommended test allocation:

| Component | Test configuration |
|---|---|
| Oracle test listener | `1522` |
| RentaGO test application | `127.0.0.1:18000` |
| Public DNS | None |
| Cloudflare | Not installed/started |
| Production Oracle `1521` | Unreachable from test environment |
| Production app `8000` | Not used |

## 17. Security Boundary

Production credentials: **FORBIDDEN**

Production data: **FORBIDDEN**

Production database: **FORBIDDEN**

Production-like `RENTAGO`: **FORBIDDEN**

Real customer/vendor/Driver data: **FORBIDDEN**

Real payments/notifications: **FORBIDDEN**

Synthetic test data: **REQUIRED**

Separate credentials: **REQUIRED**

Separate database: **REQUIRED**

Separate configuration: **REQUIRED**

## 18. Success Criteria

The isolated environment is ready only when:

1. Independent database exists.
2. No production data exists.
3. No production credentials exist.
4. Baseline schema can be recreated.
5. Ideal Now migration can be applied and inspected.
6. Synthetic tenants/vendors/Drivers/vehicles/bookings can be loaded.
7. Heartbeat persistence can be tested.
8. Stale-session behavior can be tested.
9. Compliance can be tested.
10. Tenant/Vendor isolation can be tested.
11. Accept transaction can be tested.
12. Concurrent Accept can be tested.
13. External delivery cannot reach real recipients.
14. Database reset is repeatable.

## 19. Phase 2.5 Prerequisites

- Separate physical host or VM.
- Dedicated Oracle test instance.
- Dedicated test credentials.
- Fresh synthetic database.
- Isolated process-level configuration.
- Localhost-only application binding.
- External integrations disabled.
- Synthetic fixture loader.
- Migration validation plan approved.
- Concurrency test plan approved.

## 20. Risks and Limitations

- Current production-like environment cannot be used for validation.
- No isolated database is currently available.
- Migration validation is pending.
- Concurrency validation is pending.
- Existing test suite is source-level and not database-backed Ideal Now testing.
- External notification isolation must be verified before integration testing.

## 21. Final Recommendation

Phase 2.4 readiness work is complete as a plan only. The next phase must provision
the isolated environment before any migration or database-backed Ideal Now test.

PHASE 2.4 STATUS: COMPLETE

ISOLATED ENVIRONMENT CREATED: NO

MIGRATION APPLIED: NO

DATABASE MODIFIED: NO

APPLICATION MODIFIED: NO

PRODUCTION DATABASE TOUCHED: NO

PRODUCTION CONFIGURATION TOUCHED: NO

PRODUCTION SERVICES TOUCHED: NO

CONCURRENCY TEST EXECUTED: NO

PHASE 2.5 ENVIRONMENT CREATION:
NOT YET AUTHORIZED BY THIS PHASE

PRODUCTION READY:
NO
