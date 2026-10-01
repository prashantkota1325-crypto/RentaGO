# RentaGO Production Infrastructure Readiness Report

Phase: `PHASE-PROD-1.0`

Scope: LAB/source audit and production preparation only.

Production touched: **NO**

## 1. Executive Summary

The current RentaGO implementation is a FastAPI/Jinja2 application backed by Oracle XE and running on a Windows 11 LAB workstation. It is validated for LAB workflows but is not production-ready as infrastructure.

The principal blockers are:

- No provisioned production server.
- No production database.
- No production DNS/HTTPS/reverse proxy deployment.
- No Redis or external queue infrastructure.
- Background workers run in-process with Uvicorn.
- WebSocket/realtime fanout is process-local and not horizontally scalable.
- Backups are Windows/Data Pump scripts, not a tested production backup system.
- No centralized monitoring, logging, or error tracking platform.
- Android release signing still uses the debug signing configuration.
- Production App Links certificate fingerprint and `assetlinks.json` are not configured.
- WhatsApp remains deferred/not configured.

## 2. Current LAB Environment

- OS: Microsoft Windows 11 Pro, 64-bit.
- Python: 3.12.10.
- LAB host observed IP: `192.168.1.8`.
- Application: Uvicorn/FastAPI on `0.0.0.0:8000`.
- Additional local LAB process observed on `127.0.0.1:8010`.
- Oracle listener: local TCP `1521`.
- Oracle: 21c Express Edition, service `XEPDB1`.
- LAB workstation: 12 logical processors, approximately 11.94 GB RAM, approximately 318 GB free on C:.
- Cloudflared is installed locally; quick tunnels are ephemeral and are not a production identity.
- Windows firewall profiles were observed disabled/not configured. This is not acceptable as a production control.
- `.env` exists locally and is ignored by Git. Its values were not exposed in this audit.

## 3. Application Runtime

- Framework: FastAPI.
- Templates/UI: Jinja2, Bootstrap, vanilla JavaScript.
- Runtime server: Uvicorn.
- Requirements are pinned in `requirements.txt`.
- Startup scripts use Uvicorn directly and, in some cases, `--reload`.
- The current runtime depends on the application working directory for relative templates/static paths.
- Production should use a supervised non-reload process behind a reverse proxy.

## 4. Server Requirements

### Minimum initial production recommendation

- 4 vCPU.
- 8 GB RAM.
- 100 GB SSD.
- Daily off-server backups.
- Private network access to Oracle and any internal services.

### Recommended initial production topology

- Application/reverse-proxy server: 4-8 vCPU, 16 GB RAM, 100+ GB SSD.
- Oracle database service: separate managed or dedicated Oracle host with tested backups.
- Optional worker service: separate process/host once workers are externalized.
- Redis: not required by the current source, but required if realtime/process coordination is expanded beyond one process.

The current architecture should not be placed behind multiple application workers without first externalizing in-process worker state and process-local realtime subscriptions.

## 5. Operating System

Recommended production OS: Ubuntu Server LTS, current organization-approved LTS release.

Required preparation:

- Non-root administrative user.
- SSH keys only; disable password SSH authentication.
- Disable direct root SSH login.
- UFW or equivalent default-deny inbound policy.
- Automatic security updates with maintenance policy.
- NTP/time synchronization.
- Timezone explicitly set to `Asia/Kolkata` where appropriate, with canonical UTC storage decisions documented.
- Host-level audit and intrusion monitoring.

Production server: **NOT YET PROVISIONED**.

## 6. Network and Firewall

### Public

- TCP 80: HTTP redirect to HTTPS.
- TCP 443: HTTPS reverse proxy.

### Private

- SSH: restricted source IPs only.
- Oracle: private network only.
- Redis, if introduced: private network only.
- Application/Uvicorn internal port: private loopback/network only.

Recommended documentation-only UFW policy:

```text
default deny incoming
default allow outgoing
allow 80/tcp
allow 443/tcp
allow from <admin-network> to any port 22 proto tcp
```

No firewall changes were executed.

## 7. DNS

Required production record:

```text
app.rentago.co.in A <production-public-ip>
```

AAAA should only be added if IPv6 is configured and tested. No separate API or webhook host is currently required by the source inventory.

DNS status: **NOT READY / NOT VERIFIED**.

No DNS changes were made.

## 8. HTTPS and SSL

Required:

- Certificate for `app.rentago.co.in`.
- Automated renewal and renewal monitoring.
- HTTP-to-HTTPS redirect.
- Secure session cookies.
- HSTS after HTTPS validation.
- TLS 1.2+ policy and modern cipher configuration.
- Existing security headers retained.

The LAB configuration currently has `SESSION_COOKIE_SECURE=false` because it uses HTTP. Production configuration must set it true. No production certificate was obtained or installed.

HTTPS: **NOT READY**.

## 9. Reverse Proxy

Nginx or an organization-approved equivalent is recommended:

```text
Internet
  -> Nginx/HTTPS
  -> Uvicorn application
  -> Oracle
  -> in-process/background worker boundary
```

Reverse proxy requirements:

- HTTP redirect to HTTPS.
- `/static` caching and compression.
- Upload size and request timeout limits.
- WebSocket upgrade routing for `/track/ws/...`.
- Forwarded headers configured safely.
- Security headers and access logs.

No reverse proxy is deployed in LAB or production.

## 10. Database

Actual LAB database findings:

- Oracle Database 21c XE.
- Service: `XEPDB1`.
- 62 user tables observed in the LAB schema.
- Core tables observed: `GPS_LOG`, `GPS_LATEST_POSITIONS`, `TRACKING_SESSIONS`, `BOOKINGS`, `USERS`, `NOTIFICATIONS`, and `UNIVERSAL_ACCESS_TOKENS`.
- Schema migration scripts exist, including repeatable migrations.
- Direct database access occurs in route handlers.
- Transaction boundaries are route-managed.
- Oracle connection fallback can invoke SQL*Plus, increasing operational complexity.

Production database: **NOT PROVISIONED**.

Production requirements:

- Dedicated/managed Oracle service.
- Tested schema migration process.
- Connection pool sizing.
- Index and constraint review.
- Private network isolation.
- Data Pump or managed backup strategy.
- Restore validation before go-live.

No production database was created or modified.

## 11. Redis

Redis usage: **NOT FOUND IN CURRENT SOURCE**.

The current source does not use Redis for sessions, queues, GPS ingestion, or realtime fanout. Redis is therefore not required for the current single-process LAB implementation.

Redis would become required for shared cache/session coordination, distributed workers, or multi-process realtime fanout. If introduced, it must be private, authenticated, persisted according to workload, monitored, and backed up where appropriate.

Redis required now: **NO**.

## 12. WebSocket and Realtime

WebSocket exists at the tracking route for display updates. The implementation uses `app/realtime.py`, which stores subscribers in an in-process `defaultdict` of asyncio queues.

Consequences:

- It works only inside one application process.
- It does not use Redis/pub-sub.
- It is not safe for multiple Uvicorn workers or multiple hosts.
- Realtime display is separate from authoritative GPS HTTP ingestion, GPS queue handling, and Oracle persistence.

WebSocket production status: **NOT READY**.

The production choice is either single-process operation with explicit capacity limits or a later separately approved Redis/pub-sub/realtime design. The GPS HTTP ingestion path must remain authoritative.

## 13. Background Workers

Startup currently launches in-process asyncio loops for:

- Tracking sweep.
- SLA sweep.
- Notification delivery.
- Compliance sweep.

Worker health is exposed by `/health/workers`. The workers have retry/status logic, but process-local startup means reloads, crashes, duplicate workers, and horizontal scaling require additional controls.

Production requirements:

- Separate supervised worker processes or an external scheduler/queue.
- Single-owner/lease or idempotency controls for periodic jobs.
- Restart policy.
- Worker health and lag alerts.
- Dead-letter/retry visibility.

Background workers: **NOT READY for multi-process production**.

WhatsApp remains deferred/not configured.

## 14. Storage

The source uses local filesystem storage for invoice expense attachments under `app/uploads/invoice_expenses` when present. Static assets are served from `app/static`.

Production should use:

- Durable private SSD for temporary/local files, plus
- S3-compatible/object storage or equivalent for uploaded documents and generated artifacts,
- Explicit access control, encryption, retention, malware/content validation, and backup.

No object storage integration is currently configured. Production file storage: **NOT READY**.

## 15. Backups

Existing scripts provide a starting point:

- Oracle Data Pump export.
- AES-256 7-Zip archive.
- Separate uploaded-file archive.
- Configurable backup directory.

Current limitations:

- Windows-specific tooling and paths.
- Requires `expdp.exe` and `7z.exe`.
- No verified off-server/cloud copy in this audit.
- No completed restore test against a clean environment.
- Secrets are used as archive passwords and require controlled recovery.

Production backup requirements:

- Daily database backups, with encrypted off-server copy.
- Uploaded files/documents included.
- Application source and deployment configuration backed up.
- Secrets recovery plan separated from application backup.
- Daily 30-day, weekly 12-week, and monthly 12-month retention unless policy differs.
- Quarterly restore test at minimum.

Backup: **NOT READY**.

## 16. Disaster Recovery

Documented target from current recovery notes:

- RPO: 24 hours until remote scheduled backups are enabled and verified.
- RTO: 2-4 hours after a tested restore procedure.

Recovery sequence:

1. Provision replacement server.
2. Install approved OS and security baseline.
3. Restore application source/configuration.
4. Restore secrets through the approved secret channel.
5. Restore Oracle database.
6. Restore uploaded files.
7. Apply migrations.
8. Start reverse proxy, application, workers, and monitoring.
9. Verify health, login, booking, GPS ingestion, notifications, and dashboards.

Disaster recovery: **NOT READY** because the restore has not been physically tested on a clean production-like environment.

## 17. Monitoring

Current source exposes:

- `/health` and `/health/db`.
- `/health/workers`.
- `/health/external-services`.
- A local PowerShell monitor that checks `/health`.

No external monitoring or observability platform was found.

Production monitoring must cover:

- CPU, RAM, disk, and OS health.
- HTTPS certificate expiry.
- Application latency and HTTP 5xx.
- Oracle connectivity, sessions, locks, and storage.
- GPS ingestion rate, stale data, queue depth, and rejected batches.
- Notification worker lag/failures.
- WebSocket connection failures.
- Backup and restore failures.
- Authentication failures and security events.

Monitoring: **NOT READY**.

## 18. Logging and Error Tracking

Application logs are process/stdout/stderr or local runtime files. No centralized log platform, rotation policy, or error tracking service was found.

Production requirements:

- Structured logs with correlation/request IDs.
- Rotation and retention.
- Centralized secure aggregation.
- Alerting on exceptions and 5xx spikes.
- Audit/security logs separated from diagnostic logs.
- Redaction of tokens, passwords, cookies, private keys, and database credentials.

Error tracking: **NOT READY**.

## 19. Secrets Checklist

| Secret/configuration | Purpose | Required for | Production storage | Rotation |
|---|---|---|---|---|
| `RENTAGO_DB_PASSWORD` | Oracle application login | Database | Secret manager | Scheduled/emergency |
| `RENTAGO_ADMIN_PASSWORD` | Schema/bootstrap administration | Migration/DBA only | Secret manager | Controlled |
| `RENTAGO_SECRET` | Signed session/MFA tokens | Application auth | Secret manager | Planned rotation |
| `RENTAGO_SMTP_USER` / password | SMTP submission | Email | Secret manager | Provider policy |
| `RENTAGO_GOOGLE_MAPS_API_KEY` | Maps/routes | Maps | Secret manager/provider restrictions | Provider policy |
| `RENTAGO_MAPPLS_API_KEY` | Optional maps provider | Maps | Secret manager | Provider policy |
| WhatsApp provider credentials | Deferred messaging | Not currently configured | Not applicable | Not applicable |
| Android release keystore | APK/AAB signing | Production Android | Offline encrypted vault | Key lifecycle |

No secret values were printed or changed.

## 20. Security Hardening

Before production:

- Ubuntu/OS hardening and automatic security updates.
- SSH key-only admin access and restricted source IPs.
- Firewall default deny.
- Private Oracle and Redis boundaries.
- HTTPS, secure cookies, HSTS, and reverse proxy.
- Production CORS policy explicitly reviewed.
- CSRF and rate limits verified under production hostnames.
- Tenant/RBAC/object-scope review.
- Secure token expiry, revocation, replay, and log redaction verified.
- Upload extension, size, content, storage, and download authorization review.
- Dependency vulnerability scan and pinned dependency review.
- Backup encryption and restore testing.

Security: **NOT READY**.

## 21. Android Production Release

Current Android release artifact is LAB-only:

- Debug signing configuration remains in `android/app/build.gradle.kts`.
- LAB build may allow cleartext traffic for `192.168.1.8`.
- Production API URL is not configured as the signed release default.
- Production keystore and publisher/MDM credentials are not configured.

Production requirements:

- Generate/use an organization-controlled release keystore.
- Store signing material in an encrypted restricted vault.
- Build signed AAB/APK with production HTTPS configuration.
- Verify package identity and versioning.
- Publish through Google Play or MDM.
- Keep LAB and production signing/configuration separate.

Android production signing: **NOT READY**.

## 22. Production App Links

Target:

```text
https://app.rentago.co.in/access/<secure-token>
```

The Android manifest contains the production host intent filter, but the verified App Link cannot be complete until the actual production signing certificate SHA-256 fingerprint is known and deployed in:

```text
https://app.rentago.co.in/.well-known/assetlinks.json
```

No fingerprint was invented and no production assetlinks file was deployed.

Production App Links: **NOT READY**.

## 23. External Services

| Service | LAB status | Production required | Credential/webhook | Ready |
|---|---|---|---|---|
| Oracle XE | Local LAB 21c | Dedicated/managed Oracle | DB credentials/backups | No |
| SMTP | Configured/submission tested | Required | SMTP credentials; bounce tracking needed | Partial |
| WhatsApp | Manual `wa.me`; not configured | Optional/required for promised automation | Provider credentials/template/webhook | No |
| Google Maps | Configured in LAB | Required if maps/routes retained | Restricted API key | Partial |
| Redis | Not used by current source | Not currently required | N/A unless architecture expands | Not required |
| WebSocket | Process-local LAB | Requires single-process limit or external fanout | Reverse proxy/scale design | No |
| Payment gateway | Not configured | Required if online payment is launched | Provider credentials/webhooks | No |
| Object storage | Not configured | Recommended for durable uploads | Bucket credentials/policy | No |
| Monitoring/error tracking | Not configured | Required operationally | Platform credentials | No |

## 24. Environment Configuration

The current LAB configuration is development-oriented:

- `ENVIRONMENT=development`.
- Local Oracle host/service.
- `SESSION_COOKIE_SECURE=false` for HTTP LAB use.
- LAB IP/HTTP and temporary Cloudflare tunnels are present in runtime workflows.
- Test accounts and LAB tokens exist in the LAB database.
- Production secrets and signing configuration are not present.

Production configuration checklist:

- Production hostname and HTTPS base URL.
- `ENVIRONMENT=production`.
- Strong production secret.
- Secure cookies enabled.
- Production Oracle DSN/credentials.
- Restricted Maps credentials.
- Approved SMTP/provider settings.
- Reverse proxy forwarded headers.
- Upload/storage paths.
- Worker supervision and monitoring.
- Release Android signing and App Links.

## 25. Health Checks

Existing endpoints:

- `/health`: application and Oracle basic check.
- `/health/db`: database check.
- `/health/workers`: in-process worker heartbeat check.
- `/health/external-services`: configuration/DNS probe without provider delivery confirmation.

Production health should additionally verify, without exposing secrets:

- Reverse proxy/TLS reachability.
- Oracle connection pool and schema readiness.
- Worker freshness/lag.
- Storage availability.
- Backup freshness.
- WebSocket upgrade path if retained.
- Notification provider configuration/last failure state.

## 26. Production Blockers

- No production server is provisioned.
- No production database is provisioned.
- DNS and HTTPS are not deployed/verified.
- No reverse proxy is deployed.
- No production backup/restore test.
- No centralized monitoring/logging/error tracking.
- Process-local workers/realtime are not production-scale.
- Release Android signing is not configured.
- Production App Links fingerprint/assetlinks are not configured.
- WhatsApp is deferred/not configured.

## 27. Recommended Deployment Sequence

1. Provision isolated Ubuntu Server LTS application and database infrastructure.
2. Establish private network and firewall policy.
3. Configure DNS and HTTPS/reverse proxy.
4. Provision Oracle and apply reviewed schema migrations.
5. Configure secret manager and production environment values.
6. Externalize/supervise workers and define process/realtime scaling limits.
7. Configure durable file storage and backup destinations.
8. Install monitoring, logging, alerting, and certificate monitoring.
9. Run dependency/security/UAT checks in a production-like staging environment.
10. Create production Android signing configuration and App Links asset file.
11. Run restore and smoke tests.
12. Perform a separately approved controlled production deployment.

## 28. Final Readiness Status

```text
PRODUCTION INFRASTRUCTURE AUDIT:
PARTIAL

PRODUCTION SERVER:
NOT PROVISIONED

PRODUCTION DATABASE:
NOT PROVISIONED

HTTPS:
NOT READY

DNS:
NOT READY

REVERSE PROXY:
NOT READY

REDIS:
NOT REQUIRED

WEBSOCKET:
NOT READY

BACKGROUND WORKERS:
NOT READY

BACKUP:
NOT READY

DISASTER RECOVERY:
NOT READY

MONITORING:
NOT READY

SECURITY:
NOT READY

ANDROID PRODUCTION SIGNING:
NOT READY

PRODUCTION APP LINKS:
NOT READY

WHATSAPP:
DEFERRED / NOT CONFIGURED

LAB REGRESSION:
84 PASSED / 0 FAILED / 9 SKIPPED

PRODUCTION TOUCHED:
NO

PRODUCTION DEPLOYED:
NO

CORE PASS MODULES MODIFIED:
NO

OVERALL PRODUCTION READY:
NO — AUDIT/PREPARATION PHASE ONLY
```
