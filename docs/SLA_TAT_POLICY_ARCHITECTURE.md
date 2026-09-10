# RentaGO SLA, TAT, Policy and Rules Architecture

## Discovery Baseline

RentaGO is a Python FastAPI application using Jinja2/Bootstrap/vanilla JavaScript and Oracle XE 21c. The current application is a server-rendered monolith with route-level database access. It is not a greenfield system and this SLA program must extend the existing booking, trip, billing, notification, audit, and RBAC behavior.

## Existing Integration Points

| Capability | Existing implementation | Integration decision |
|---|---|---|
| Authentication | `app/auth.py`, signed session cookie, `user_sessions` | Reuse; SLA APIs require the current session and module permission. |
| RBAC | `roles` matrix, `module_level`, `nav_levels` | Add configurable SLA/Policy/Rules permissions through the existing matrix. |
| Booking workflow | `app/routes/bookings.py`, Step 1/2/3 status fields | Emit SLA events from existing transitions; do not create a second booking engine. |
| Trip workflow | Booking route dual Guest/Driver confirmations | Attach trip start/end and closure SLAs to existing actions. |
| Existing SLA | `app/sla.py` with hardcoded vendor/driver thresholds | Refactor to read published department/process definitions. Keep fallback defaults during migration. |
| Notifications | `app/notify.py`, `notifications` outbox, email/WhatsApp links | Reuse as the notification adapter; add configurable templates/channels and delivery status. |
| Audit | `app/audit.py`, `audit_log` | Reuse for configuration changes, pauses, escalations, approvals, and SLA state changes. |
| Background work | In-process tracking loop and page-triggered SLA sweep | Replace business-critical timing with a durable worker/queue; retain page-triggered sweep as a safe fallback. |
| Realtime | Browser GPS polling; no production WebSocket/broker | Add realtime later behind an event interface; do not couple SLA evaluation to page rendering. |
| Database | Oracle schema plus idempotent `scripts/migrate.py` | Add normalized SLA tables and indexes through additive migrations. |
| Reporting | `app/routes/reports.py`, CSV export | Add SLA reports and preserve tenant/role scope. |

## Current SLA Limitations

- `app/sla.py` currently hardcodes 5-minute vendor, 45-minute warning, and 60-minute reassignment thresholds.
- Current `sla_settings` provides a small department threshold table but does not model versions, events, working calendars, approvals, escalation chains, exceptions, or audit history.
- SLA evaluation is triggered by page requests/manual actions and is not a durable scheduled worker.
- Notifications are queued in the database; SMTP/WhatsApp delivery workers are not fully operational.
- Existing booking records do not yet carry a complete configurable department/process ownership model.

## Target Executable Architecture

```text
Existing RentaGO Transaction/Event
             |
             v
Event Publisher / Outbox
             |
             v
Workflow + Business Rule Resolver
             |
             v
SLA/TAT Instance Engine
             |
             +--> Working Hours / Holiday / Timezone Calculator
             +--> Pause / Resume / Exception Handler
             +--> Escalation Engine
             +--> Approval Engine
             +--> Notification Adapter
             +--> Audit Log
             +--> Dashboards / Reports / Control Tower
```

The first implementation should be a modular service layer inside the existing FastAPI application. A queue/worker boundary should be introduced before high-volume deployment. Redis, WebSockets, and a separate analytics store are scalability options, not prerequisites for the first safe migration.

## Proposed Core Tables

Add only after confirming existing data and migration impact:

- `sla_departments`
- `sla_processes`
- `sla_definitions`
- `sla_versions`
- `sla_instances`
- `sla_pauses`
- `sla_exceptions`
- `sla_escalation_rules`
- `sla_escalations`
- `sla_approval_workflows`
- `sla_approval_steps`
- `sla_notification_rules`
- `sla_notifications`
- `sla_working_hours`
- `sla_holiday_calendars`
- `sla_holidays`
- `business_rules`
- `business_rule_conditions`
- `business_rule_actions`
- `policy_definitions`
- `policy_versions`
- `sla_audit_log`

Existing `sla_settings` will be treated as a compatibility source during migration and eventually mapped to published definitions, not deleted blindly.

## Event Integration Map

| Existing event | Initial SLA use |
|---|---|
| Booking Step 1 submitted | acknowledgement, validation, vendor allocation |
| Vendor allocated | vehicle/driver allocation deadline |
| Driver/vehicle allocated | customer confirmation, dispatch readiness |
| Guest trip started | driver confirmation |
| Driver trip started | active trip monitoring |
| Guest trip ended | driver completion |
| Driver trip ended | trip closure, invoice generation, feedback window |
| Invoice created | invoice approval/submission |
| Payment recorded | receivable/payment closure |
| GPS deviation/SOS | P0/P1 incident and escalation |
| Document expiry | fleet/vendor/driver compliance alert |

## Rule Resolution Precedence

```text
Global default
 -> Department
 -> Process
 -> Service/location
 -> Corporate override
 -> Vendor override
 -> Contract override
 -> Transaction override
```

The resolver must return the selected rule ID/version and explain why it was selected. Historical transactions retain the applied version.

## Security and Data Integrity

- Only authorized internal RentaGO roles can create, approve, publish, or alter SLA/policy/rule definitions.
- Corporate and Vendor users can see only SLA instances and notifications related to their permitted records.
- Every state transition is idempotent by source event ID and SLA definition version.
- Pauses, exceptions, approvals, escalations, and overrides require actor, timestamp, reason, and audit record.
- No SLA engine failure may block the underlying booking/trip/payment transaction; failures go to an error/outbox stream for retry.

## Execution Sequence

1. Normalize current SLA settings and seed configurable departments/processes.
2. Add versioned SLA definitions and SLA instances.
3. Create an event/outbox adapter around existing booking/trip/payment transitions.
4. Implement working hours, holidays, timezone, pause, exception, and escalation services.
5. Replace hardcoded `app/sla.py` thresholds with the resolver while retaining safe defaults.
6. Add editable Admin UI, approvals, policy/rule simulator, dashboards, reports, and audit views.
7. Add durable worker/queue processing and realtime dashboard updates.
8. Run lifecycle, security, concurrency, and regression tests before production publication.

## Current Scope Boundary

This discovery document does not claim the 60-phase SLA program is complete. It records the existing architecture and the safe integration plan. Implementation must proceed package-by-package with migration and regression verification.
