# RentaGO Phase 1 Gap Analysis

## Assessment Summary

RentaGO is a feature-rich prototype with workbook parity, not a production-ready enterprise platform. The largest risks are exposed credentials and password material, schema drift, incomplete authorization, absent CSRF and secure deployment controls, weak financial integrity, and non-scalable background/realtime processing.

## Module Inventory

| Module | Status | Existing implementation | Main gap | Priority |
|---|---|---|---|---|
| Core application | B | `app/main.py` | No production middleware/health/observability | P0 |
| Configuration | D | `app/config.py`, `.env` | Weak defaults and secret exposure risk | P0 |
| Database access | C | `app/db.py` | SQL*Plus fallback, missing schema validation | P0 |
| Authentication | D | `app/routes/auth.py`, `app/security.py` | Plaintext compatibility, CSRF, secure-cookie, diagnostics | P0 |
| RBAC/scoping | C/D | `app/auth.py`, `app/scope.py` | Incomplete object/action authorization | P0/P1 |
| CRM/leads | C | `leads`, generic masters CRUD | No complete activities/follow-up/conversion workflow | P1 |
| Customers/corporates | C | companies, employees, individuals, contacts | Fragmented model and weak object scoping | P1 |
| Booking engine | C | `app/routes/bookings.py` | Monolith, free-form states, conflict/concurrency gaps | P0/P1 |
| Pricing/ratecards | D | `app/rates.py`, ratecards CRUD | Incomplete dimensions and importer mismatch | P1 |
| Operations/dispatch | C | dashboards and allocation routes | Limited exception/dispatch controls | P1 |
| Fleet | C | vehicles master and booking lookup | No availability, maintenance, document lifecycle | P1 |
| Vendors | C | vendors master and booking allocation | No contracts, performance, payout lifecycle | P1 |
| Drivers | C | drivers master and assignment | No robust availability/documents/performance | P1 |
| Allocation | C | vendor/driver allocation endpoints and SLA | No safe automatic conflict-free engine | P1 |
| Trips | C | booking lifecycle and trip views | Actions in booking module; actor checks incomplete | P0/P1 |
| GPS/tracking | C/D | browser GPS, tokens, trails | Missing schema, privacy, retention, token controls | P0/P1 |
| Realtime | D | polling and in-process sweeps | No WebSocket/SSE/broker/scaling | P1 |
| Billing/invoices | C | invoice routes and completion calculations | Weak approvals, validation, PDF generation | P0/P1 |
| Payments | C | payment record/list | No gateway, reconciliation, strong references/refunds | P0/P1 |
| Finance/profitability | D | finance dashboard and invoice/payment data | No accounting-grade ledger or cost model | P1 |
| Contracts | C | contracts master table | No versions, approvals, renewals, expiry workflow | P2 |
| Notifications | C | outbox and manual links | No delivery worker/provider integration | P2 |
| Dashboards | D | multiple dashboard templates/routes | Duplicate SLA route and inconsistent authorization | P2 |
| Reports | C | filtered page and CSV export | Limited scope, pagination, export formats | P2 |
| Documents | F | no dedicated secure document system | Missing storage, access, metadata, retention | P2 |
| Testing | D | one end-to-end smoke test | No unit/integration/security/concurrency/CI suite | P0/P1 |
| Deployment | D/F | PowerShell, reload, Cloudflare tunnel | No production topology, TLS, monitoring, backup | P0 |

## Database Gaps

Declared schema tables: `users`, `roles`, `login_log`, `audit_log`, `companies`, `employees`, `vendors`, `vehicles`, `drivers`, `individuals`, `bookings`, `trips`, `invoices`, `payments`, `leads`, `contacts`, `contracts`, `ratecards`, `settings`, `notifications`, and `otp_log`.

Application references absent or incomplete in the tracked schema: `user_sessions`, `gps_log`, `track_token`, `track_sent`, `ack_sent_time`, `driver_gps`, `guest_gps`, `driver_gps_ts`, and `guest_gps_ts`. Foreign keys, status constraints, payment references, allocation relationships, history tables, and concurrency-safe identifiers are also incomplete.

## API Gaps

The route surface is broad, but handlers are primarily HTML form endpoints. There is no versioned API contract, consistent error envelope, formal request schema layer, pagination standard, idempotency strategy, or complete authorization test matrix. Generic masters routes use dynamic SQL and need allow-listed identifiers.

## Frontend Gaps

The server-rendered UI has broad screen coverage, but no component test suite, frontend build pipeline, consistent loading/error/empty-state contract, CSRF form integration, or audited safe handling for public tracking data. Bootstrap is loaded from a CDN without SRI.

## Security Gaps

- Secrets, cookies, password material, and PII may exist in repository artifacts.
- Password vault plaintext fallback and debug password logging are unsafe.
- No CSRF protection on state-changing forms.
- Session cookies are not explicitly `Secure`.
- OTPs lack robust delivery, rate limits, atomic consumption, and expiry controls.
- Public tracking access lacks documented privacy, retention, and token lifecycle controls.
- Several mutation routes lack reliable object-level authorization.
- No rate limiting, security headers, CORS policy, or centralized secure error handling is evident.

## Realtime, GPS, and Integration Gaps

No WebSocket/SSE layer, durable worker, message queue, provider-backed notifications, payment gateway, server PDF generation, or observability integration exists. GPS data uses inconsistent field models and has no retention/geofence/deviation policy.

## Duplicate or Conflicting Functionality

1. Duplicate `/dashboards/sla` handlers in `app/routes/dashboards.py`.
2. Two GPS storage naming models: live-location fields and GPS fields.
3. Signed-cookie documentation conflicts with actual `user_sessions` dependency.
4. Python and SQL bootstrap paths overlap.
5. `MAX()+1` identifiers are used across multiple areas.
6. Importer ratecard fields do not align with schema ratecard fields.
