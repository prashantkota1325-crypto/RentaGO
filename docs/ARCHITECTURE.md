# RentaGO Current Architecture

## System Overview

```text
Browser / mobile browser
        |
        | HTTP HTML forms, vanilla JS, browser geolocation
        v
FastAPI + Uvicorn (`app/main.py`)
        |
        +-- Jinja2 templates + Bootstrap + static JavaScript
        +-- route modules under `app/routes/`
        +-- auth/RBAC/scope helpers
        +-- pricing, GPS, SLA, notification, tracking helpers
        v
Oracle XE 21c (`XEPDB1`)
        |
        +-- native python-oracledb
        +-- SQL*Plus subprocess fallback
```

## Repository Structure

- `app/main.py`: FastAPI construction, router registration, startup task, root endpoints.
- `app/config.py`: environment-backed settings and Oracle DSN construction.
- `app/db.py`: database connections and SQL*Plus fallback implementation.
- `app/auth.py`: signed cookies, session validation, RBAC, role cache.
- `app/scope.py`: account/vendor/driver/company visibility rules.
- `app/security.py`: VBA-compatible password functions.
- `app/audit.py`: login and audit writes.
- `app/gps.py`, `app/tracking.py`: coordinate processing and tracking sweep.
- `app/location_service.py`: provider-neutral maps facade with Google, Mappls configuration boundary, and OpenStreetMap development fallback.
- `app/routes/maps.py`: standardized `/maps/search`, `/maps/autocomplete`, `/maps/geocode`, `/maps/reverse-geocode`, `/maps/routes`, `/maps/eta`, `/maps/distance`, `/maps/route-matrix`, `/maps/geofence`, `/maps/snap-to-road`, and `/maps/live-location` endpoints.
- `app/rates.py`: rate lookup.
- `app/sla.py`: allocation SLA logic.
- `app/notify.py`: notification outbox/link generation.
- `app/routes/`: HTTP route handlers.
- `app/templates/`: Jinja2 views.
- `app/static/`: CSS, JavaScript, PWA assets.
- `db/schema/schema.sql`: Oracle DDL baseline.
- `scripts/`: setup, migration, seeding, and role repair utilities.
- `import/`: workbook importer.
- `tests/`: running-server smoke test.

## Request and Data Flow

Route handlers authenticate through `current_user`, check the roles matrix, optionally apply scope filters, query Oracle, perform business calculations, write audit/notification records, and render a template or redirect. There is no separate API/service/repository layer. Most booking, allocation, trip, GPS, cancellation, and notification behavior is in the monolithic bookings route module.

## Application Components

| Component | Current state | Assessment |
|---|---|---|
| Web application | FastAPI with ten routers | B: functional prototype |
| UI | Jinja2, Bootstrap, vanilla JS | B/C: broad coverage, limited automated UI validation |
| Persistence | Oracle plus custom fallback driver | C: operational but complex and weakly constrained |
| Business services | Helpers plus route-level logic | D: highly coupled |
| Authentication | Signed timed cookie and session rows | D: security and schema gaps |
| RBAC | Roles matrix and scope helpers | C/D: implemented, needs object-level enforcement |
| Background work | In-process asyncio loops/page-triggered SLA | D: not horizontally scalable |
| Realtime | Browser polling/public GPS posts | D: no production realtime infrastructure |
| Deployment | PowerShell and ad hoc tunnel | F/D: development-oriented |

## Integration Architecture

The workbook importer maps Excel data into Oracle. Nominatim is used for geocoding and Google Maps links are generated for routes. Email and WhatsApp are represented as notification links/outbox records; no durable provider worker is implemented. No payment gateway, message broker, external scheduler, or observability platform is configured.

## Architectural Risks

- Schema and application code are out of sync for sessions and GPS.
- Direct database access from route handlers makes transactions and authorization inconsistent.
- SQL*Plus fallback executes generated SQL scripts and adds process overhead.
- In-process background tasks are duplicated or lost across reloads/workers.
- Relative static/template paths depend on the current working directory.
- No production reverse proxy, TLS, health checks, monitoring, backup, or recovery configuration.

## Target Direction After Phase 1

Do not rewrite the application immediately. First stabilize security, schema, migrations, and authorization. Then extract tested services for booking state transitions, pricing, allocation, trips, billing, payments, and notifications while preserving existing routes and templates during controlled migration.
