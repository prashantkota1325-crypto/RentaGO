# RentaGO Prototype Web

Web re-implementation of the RentaGO Excel prototype (`RentaGO_Prototype_new.xlsm`)
with full feature parity, backed by Oracle and built with FastAPI + Jinja2 + Bootstrap.

## Stack
- **Python 3.12** (FastAPI, uvicorn, Jinja2, python-oracledb, openpyxl, itsdangerous, python-dotenv)
- **Oracle XE 21c** (free edition, XEPDB1 pluggable DB)

## Prerequisite: Oracle XE 21c (manual install)
Oracle XE is NOT available via winget/composer — it must be installed with the GUI installer:

1. Download Oracle Database XE 21c for Windows:
   https://www.oracle.com/database/technologies/xe-downloads.html
   (requires a free Oracle account + license acceptance)
2. Run `setup.exe`, accept defaults. Install to default location.
3. During install, set the **SYSTEM password** (remember it).
4. The DB listens on `localhost:1521` with pluggable database service **XEPDB1**.

> If the listener reports `ORA-12514` after a reboot, the instance's
> `local_listener` may point at a missing TNS alias. Fix once as SYSDBA:
> `ALTER SYSTEM SET local_listener='(ADDRESS=(PROTOCOL=TCP)(HOST=<host>)(PORT=1521))' SCOPE=BOTH; ALTER SYSTEM REGISTER;`

## Setup
```powershell
# 1. Install Python deps
pip install -r requirements.txt

# 2. Configure (copy .env.example -> .env, fill SYSTEM password etc.)
Copy-Item .env.example .env

# 3. Bootstrap schema + app user (connects as SYSTEM)
python scripts/setup_db.py

# 4. Apply incremental column migrations (idempotent)
python scripts/migrate.py

# 5. Import existing workbook data
python import/import_xlsm.py "C:\Users\Prashant Kota\RentaGO_Prototype_new.xlsm" --apply

# 6. Fix the roles matrix (blank = no access, not view)
python scripts/fix_roles.py

# 7. Seed a Super Admin login (if the workbook users' passwords are unknown)
python scripts/seed_admin.py --user-id admin --password "YourPass"

# 8. Run the app
python -m uvicorn app.main:app --reload
# -> http://127.0.0.1:8000
```

Or run `run.ps1`.

## Project layout
```
app/
  main.py            # FastAPI entrypoint
  config.py          # settings (env-driven, loads .env)
  db.py              # Oracle connection helpers (native + sqlplus fallback)
  security.py        # SHA-256 password scheme (matches VBA)
  auth.py            # session cookie + RBAC matrix + nav levels
  scope.py           # per-role data scoping (guest/vendor/driver/corp-admin)
  audit.py           # audit_log + login_log writes
  sla.py             # 5/45/60-min SLA sweep + auto-reassign
  rates.py           # ratecard pricing lookup
  gps.py             # coordinate extraction + haversine sync check
  templating.py      # shared Jinja2 templates + globals
  routes/            # auth, bookings, trips, invoices, payments, dashboards
  templates/         # Jinja2 pages
  static/            # css/js
db/schema/schema.sql # Oracle DDL for all tables
import/import_xlsm.py# xlsm -> Oracle importer
scripts/             # setup_db, migrate, fix_roles, seed_admin
tests/               # smoke_test.py (against a running server)
docs/                # (placeholder)
```

## Feature map (web vs Excel SOP)
- **Auth** — login/logout, salted SHA-256 (workbook users authenticate unchanged),
  self-registration + Super Admin approval queue, change password, login/logout log.
- **Booking wizard** — Step 1 request (guest autocomplete, company auto-create,
  employee/individual sync), Step 2 vendor allocation (30-min SLA red flag, lead-time
  gate, vendor deadline), Step 3 driver & vehicle allocation (masters autocomplete),
  trips row + Google Maps route, ratecard-priced provisional invoice on completion.
- **Trips** — dual-confirmation start/end (guest + driver), actuals (kms/hrs),
  live-location links with Haversine SYNCED/RED FLAG (500 m).
- **Cancellation** — 6-tier policy with auto-detected reason, charges
  (Rs.0/500/1000), cancellation invoice.
- **Invoices** — provisional -> vendor expenses -> final, A4 print/PDF view with
  GPS sync report.
- **Payments** — receipts/refunds/vendor payments linked to invoices (PY-0001 ids).
- **Dashboards** — CEO KPIs, Ops (SLA alerts + pending allocations + active trips),
  Sales (lead funnel), Finance (receivables/overdue), Vendor, Customer 360,
  Investor MIS, Compliance (audit + login logs), cross-trip Tracking.
- **SLA engine** — on-request sweep (throttled 5 min) mirroring the VBA 5-minute
  timer: vendor-unallocated info alert, 45-min driver warning, 60-min auto-reassign.
- **RBAC** — roles matrix (F/V/blank) drives nav + route guards; account roles
  (guest/vendor/driver/corporate admin) see only their own records via scope.py.

## Notes
- Passwords imported from the workbook authenticate unchanged (same salt:sha256 scheme).
- SMTP email for the Excel prototype still awaits tenant-level SMTP AUTH enablement
  (one-time M365 admin action); not a code issue.
