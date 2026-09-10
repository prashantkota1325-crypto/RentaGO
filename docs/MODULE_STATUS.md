# RentaGO Module Status

Status codes: A complete, B mostly complete, C partial/prototype, D implemented but needs major improvement, E broken/high risk, F missing.

| Area | Status | Evidence | Current conclusion |
|---|---|---|---|
| Application shell | B | `app/main.py` | Runs and registers routes; lacks production middleware. |
| Configuration | D | `app/config.py`, `.env.example` | Environment support exists; defaults are unsafe. |
| Oracle data layer | C | `app/db.py`, `db/schema/schema.sql` | Native/fallback access exists; schema drift and weak integrity. |
| Authentication | D | `app/routes/auth.py`, `app/security.py` | Login/recovery exist; sensitive diagnostics removed and new plaintext writes stopped, but legacy records, CSRF, MFA, rate limits, and actor checks remain. |
| RBAC | C | `app/auth.py`, `roles`, `app/routes/masters.py` | Matrix and route checks exist; complete application/master catalogue is exposed; organization metadata foundation added, object/action coverage remains incomplete. |
| CRM | C | leads/contacts tables and masters | Basic records exist; lifecycle is incomplete. |
| Customer management | C | companies/employees/individuals, corporate portal entry point | Basic data and portal routing exist; consolidated tenant model and corporate workflow remain. |
| Bookings | C | `app/routes/bookings.py` | Broad workflow exists; monolithic and concurrency-sensitive. |
| Pricing | D | `app/rates.py`, `ratecards` | Basic lookup only; importer/schema mismatch. Booking details now include planned route km/hour estimates from saved GPS coordinates. |
| Operations | C | allocation routes, SLA, dashboards | Functional prototype; no robust dispatch control center. |
| Fleet | C | vehicles master | Basic records; lifecycle and availability incomplete. |
| Vendors | C | vendors master/allocation, vendor portal entry point | Basic allocation and portal routing exist; contracts/KPI/payouts and vendor identity model remain. |
| Drivers | C | drivers master/allocation | Basic assignment; documents/availability/performance incomplete. |
| Allocation | C | vendor/driver allocation endpoints | Manual workflow exists; engine and conflict prevention incomplete. |
| Trips | C | trip routes and booking actions | Lifecycle exists; separation and actor checks needed. |
| GPS | C | `app/gps.py`, `app/routes/track.py`, `booking-form.js` | Address search now validates and persists selected pickup/drop latitude and longitude; privacy/scaling hardening remains. |
| Realtime | D | polling and background tasks | No production realtime transport; schema coverage was added for current GPS flow. |
| Invoices | C | `app/routes/invoices.py` | Provisional/final flow exists; controls and PDF incomplete. |
| Payments | C | `app/routes/payments.py` | Manual records exist; reconciliation/gateway absent. |
| Finance | D | finance dashboard, invoices/payments | Reporting view exists; no accounting-grade model. |
| Contracts | C | `contracts` table and masters CRUD | Basic records; versions/approvals/renewals absent. |
| Notifications | C | `app/notify.py`, notifications route, `app/notification_scope.py` | Corporate Step 1 queues RentaGO Operations email/WhatsApp notifications; Vendor Step 3 queues RentaGO Operations email/WhatsApp plus Vendor events. Portal filters remain enforced; automatic delivery worker remains absent. |
| Dashboards | D | `app/routes/dashboards.py` | Many views; duplicate SLA route and KPI gaps. |
| Reports | C | `app/routes/reports.py` | Corporate and Vendor portals have report access; page and CSV rows are filtered through booking visibility. Advanced report families remain incomplete. |
| Documents | F | no dedicated module | Missing secure document lifecycle. |
| Feedback | C | `app/routes/feedback.py`, `trips` feedback fields | Internal RentaGO review tool now supports filtering, ownership, follow-up action, rectification, and closure. |
| Testing | D | `tests/smoke_test.py` | One broad smoke test; no unit/negative/concurrency/CI coverage. |
| Deployment | D/F | `run.ps1`, `start_global.ps1` | Dev launcher only; not production hardened. |

## Module Exit Criteria

No module should be marked complete until its database operations, authorization, error handling, tests, logs, and user workflow are verified. The current statuses are repository assessments, not claims of production readiness.
