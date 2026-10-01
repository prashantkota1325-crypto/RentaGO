# RentaGO Security Test Environment Plan

## 1. Current Environment Constraints

The current Windows machine is production-like and must not be used for live
authorization attack testing.

Observed constraints:

- Oracle XE 21c is running locally.
- `XEPDB1` is open and read/write.
- The `RENTAGO` schema is populated.
- Port `1521` is used by the current Oracle listener.
- Port `8000` is used by the current RentaGO application.
- Cloudflare Tunnel is active.
- RentaGO Supervisor, backup, health-monitor, and permanent-service tasks exist.
- Current machine has limited free RAM and should not host a second Oracle instance.
- The current `.env` target is not to be reused or inspected for testing.

## 2. Why Production-Like Environment Must Not Be Attacked

Live attack testing could:

- Expose real customer, vendor, driver, booking, invoice, payment, or GPS data.
- Modify bookings, trips, invoices, notifications, audit records, or sessions.
- Trigger SMTP, WhatsApp, SMS, or other external delivery.
- Trigger SLA, tracking, compliance, or notification workers.
- Create or alter production-like user/session state.
- Expose the test traffic through Cloudflare.

No live HTTP attack testing should occur until an isolated environment exists.

## 3. Recommended Isolated Architecture

Use a separate company-controlled physical host or Windows VM. The current PC
is not recommended for an additional Oracle instance because available RAM is
insufficient while the existing system remains active.

```text
Separate Test Host / VM
    |
    +-- Oracle XE 21c test instance
    |     +-- Test listener
    |     +-- Test PDB/service
    |     +-- RentaGO test schema/user
    |     +-- Synthetic data only
    |
    +-- RentaGO test application
          +-- 127.0.0.1:18000
          +-- Separate process environment
          +-- Workers connected only to test Oracle
          +-- External integrations disabled
          +-- No Cloudflare Tunnel
```

## 4. Hardware Recommendation

Minimum:

- 4 vCPU.
- 8 GB RAM.
- 100 GB SSD.
- Windows 10/11 Pro or an approved equivalent Windows test host.

Preferred:

- 4 vCPU.
- 12 GB RAM or more.
- 100 GB or more SSD.
- Company-controlled administrator access.
- Private/internal networking.

## 5. Software Requirements

- Python 3.12.
- RentaGO dependencies from `requirements.txt`.
- Oracle XE 21c or an approved isolated Oracle-compatible test instance.
- SQL*Plus and Oracle client tools where required.
- 7-Zip only if isolated test backup/restore is needed.
- No production Cloudflare client/configuration.
- No production backup or restore paths.

## 6. Oracle Requirements

Proposed test-only identity:

```text
SID: RGOQA
Database: RGOQA
PDB: RGOQA_PDB
Service: RGOQA_PDB
Listener: RGOQA_LISTENER
Port: 1522
Application user/schema: RGOQA_APP
Administrator: RGOQA_ADMIN
```

These are planning names only. Nothing was created.

The test application user must not have privileges on the production-like
`RENTAGO` schema or `XEPDB1` objects.

## 7. Application Requirements

Application entry point:

```text
app.main:app
```

Future test-only launch plan:

```text
python -m uvicorn app.main:app --host 127.0.0.1 --port 18000
```

The existing application startup launches tracking, SLA, notification, and
compliance workers. They may run only after the test database and test
configuration are verified.

## 8. Required Ports

| Component | Production-like port | Proposed test port | Binding |
|---|---:|---:|---|
| Current Oracle | 1521 | Do not use | Existing environment |
| Test Oracle | Not present | 1522 | Test host/private network |
| Current RentaGO app | 8000 | Do not use | Existing environment |
| Test RentaGO app | Not present | 18000 | `127.0.0.1` only |

No test port should be exposed through Cloudflare or bound to `0.0.0.0`.

## 9. Network Isolation

The test host must:

- Bind the application only to `127.0.0.1:18000`.
- Prevent access to production Oracle port `1521`.
- Prevent access to the production-like `RENTAGO` schema.
- Avoid the production Wi-Fi/LAN path where practical.
- Use host-only/private networking or a restricted internal network.
- Use restricted RDP access only for authorized administrators.
- Have no public DNS or public application endpoint.

## 10. External Integration Isolation

Disable or omit all production integrations:

- SMTP.
- WhatsApp.
- SMS.
- Payment gateways, including Razorpay and Cashfree.
- Production webhooks.
- Production Google Maps or Mappls keys.
- Cloudflare Tunnel.
- Production backup directories.

If notification testing is required, use a local sink or synthetic provider.

## 11. Database Schema and Initialization

Base schema:

db/schema/schema.sql
```

Migration layer:

scripts/migrate.py
```

The schema contains the objects required for:

- Tenants and memberships.
- Organizations.
- Users and roles.
- Companies and employees.
- Vendors, drivers, and vehicles.
- Bookings and trips.
- Invoices and payments.
- Notifications.
- GPS logs.
- Invoice documents.
- SLA/policy/rules data.

The fresh schema must be created only on the isolated test Oracle instance.
Production import data must not be copied.

## 12. Synthetic Test-Data Model

### Tenants

- `TEN-TEST-A` / Corporate Tenant A.
- `TEN-TEST-B` / Corporate Tenant B.

### Organizations

- `CORP-TEST-A`.
- `CORP-TEST-B`.
- `VEND-TEST-A`.
- `VEND-TEST-B`.
- `RENTAGO-TEST`.

### Users

- Corporate Admin A.
- Corporate User A.
- Corporate Admin B.
- Corporate User B.
- Vendor User A.
- Vendor User B.
- Guest A.
- Guest B.
- Driver A.
- Driver B.
- Internal RentaGO User.

All names, emails, mobile numbers, IDs, and passwords must be synthetic.

### Business objects

- Corporate A/B companies.
- Corporate A/B employees.
- Vendor A/B records.
- Vendor A/B drivers.
- Vendor A/B vehicles.
- Corporate A/B bookings.
- Vendor A/B bookings.
- Guest A/B bookings.
- Trips.
- Invoices.
- Payments.
- Cancellation/refund records.
- Feedback.
- Notifications.
- Invoice documents.
- GPS/tracking records.
- Reportable booking data.

## 13. Test Accounts Required

Each test account must have:

- One explicit tenant membership.
- Correct organization ID/type.
- Correct role.
- Synthetic password or PIN.
- No production email, phone, API key, or provider account.

Guest and Driver accounts require booking-scoped mobile sessions for mobile
authorization testing.

## 14. Proposed Attack-Test Matrix

The future Phase 2B tests must cover:

- Corporate A accessing Corporate B bookings, guests, invoices, payments, GPS, reports, documents, and notifications.
- Corporate A changing tenant/company/organization parameters.
- Vendor A accessing Vendor B bookings, drivers, vehicles, billing, reports, and documents.
- Vendor A changing vendor or tenant parameters.
- Guest A accessing Guest B or arbitrary booking IDs.
- Driver A accessing Driver B trips or GPS.
- Direct booking, invoice, payment, feedback, notification, file, driver, vehicle, and vendor ID substitution.
- Unauthorized vendor allocation with database-before/database-after comparison.
- Unauthorized driver/vehicle allocation with database-before/database-after comparison.
- Cross-tenant exports and report filters.
- Tracking token/session/booking mismatches.
- Missing and ambiguous tenant memberships.
- Internal-only master-data access from external roles.
- Privilege escalation through role or organization parameters.

Every state-changing denial must verify that the test database is unchanged.

## 15. Required Environment Variables

Use a separate process environment, never the current `.env`:

```text
RENTAGO_ENVIRONMENT=test
RENTAGO_DB_HOST=<TEST_DB_HOST>
RENTAGO_DB_PORT=1522
RENTAGO_DB_SERVICE=RGOQA_PDB
RENTAGO_DB_USER=RGOQA_APP
RENTAGO_DB_PASSWORD=<TEST_APP_PASSWORD>
RENTAGO_ADMIN_USER=RGOQA_ADMIN
RENTAGO_ADMIN_PASSWORD=<TEST_ADMIN_PASSWORD>
RENTAGO_SECRET=<TEST_ONLY_SECRET>
RENTAGO_SESSION_COOKIE_SECURE=<LOCAL_TEST_SETTING>
RENTAGO_SMTP_USER=
RENTAGO_SMTP_PASSWORD=
RENTAGO_GOOGLE_MAPS_API_KEY=
RENTAGO_MAPPLS_API_KEY=
```

No configuration file should overwrite or modify the production `.env`.

## 16. Background Workers

The application automatically starts:

- Tracking worker.
- SLA worker.
- Notification worker.
- Compliance worker.

They must operate only against the test database. External delivery must be
disabled before application startup.

## 17. Reset and Repeatability

Preferred reset strategy:

1. Destroy the isolated test schema/database.
2. Recreate the isolated Oracle identity.
3. Recreate the schema from `db/schema/schema.sql`.
4. Apply reviewed migrations.
5. Load synthetic fixtures.
6. Run the attack matrix.

Do not delete individual production-like records or reuse production backups.

## 18. Current Blockers

- No separate test host or VM is currently provisioned.
- Current PC has insufficient free RAM for a safe second Oracle instance.
- No synthetic fixture loader currently exists.
- No isolated test database credentials exist.
- Hypervisor availability on the current PC was not fully verified.
- Current production-like services must remain untouched.

## 19. Exact Prerequisites Before Phase 2B

- Separate physical host or Windows VM approved by RentaGO.
- Minimum 4 vCPU, 8 GB RAM, 100 GB SSD.
- Dedicated Oracle test instance and service.
- Dedicated `RGOQA_ADMIN` and `RGOQA_APP` accounts.
- Fresh schema created without production data.
- Synthetic fixture set loaded.
- Test process environment prepared separately from `.env`.
- Test application bound to `127.0.0.1:18000`.
- Cloudflare disabled/not installed for test use.
- SMTP, WhatsApp, SMS, payment, and webhooks disabled.
- Reset/recreate procedure tested.
- Database-before/database-after comparison procedure prepared.
- Owner approval for test host and credentials.

## 20. Final Recommendation

**SEPARATE HOST OR VM REQUIRED BEFORE LIVE AUTHORIZATION TESTING**

The current production-like host and populated `RENTAGO` schema must not be
used for attack simulation.

## 21. Files/Source Inspected

- `app/main.py`
- `app/config.py`
- `app/db.py`
- `app/auth.py`
- `app/scope.py`
- `app/routes/bookings.py`
- `app/routes/mobile.py`
- `app/routes/track.py`
- `app/routes/feedback.py`
- `app/routes/reports.py`
- `app/routes/invoices.py`
- `app/routes/payments.py`
- `db/schema/schema.sql`
- `scripts/migrate.py`
- `requirements.txt`
- Existing tests under `tests/`

## 22. Changes Made

- Application source modified: **NO**.
- Database modified: **NO**.
- Production configuration modified: **NO**.
- `.env` modified: **NO**.
- Credentials modified: **NO**.
- Attack tests implemented: **NO**.
- Commit/push performed: **NO**.

## 23. Final Status

**BLOCKED UNTIL A SEPARATE ISOLATED TEST HOST/DATABASE EXISTS**
