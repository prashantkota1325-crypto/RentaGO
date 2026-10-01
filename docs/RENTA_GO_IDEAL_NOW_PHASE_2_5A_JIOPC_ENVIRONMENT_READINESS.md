# RentaGO Ideal Now Phase 2.5A — JioPC Environment Readiness

## 1. Executive Summary

The observed machine does not match the JioPC Ultra specification supplied by
the owner and is not safe for isolated validation setup.

Observed machine:

- Windows 11 Pro, build 22621, 64-bit.
- Intel i7-4930K, 12 logical processors.
- Approximately 11.94 GB total RAM.
- Approximately 0.48 GB free RAM during inspection.
- Existing Oracle XE/RentaGO/Cloudflare production-like processes active.
- Existing application on `0.0.0.0:8000`.
- Existing Oracle listener on port `1521`.
- Firewall profiles reported disabled.

Status: **BLOCKED**.

This machine must not be used to create the isolated test Oracle or test
application environment.

## 2. JioPC Hardware Assessment

The supplied JioPC specification was:

```text
8 vCPU
16 GB RAM
1 TB storage
```

The observed hardware was:

```text
CPU: Intel i7-4930K
Logical processors: 12
RAM: approximately 11.94 GB
Free RAM: approximately 0.48 GB
```

The observed hostname was not identified as a separate JioPC environment.

Status: **FAIL — wrong/uncertain host and insufficient available memory**.

## 3. Operating System Assessment

- OS: Windows 11 Pro.
- Version: `10.0.22621`.
- Architecture: 64-bit.
- PowerShell: Available.
- Python: 3.12.10 available.
- Administrator capability: Not elevated/verified for installation.
- Reboot authorization: Not requested or used.

Status: **PARTIAL**.

## 4. Software Inventory

| Component | Status | Notes |
|---|---|---|
| Git | Not installed/available | Git executable unavailable |
| Python | Installed | Version 3.12.10 |
| pip | Installed | Available with Python |
| venv capability | Likely available through Python | Not created |
| Java/JDK | Not installed/available | Required for Android tooling, not this phase’s setup |
| Oracle XE | Installed | Existing production-like instance |
| SQL*Plus | Installed | Existing Oracle client tool |
| SQL Developer | Not verified | Not required for this preflight |
| PostgreSQL | Not verified | Not required by current RentaGO architecture |
| Node.js/npm | Not installed/available | Not required for current Python web app |
| Docker | Not installed/available | Not required for the planned Windows setup |
| WSL | Executable available | Distribution state not verified |
| curl | Installed | Available |
| OpenSSL | Not found | Not required for initial setup |

No software was installed.

## 5. Oracle Assessment

Existing Oracle environment:

- Oracle XE 21c installed.
- `OracleServiceXE`: Running.
- Oracle listener: Running.
- Existing listener port: `1521`.
- Existing `XEPDB1`: Production-like and populated.
- Existing `RENTAGO` schema: Production-like.

No test Oracle instance, test PDB, test service, test listener, schema, or user
was created.

The existing Oracle installation must not be reused for Phase 2.5B testing.

## 6. Network Assessment

- Active Wi-Fi interface: Present.
- Network profile: Public.
- Current Oracle listener: Bound broadly on port `1521`.
- Current RentaGO application: Bound to `0.0.0.0:8000`.
- Cloudflared: Running.
- Windows Firewall profiles: Reported disabled during inspection.

This is unsuitable for isolated test setup without a separate host/network
boundary.

## 7. Port Assessment

| Component | Current state | Test plan |
|---|---|---|
| Existing Oracle | `1521` listening | Do not use |
| Existing RentaGO app | `8000` listening on all interfaces | Do not use |
| Test Oracle | `1522` not currently listening | Use only on separate host |
| Test RentaGO app | `18000` not currently listening | Bind only to `127.0.0.1` on separate host |

No ports were changed.

## 8. Source Code Availability

The RentaGO source copy is present in the current workspace.

The source contains:

- FastAPI application.
- Oracle schema and migrations.
- Existing Ideal Now implementation.
- Tests.
- Documentation.

The current workspace also contains production-like local configuration/data
artifacts that must not be copied to the test environment, including `.env` and
populated import data. Their contents were not displayed.

Git was not available for repository verification.

Status: **PARTIAL**.

## 9. Secret/Production Data Boundary

- Production credentials: Must not be copied.
- Production `.env`: Must not be copied.
- Production Oracle/XEPDB1: Must not be used.
- Populated import data: Must not be copied.
- Production backups: Must not be restored.
- Cloudflare credentials: Must not be copied.
- SMTP/payment/WhatsApp/SMS credentials: Must not be copied.
- Real customer/vendor/Driver data: Must not be copied.

The current host remains production-like and is not a safe staging boundary.

## 10. Proposed Isolated Directory Structure

On the future JioPC/test host:

```text
RentaGO_Isolated\
    app\
    tests\
    db\
    scripts\
    logs\
    reports\
    synthetic_data\
    test_backups\
    venv\
```

The production `.env`, populated import data, production backups, cookies,
logs, keys, and credentials must not be copied into this directory.

## 11. Proposed Database Isolation

Future test identity:

```text
SID: RGOQA
Database: RGOQA
PDB/service: RGOQA_PDB
Listener: RGOQA_LISTENER
Port: 1522
Admin: RGOQA_ADMIN
Application user/schema: RGOQA_APP
```

The application user must have no access to production `RENTAGO` or
production-like `XEPDB1`.

The schema must be created fresh and populated only with synthetic records.

## 12. Synthetic Test Data Plan

Required synthetic data:

- Tenant A and Tenant B.
- Vendor A1, Vendor A2, and Vendor B1.
- Driver A1, A2, A3, and B1.
- Vehicles associated with each Vendor.
- Eligible, allocated, cross-Vendor, cross-tenant, same-day-conflict,
  future-day, invalid-compliance, and concurrency-test bookings.
- Trips, invoices, payments, feedback, notifications, audit records, and
  Ideal Now availability sessions.

No real data may be copied.

## 13. Resource Capacity Assessment

### Current observed machine

- CPU: Technically sufficient.
- RAM: Not sufficient; only approximately 0.48 GB free.
- Disk: Sufficient.
- Existing process load: Production-like Oracle, application, and Cloudflare.

Classification: **NOT RECOMMENDED**.

### Future test host

- Minimum RAM: 8 GB.
- Recommended RAM: 12 GB.
- Preferred RAM: 16 GB.
- Minimum CPU: 4 vCPU.
- Expected storage: 100 GB minimum.

## 14. Required Software Installation Plan

Installation was not performed.

Future JioPC requirements:

| Component | Purpose | Administrator rights | Reboot risk |
|---|---|---|---|
| Python 3.12 | Application/tests | Possibly | Low |
| Python dependencies | RentaGO runtime | Usually not if venv | Low |
| Oracle XE/test database | Test persistence | Yes | Possible |
| SQL*Plus/Data Pump | Oracle setup/recovery | Possibly | Low/possible |
| Git | Source retrieval | Possibly | Low |
| Java/Android tools | Not required for this phase | Not applicable | Not applicable |

Any installation requiring elevation or reboot requires explicit owner approval.

## 15. Security Boundary

```text
Current production-like machine
    X  No connection from test environment

Separate JioPC/test host
    +-- isolated source
    +-- isolated Python environment
    +-- isolated Oracle instance
    +-- synthetic data
    +-- 127.0.0.1:18000 application
    +-- no Cloudflare
    +-- no external delivery
```

## 16. Risks

- The observed machine is not the supplied JioPC specification.
- Free RAM is insufficient for another Oracle instance.
- Existing production-like processes are active.
- Current application and Oracle ports are already occupied.
- Cloudflare is running.
- Firewall profiles were reported disabled.
- Git is unavailable for source provenance verification.
- No isolated test database exists on the observed host.
- No synthetic fixture loader is currently available.

## 17. Prerequisites

- Confirm that the work is being performed on the actual JioPC Ultra.
- Confirm hardware matches 8 vCPU/16 GB/1 TB specification.
- Confirm a separate test host identity.
- Provision isolated Oracle test instance.
- Create separate test users and credentials.
- Create a clean source copy without production artifacts.
- Prepare synthetic fixtures.
- Prepare process-level test configuration.
- Select test ports `1522` and `18000`.
- Disable external integrations in the test configuration.
- Verify localhost-only binding.
- Prepare reset and rollback procedures.

## 18. Phase 2.5B Readiness Decision

```text
PHASE 2.5A STATUS: BLOCKED
```

The observed environment does not satisfy the safety criteria for Phase 2.5B.

## 19. Exact Next Steps

1. Confirm the actual JioPC Ultra hostname and hardware.
2. Do not use the current `PRASHANT`/production-like machine.
3. On the confirmed JioPC, perform a new read-only preflight.
4. Obtain explicit owner approval for required software installation.
5. Provision the isolated Oracle test environment only after that preflight passes.

## Safety Confirmation

- Existing production-like environment untouched: **YES**.
- Production database untouched: **YES**.
- Production configuration untouched: **YES**.
- Production credentials untouched: **YES**.
- Cloudflare untouched: **YES**.
- Supervisor untouched: **YES**.
- Scheduled tasks untouched: **YES**.
- GPS untouched: **YES**.
- Android/iOS untouched: **YES**.
- Payment integrations untouched: **YES**.
- WhatsApp/SMS untouched: **YES**.
- Windows restarted: **NO**.
- Destructive commands executed: **NO**.
- Git commit: **NO**.
- Git push: **NO**.
- Production data copied: **NO**.
- Secrets exposed: **NO**.
