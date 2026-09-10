# RentaGO Production-Hardening Audit

Audit date: 2026-09-09

## Executive Status

RentaGO is functionally advanced and currently reachable at `https://app.rentago.co.in`, but it is **not yet production-ready for 24/7 multi-instance operation**. The current deployment is a single Windows PC running Oracle XE, FastAPI/Uvicorn, in-process workers, and a named Cloudflare Tunnel service.

No destructive architecture migration is recommended in the first hardening pass. The first priority is to make the current system secure, idempotent, observable, and recoverable before moving it to cloud infrastructure.

## Existing Architecture

- Frontend: server-rendered Jinja2 templates, Bootstrap, vanilla JavaScript, service worker.
- Backend: FastAPI/Uvicorn monolith under `app/`.
- Database: Oracle XE 21c, normally service `XEPDB1`, accessed through `python-oracledb` with SQL*Plus fallback.
- Authentication: signed `itsdangerous` cookie plus `user_sessions` database records and OTP/MFA flows.
- Authorization: role/module matrix and booking visibility helpers in `app/auth.py` and `app/scope.py`.
- SLA engine: database-backed definitions, instances, policies, rules, event ledger, escalation, approval, exception, calendar, and report routes.
- Workers: in-process asyncio loops for tracking, SLA evaluation, notification delivery, and compliance expiry.
- Queue: Oracle `notifications` outbox; no Redis/Valkey queue currently exists.
- Realtime: browser polling and GPS pings; no WebSocket broker or cluster.
- File storage: local filesystem for uploaded/attached files; no object storage yet.
- External services: Cloudflare Tunnel, Google/Map provider abstraction, SMTP outbox delivery; WhatsApp currently stores/manual-opens `wa.me` links unless a provider is configured.
- Payments: application payment records exist; no verified payment-gateway webhook integration was found in the current deployment.
- Backups: Oracle Data Pump plus AES-encrypted 7-Zip archives, scheduled on Windows, with a controlled restore test into temporary schemas.
- Deployment: Windows Task Scheduler for app startup/backups/monitoring and Cloudflare Windows service for the named tunnel.
- Tests: focused SLA unit tests in `tests/test_sla_core.py` and an end-to-end smoke script requiring a running server and test credentials.

## Current Strengths

- Oracle schema migrations are additive and idempotent.
- SLA and notification workers have retry/error isolation.
- SLA event source IDs and notification IDs provide useful idempotency foundations.
- Policies, rules, escalations, exceptions, approvals, audit, imports/exports, and operational reports are present.
- Encrypted backup creation and a controlled restore test have passed.
- Public HTTPS health endpoint is working through Cloudflare.

## Risks

### Critical

- Single-PC availability: if the host, Oracle XE, network, or Windows account fails, the public application is unavailable.
- In-process workers are not safe for multiple app processes: each process can run its own SLA, compliance, tracking, and notification loops.
- No complete CSRF protection was found for state-changing cookie-authenticated forms.
- Full tenant/object authorization coverage and automated IDOR testing are incomplete.
- Backup restore is tested locally but not yet a full staging restore of every business artifact and uploaded document.

### High

- Notification delivery has no distributed job claim/lock for multiple workers.
- SMTP production delivery, bounce handling, and provider delivery confirmation are not fully verified.
- WhatsApp provider authentication/templates/webhooks are not production-verified.
- Payment/refund gateway webhook signature verification has not been verified.
- Local file attachments are not yet protected by durable object storage and disaster-recovery replication.
- No Redis/Valkey, WebSocket cluster, reverse proxy/load balancer, or cloud database deployment exists.
- Rate limiting and brute-force protection require a complete production review.

### Medium

- Health checks currently verify application/database availability but do not expose separate readiness, worker, storage, or external-provider health.
- Structured correlation IDs are not consistently present across all business operations.
- Database indexes and foreign-key/unique-constraint coverage need workload-based review.
- Full concurrency tests for assignment, payment, refund, cancellation, and worker claims are incomplete.
- Legacy plaintext password-vault compatibility remains a migration risk; new password writes do not populate the legacy plaintext field.

## Recommended Fix Order

1. Add CSRF tokens and state-changing request tests, excluding signed webhook endpoints.
2. Add server-side tenant/object authorization tests for bookings, files, reports, notifications, and exports.
3. Add idempotency keys, row locking, and concurrency tests for assignments, payments, refunds, cancellation, and notification claims.
4. Add a database/distributed worker lock or queue claim model before any multi-process deployment.
5. Add `/ready`, worker health, queue depth, and external-service health checks.
6. Complete SMTP/WhatsApp/payment provider verification with secrets only in deployment configuration.
7. Perform a full staging restore drill including attachments and measured RPO/RTO.
8. Deploy Oracle/PostgreSQL-compatible production architecture, Redis/Valkey, object storage, monitoring, and reverse proxy in cloud infrastructure.

## Files Likely to Change in Hardening

- `app/main.py`: middleware, readiness, lifecycle ownership, correlation IDs.
- `app/auth.py`, `app/security.py`: CSRF/session/rate-limit hardening.
- `app/scope.py` and protected route modules: object-level authorization.
- `app/db.py`, `scripts/migrate.py`: transactions, indexes, constraints, claim/lock support.
- `app/sla_worker.py`, `app/notification_worker.py`, `app/tracking.py`, `app/compliance_worker.py`: distributed locking and worker health.
- `app/notify.py`, provider adapters, and webhook routes: delivery verification/idempotency.
- `tests/`: E2E, authorization, concurrency, failure-injection, and restore verification.
- `docs/`: runbooks, provider verification, monitoring, rollback, and readiness reports.

## Files/Behavior Not to Modify Unnecessarily

- Existing booking/trip/invoice/payment business rules.
- Existing SLA policy semantics and published version history.
- Existing Oracle data and migrations except additive, reviewed changes.
- Existing Cloudflare hostname and public URL.
- Existing portal workflows unless a security test proves a defect.

## Production Readiness Decision

**Status: NOT PRODUCTION READY FOR 24/7 MULTI-INSTANCE OPERATION.**

The application is suitable for continued controlled testing on the current host. No go-live approval should be issued until the Critical and High risks above have verified mitigations, especially CSRF, tenant/object authorization, concurrency/idempotency, distributed worker locking, and staging restore evidence.
