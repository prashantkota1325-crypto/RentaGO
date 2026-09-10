# RentaGO IP Audit Baseline

Date: 2026-09-10

## Repository

- Project: RentaGO Prototype Web.
- Git executable: not available in the audit environment.
- Current branch/commit/remotes: UNKNOWN; must be verified on a machine with Git installed.
- `.gitignore`: present and excludes `.env`, keys, logs, cookies, and local diagnostic scripts.
- Authoritative repository owner: UNKNOWN; RentaGO should control the private source repository.

## Architecture

- FastAPI/Uvicorn + Jinja2/Bootstrap/vanilla JavaScript.
- Oracle XE 21c `XEPDB1` with `python-oracledb` and SQL*Plus fallback.
- Signed cookie sessions, database sessions, MFA/OTP, role/module RBAC, booking scope.
- In-process tracking, SLA, notification, and compliance workers.
- Oracle notification outbox.
- Local file uploads.
- Cloudflare Tunnel public HTTPS endpoint.
- Additive migrations in `scripts/migrate.py` and canonical schema in `db/schema/schema.sql`.

## Existing Protection

- HTTPS and named Cloudflare Tunnel.
- Password hashing for new writes; legacy plaintext compatibility remains.
- Secure sessions and session invalidation.
- Role/object booking scope helpers.
- CSRF middleware and security headers.
- Database-backed login/mobile-PIN rate limiting.
- Encrypted database backups and restore drill.
- Worker/readiness/external-service health endpoints.
- Regression tests and smoke-test script.

## Findings

- CRITICAL: Git/repository ownership and history could not be verified because Git is unavailable.
- HIGH: `.env` exists locally and contains configured secret categories; it is ignored but must never be committed or shared.
- HIGH: `scripts/seed_admin.py` contains a development default password path; production use must always provide an explicit password.
- HIGH: Ignored diagnostic scripts query password-vault data and contain test credentials; rotate any values if these files were ever shared or committed.
- HIGH: SMTP/WhatsApp/payment provider production delivery and webhook verification are not fully verified.
- HIGH: Full cross-tenant/object authorization and concurrency test matrices are incomplete.
- MEDIUM: Current deployment is one Windows host and local Oracle XE; 24/7 failover is not yet available.
- MEDIUM: Third-party license metadata needs machine-generated verification.

## Proposed Protection Files

- `docs/IP_OWNERSHIP.md`
- `docs/THIRD_PARTY_LICENSES.md`
- `docs/SBOM.md`
- `docs/RENTA_GO_SOURCE_OF_TRUTH.md`
- `docs/RENTA_GO_PROPRIETARY_LOGIC_INVENTORY.md`
- `docs/RENTA_GO_BACKUP_AND_RECOVERY.md`
- `docs/RENTA_GO_DEVELOPER_ACCESS_POLICY.md`
- `docs/RENTA_GO_OPEN_CODE_INDEPENDENCE_CHECKLIST.md`
- `docs/AI_ASSISTED_DEVELOPMENT.md`
- `docs/RENTA_GO_TECHNOLOGY_DUE_DILIGENCE.md`
- `docs/RENTA_GO_IP_PROTECTION_REPORT.md`

## Application-Code Changes

No application-code changes are required for the documentation-only IP audit. Any secret rotation, repository transfer, or deletion of diagnostic files requires explicit human authorization.
