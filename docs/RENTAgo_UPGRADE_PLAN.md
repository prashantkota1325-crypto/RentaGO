# RentaGO Upgrade Plan

## Execution Principles

Phase 1 is complete with this audit. Implementation must proceed by dependency and priority, not by blindly executing the numbered master prompt. Preserve current routes and data while introducing safe, tested improvements. No destructive schema change should occur without data-impact analysis and a rollback plan.

## Dependency Graph

```text
Secrets and deployment safety
        |
Database schema + migrations + constraints + identifiers
        |
Authentication
        |
RBAC + object/action authorization + organization scope
        |
Customers/companies + CRM
        |
Pricing/ratecards
        |
Booking transaction and status history
        |
Vendor/fleet/driver availability
        |
Allocation and dispatch
        |
Trip lifecycle
        |
Billing and payments
        |
Vendor bills/payouts + finance/profitability
        |
Notifications, dashboards, reports, documents
        |
Realtime/GPS scale-out and advanced analytics
```

## Recommended Work Packages

1. P0 security containment: rotate exposed secrets, remove password/cookie/PII artifacts, stop sensitive logging, disable public tunnel exposure, and set production secret requirements.
2. P0 schema baseline: reconcile application references with Oracle DDL, add safe versioned migrations, constraints, foreign keys, indexes, session/GPS objects, and sequence-based identifiers.
3. P0 authorization: enforce object-level access on bookings, trips, invoices, payments, dashboards, GPS trails, and generic masters; add CSRF, secure cookies, rate limits, and secure headers.
4. P0 workflow stabilization: resolve duplicate SLA route, centralize booking/trip/payment state transitions, validate all financial inputs, and make critical writes transactional/idempotent.
5. P1 identity organization: harden password migration to a modern password hash, complete configurable roles/departments/permissions, and test same-user/session behavior.
6. P1 CRM and customer model: consolidate customer/corporate/contact ownership, lead stages, activities, follow-ups, conversion, and record history.
7. P1 booking and pricing: normalize configurable states, booking history, requirements, customer billing, rate dimensions, taxes, discounts, and importer mappings.
8. P1 operations: implement availability-aware fleet/vendor/driver allocation, conflict prevention, dispatch queues, exception handling, and allocation history.
9. P1 trip operations: separate trip services from booking routes, enforce driver/guest/operator identity, support actuals, expenses, events, feedback, and completion controls.
10. P1 billing, payments, vendor payouts, finance: add invoice controls, payment reconciliation/refunds, vendor bills/payout approvals, cost classification, and profitability views.
11. P1 realtime/GPS foundation: reconcile location schema, introduce authenticated scoped realtime transport and durable worker infrastructure, then add tracking retention and privacy controls.
12. P2 contracts and notifications: versions, approvals, renewals, expiry alerts, provider-backed email/SMS/WhatsApp readiness, templates, retries, and delivery status.
13. P2 dashboards/reports/documents: role-specific KPIs, scoped reports and exports, secure document storage/access, retention, and audit trails.
14. P3 quality and optimization: split oversized modules, add observability, caching/pagination, CI, browser tests, accessibility, asset pinning, PDF generation, and automation.
15. P4 optional innovation: advanced analytics, predictive demand, optimization, and marketplace capabilities only after P0-P3 stability.

## Priority Backlog

### P0 - Production Blocking

1. Remove and rotate exposed credentials, session secrets, cookies, password material, and PII artifacts.
2. Remove plaintext password storage/comparison and sensitive debug logging.
3. Reconcile missing `user_sessions`, GPS tables, and tracking columns through safe migrations.
4. Fix authorization gaps on invoice expenses, payments, trip actions, dashboards, GPS trails, and masters.
5. Add CSRF protection, secure cookie settings, security headers, rate limiting, and production error handling.
6. Disable development reload, direct public exposure, and runtime dependency installation in deployment.
7. Resolve duplicate `/dashboards/sla` routing and verify all route imports.
8. Add transactional validation for booking, trip, invoice, payment, and cancellation writes.

### P1 - Core Business Functionality

9. Complete configurable RBAC, organization scope, departments, and permissions.
10. Complete CRM, customer, corporate-account, and lead lifecycle management.
11. Complete booking engine, status history, modification/cancellation/rescheduling, and conflict prevention.
12. Complete pricing and ratecard dimensions, taxes, discounts, and importer consistency.
13. Complete fleet availability, maintenance, vehicle documents, and utilization.
14. Complete vendor contracts, rates, availability, performance, bills, and payouts.
15. Complete driver profiles, documents, availability, assignment, and performance.
16. Complete allocation and dispatch with conflict-free manual/automatic allocation.
17. Complete trip lifecycle, events, actuals, expenses, feedback, and actor authorization.
18. Implement authenticated scalable realtime infrastructure.
19. Implement privacy-controlled GPS tracking, location history, retention, and scoped maps.
20. Complete billing, invoice approvals, credit/debit notes, and server-generated PDFs.
21. Complete customer payments, reconciliation, refunds, vendor payouts, and finance/profitability.

### P2 - Important Functionality

22. Contract versions, approvals, renewals, and expiry alerts.
23. Notification templates, durable delivery workers, retries, and provider integrations.
24. Role-based operational, sales, finance, fleet, vendor, and executive dashboards.
25. Scoped reports with filters, pagination, CSV, Excel/PDF readiness, and scheduled reporting.
26. Secure document management with metadata, access control, retention, and audit.

### P3 - Enhancements

27. Advanced analytics and management KPIs.
28. UI consistency, accessibility, loading/error/empty states, and responsive refinements.
29. Automation for follow-ups, reminders, allocations, alerts, and reconciliation.
30. CI/CD, observability, backups, performance tuning, and operational tooling.

### P4 - Future / Optional

31. Predictive demand and pricing.
32. Advanced allocation optimization.
33. Marketplace and external partner capabilities.

## Required Verification Per Work Package

Run unit, integration, authorization, database, and workflow tests as applicable. Start the application, exercise protected and public routes, inspect logs, validate database changes, check browser behavior, check for duplicate functionality, update module status, and record remaining risks.
