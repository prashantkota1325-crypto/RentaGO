# RentaGO AI Context

## Audit Scope

This document records the Phase 1 repository baseline for future engineering work. The Phase 1 audit was read-only; the subsequent P0 stabilization pass made only additive/hardening changes and did not remove business functionality.

## Product

RentaGO is a web re-implementation of an Excel/VBA car-rental operating system. It covers bookings, vendor and driver allocation, trips, GPS links, invoices, payments, dashboards, reporting, master data, notifications, and role-based access.

## Technology

- Python 3.12
- FastAPI 0.115.6 and Uvicorn 0.34.0
- Jinja2 server-rendered templates
- Bootstrap and vanilla JavaScript
- Oracle XE 21c, service XEPDB1
- `python-oracledb` native driver with SQL*Plus fallback
- `openpyxl` workbook importer
- `itsdangerous` signed session cookies

## Entrypoints

- ASGI application: `app/main.py`, object `app.main:app`
- Development command: `python -m uvicorn app.main:app --reload`
- PowerShell launchers: `run.ps1`, `start_global.ps1`
- Database setup: `scripts/setup_db.py`, `scripts/bootstrap.sql`
- Incremental migration script: `scripts/migrate.py`
- Workbook importer: `import/import_xlsm.py`
- Smoke test: `tests/smoke_test.py`

## Request Architecture

`app/main.py` creates the FastAPI application, mounts static files, registers ten routers, starts a tracking sweep, and exposes `/`, `/sw.js`, and `/home`. Routes use Jinja2 templates and direct database calls through `app/db.py`. Business logic is concentrated in route modules, especially `app/routes/bookings.py`.

## Route Groups

`/auth`, `/bookings`, `/trips`, `/track`, `/invoices`, `/payments`, `/dashboards`, `/masters`, `/reports`, and `/notifications`.

Portal entry points include `/auth/login` for internal RentaGO users, `/auth/corporate-login` for corporate roles, `/auth/vendor-login` for vendor roles, `/auth/guest-login` for guest users, and `/auth/driver-login` for driver users. All use the same session, database, booking workflow, and business routes. Guest/driver trip actions are role- and assignment-checked at the backend; RentaGO internal users retain override capability.

## Authentication and Authorization

Login reads `users`, verifies VBA-compatible salted SHA-256 credentials, creates a signed timed `rentago_session` cookie, and records a server-side `user_sessions` row for same-user single-session invalidation. RBAC is driven by `roles` with `F`, `V`, or blank access levels. The Roles Matrix now exposes the complete existing application/master catalogue; missing role rows remain no-access until explicitly assigned. `app/scope.py` applies account/vendor/driver/company visibility rules.

Important remaining risks: legacy plaintext password-vault compatibility for existing records, missing CSRF protection, incomplete actor/object authorization, and broader production hardening. New password writes no longer populate the legacy plaintext column; production settings now reject weak secrets/defaults.

## Database Baseline

The tracked schema declares the business tables plus `user_sessions` and `gps_log`; additive migration coverage now includes session/GPS objects and booking tracking/acknowledgement columns. Existing environments still require the migration to be run and verified.

The first tenant-foundation migration now adds `organizations`, user organization metadata, and `bookings.corporate_id`/`bookings.vendor_id`. Existing company/vendor names remain for backward compatibility while authorization is being migrated toward stable organization relationships.

## Realtime and GPS

There is no WebSocket or SSE layer. Booking address search uses Nominatim and stores validated selected pickup/drop latitude and longitude in the booking. Browser geolocation posts periodic pings through public tokenized tracking routes. A process-local tracking sweep runs every 60 seconds. SLA work runs from page requests or a manual endpoint. These mechanisms are prototype-level and are not suitable for multiple production workers without redesign.

## Engineering Rules

1. Search existing routes, tables, templates, and utilities before adding anything.
2. Prefer safe migrations and preserve workbook compatibility unless a data-impact review approves a change.
3. Resolve P0 security, schema, authorization, and deployment blockers before feature expansion.
4. Add tests for database operations, authorization, concurrency, and complete lifecycle transitions.
5. Do not expose `.env`, cookies, password material, diagnostic scripts, or debug logs.

## Known Sensitive Artifacts

Review and remove or protect `.env`, `cookies.txt`, `server_debug.log`, root diagnostic scripts, and imported SQL/data artifacts. Rotate any credentials or session secrets that may have been exposed.
