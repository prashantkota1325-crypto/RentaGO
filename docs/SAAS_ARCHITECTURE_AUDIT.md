# RentaGO SaaS Architecture Audit

Audit date: 2026-09-09

## Current Status

The current application is a substantially implemented single-platform RentaGO operation with organization-aware records, role/module permissions, booking scope helpers, SLA/TAT/Policy services, Oracle persistence, and local production supervision.

It is **not yet a commercial multi-tenant SaaS platform**. The existing organization model is not equivalent to a secure tenant boundary. A tenant migration must therefore be incremental and must preserve RentaGO as Tenant 1.

## Current Architecture

- Frontend: Jinja2 server-rendered HTML, Bootstrap, vanilla JavaScript, service worker.
- Backend: FastAPI/Uvicorn monolith under `app/`.
- Database: Oracle XE 21c, service `XEPDB1`.
- Database access: `python-oracledb` preferred, SQL*Plus fallback in `app/db.py`.
- Authentication: signed `itsdangerous` cookie containing user/session identity, `user_sessions` validation, password hashing compatibility, Email MFA/OTP flows.
- Authorization: role/module matrix through `module_level()` plus route-specific role checks.
- Existing organization model: `organizations`, `users.organization_id`, `users.organization_type`, booking `corporate_id` and `vendor_id`.
- Current data scoping: `app/scope.py` and route-level `visible_booking_ids()` / `can_view()` logic.
- SLA/TAT/Policy: database-backed definitions, instances, event ledger, rules, policies, calendars, escalations, exceptions, approvals, reports, outbox notifications, and in-process workers.
- Workers: in-process asyncio loops for tracking, SLA evaluation, notification delivery, and compliance expiry.
- Queue: Oracle notification outbox. No Redis/Valkey queue or distributed lock is configured.
- WebSocket: no production WebSocket server/channel architecture found; GPS uses HTTP/mobile polling and ping endpoints.
- File storage: local filesystem/application-managed attachments; no tenant object-storage abstraction.
- External services: Cloudflare Tunnel, Google/Map provider abstraction, SMTP configuration, manual/provider-dependent WhatsApp links, no verified production payment gateway webhook layer identified.
- Deployment: Windows Task Scheduler for application, backups, monitoring; Windows Cloudflare service; one host and one local Oracle instance.
- Backups: Oracle Data Pump plus encrypted 7-Zip archives, remote/OneDrive destination, controlled temporary-schema restore test.

## Current Database Model

Core tables include:

- `users`, `roles`, `user_sessions`, `employees`, `organizations`.
- `companies`, `contacts`, `vendors`, `drivers`, `vehicles`, `individuals`.
- `bookings`, `trips`, `gps_log`, `invoices`, `payments`, `invoice_expense_documents`.
- `notifications`, `audit_log`, `login_log`.
- `sla_definitions`, `sla_instances`, `sla_event_log`, `sla_escalations`, `sla_escalation_rules`.
- `sla_pauses`, `sla_exceptions`, `sla_approval_workflows`, `sla_approval_steps`, `sla_approval_instances`.
- `sla_notification_rules`, `sla_working_hours`, `sla_holidays`, `sla_settings`.
- `policy_definitions`, `policy_versions`, `business_rules`.

The current model has organization/company/vendor identifiers, but most tenant-owned entities do not have a canonical `tenant_id`. Corporate and vendor identifiers are business relationships, not an authoritative tenant context.

## Current API/Route Surface

Major route groups include:

- `/auth/*`
- `/bookings/*`
- `/trips/*`
- `/invoices/*`
- `/payments/*`
- `/masters/*`
- `/reports/*`
- `/track/*`
- `/mobile/*`
- `/maps/*`
- `/policies/*`
- `/rules/*`
- `/sla/*`
- `/dashboards/*`

Authorization is implemented inside route functions and shared helpers. There is no central tenant middleware or repository layer that automatically applies tenant predicates to every query.

## Current Worker/Scheduler Model

- Tracking worker starts at FastAPI startup.
- SLA/TAT worker starts at FastAPI startup.
- Notification delivery worker starts at FastAPI startup.
- Compliance expiry worker starts at FastAPI startup.
- Windows Task Scheduler starts the application supervisor and backup/monitor tasks.
- Multiple application processes would currently create duplicate in-process worker loops.
- No distributed job claim, advisory lock, Redis lock, or queue consumer group is present.

## Current Security Model

Strengths:

- Signed session cookies with database-backed session invalidation.
- Role/module authorization helpers.
- Booking visibility helpers and participant checks.
- Password hash support for new writes.
- Secure production tunnel and HTTPS endpoint.
- Audit logging for many administrative and SLA actions.

Gaps:

- Complete CSRF protection for cookie-authenticated state-changing forms is not yet established.
- Tenant/object authorization is distributed across routes and is not universally enforced by a central tenant context.
- No complete automated IDOR/cross-tenant test matrix.
- Legacy plaintext password-vault compatibility remains a migration risk.
- No complete rate-limit/brute-force/security-header/CSP audit.
- Local files and exports require a tenant-aware storage/download design.

## SaaS Gaps

### Critical

- No canonical `tenant_id` and request-scoped tenant context.
- Existing RentaGO organization records cannot yet safely represent Tenant 1 versus future customers.
- No guarantee that every query, worker, export, file, notification, or report is tenant-scoped.
- In-process workers are unsafe for multi-instance deployment.
- No production cloud architecture or managed database/queue/object storage.

### High

- No platform Super Admin versus Tenant Admin boundary.
- No tenant provisioning/onboarding lifecycle.
- No subscription plans, entitlements, usage metering, quotas, trial, suspension, or billing separation.
- No centralized white-label/branding service.
- No custom-domain tenant resolution.
- No tenant-aware WebSocket architecture.
- No tenant-isolated file/object storage.

### Medium

- Existing reports/import/export need tenant filters and audited export scopes.
- Existing SLA/policy/rule configuration needs global default -> plan -> tenant -> branch precedence.
- Existing organization fields need migration mapping and data consistency checks.
- Platform analytics and tenant analytics are not separated.

## Recommended Migration Approach

### Phase A: Non-Destructive Foundation

1. Create a canonical `tenants` table and treat RentaGO Technologies as Tenant 1.
2. Create `tenant_memberships` rather than immediately replacing existing user/organization fields.
3. Add a request-scoped tenant context derived from authenticated membership, never trusted from a form/query parameter.
4. Add tenant-aware authorization helpers and fail closed for tenant-owned objects.
5. Add tenant context to audit, notifications, SLA events, workers, exports, and files.

### Phase B: Data Migration

1. Backup and validate restore before migration.
2. Map current `organizations`, companies, vendors, and RentaGO users to Tenant 1 or controlled future tenant records.
3. Add nullable `tenant_id` columns additively.
4. Backfill and validate every tenant-owned row.
5. Add tenant-aware indexes and scoped unique constraints.
6. Make tenant IDs non-null only after validation and rollback evidence.

### Phase C: Platform SaaS Layer

1. Platform Super Admin and Tenant Admin boundaries.
2. Plans, features, quotas, subscriptions, and usage metering.
3. Tenant branding and custom domains.
4. Tenant onboarding and imports.
5. Tenant-aware worker/job claims and notification delivery.
6. Object storage and tenant-safe signed downloads.

### Phase D: Cloud Readiness

1. Managed production database.
2. Redis/Valkey or durable queue.
3. Worker cluster with distributed locking/idempotency.
4. Reverse proxy/load balancer and separate staging/production environments.
5. Monitoring, alerting, restore drills, and measured RPO/RTO.

## Files Expected to Change

- `app/auth.py`, `app/scope.py`, `app/main.py`.
- New tenant context/membership/entitlement modules.
- `scripts/migrate.py`, `db/schema/schema.sql`.
- Protected route modules and query paths, incrementally.
- Worker modules and notification outbox processing.
- File upload/download/export routes.
- New Super Admin, Tenant Admin, onboarding, plan, and branding routes/templates.
- Tests for tenant isolation, authorization, concurrency, worker claims, files, reports, and exports.
- Production/deployment/runbook documentation.

## Files That Must Not Be Rebuilt Unnecessarily

- Existing booking, trip, billing, GPS, SLA, policy, rule, approval, and notification business logic.
- Existing Oracle data and migrations, except additive reviewed migrations.
- Existing public domain/tunnel setup.
- Existing RentaGO Tenant 1 operational workflows.
- Existing import/export formats unless tenant scope requires an additive field.

## First Implementation Package

The first code package after this audit should be **Tenant Foundation and Context**, limited to:

- `tenants` table.
- `tenant_memberships` table.
- RentaGO Tenant 1 seed/mapping.
- Authenticated tenant context helper.
- Explicit fail-closed behavior when a tenant-owned operation lacks context.
- Unit tests for Tenant A/Tenant B context separation.

It must not yet add tenant filters to every business table in one destructive change. That work should follow an entity mapping and staged migration.

## Current Decision

**SaaS conversion status: NOT READY FOR IMPLEMENTATION BEYOND THE FOUNDATION.**

The architecture audit is complete. The existing RentaGO platform should be preserved as the first tenant while a non-destructive tenant foundation is introduced around it.
