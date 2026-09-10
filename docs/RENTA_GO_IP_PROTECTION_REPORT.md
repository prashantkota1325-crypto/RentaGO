# RentaGO IP Protection Report

Date: 2026-09-10

## 1. Executive Summary

The RentaGO implementation is treated as proprietary technology and business logic owned/controlled by RentaGO Technologies Pvt. Ltd. The project now contains explicit IP ownership, dependency, source-of-truth, AI-assisted development, developer access, backup, and due-diligence documentation.

## 2. Current Architecture

FastAPI/Jinja2/vanilla JavaScript, Oracle XE, database-backed sessions/RBAC, SLA/TAT/Policy workers, notification outbox, GPS tracking, local files, encrypted backups, and a named Cloudflare Tunnel. See `docs/production-hardening-audit.md` and `docs/SAAS_ARCHITECTURE_AUDIT.md`.

## 3. Source Repository Ownership

**UNKNOWN / ACTION REQUIRED.** Git was not available in the audit environment, so remotes, branch, commit, visibility, and organization ownership could not be verified. RentaGO must verify control of the authoritative private repository.

## 4. OpenCode Configuration

No project `.opencode` directory or `AGENTS.md` was found. Project sharing state is **UNKNOWN** and must be verified in the applicable OpenCode/user configuration. Public sharing must remain disabled.

## 5. Source Code Protection

`.gitignore` protects `.env`, keys, logs, cookies, and diagnostic scripts. The source directory is currently under a local OneDrive path; a private RentaGO-controlled repository is required as the authoritative source.

## 6. Secret Protection

`.env` exists and contains configured secret categories. It is ignored by Git and must never be shared or committed. Diagnostic scripts contain password-related queries and test credentials; if they were ever shared or committed, rotation is required.

**Finding: HIGH — perform repository-history and secret-scanning review with Git available.**

## 7. Dependencies and Licenses

`requirements.txt` and `docs/THIRD_PARTY_LICENSES.md` identify direct dependencies. Exact transitive license/SBOM verification remains **REVIEW REQUIRED**.

## 8. Proprietary Business Logic

Booking, allocation, vendor, driver, vehicle, trip, GPS, billing, payment, refund, SLA/TAT/Policy, notification, report, and tenant logic are documented as RentaGO-specific proprietary implementation in `docs/RENTA_GO_PROPRIETARY_LOGIC_INVENTORY.md`.

## 9. Database/IP Protection

Oracle schema and additive migrations are versioned. Backups are encrypted. Restore testing has passed for the database into temporary schemas. Uploaded-file backup and complete staging restore remain pending.

## 10. Developer Access

Developer access policy is documented in `docs/RENTA_GO_DEVELOPER_ACCESS_POLICY.md`. Human/legal review is required for NDA and IP-assignment agreements.

## 11. Infrastructure Ownership

Domain and Cloudflare Tunnel are configured, but account ownership and recovery contacts must be verified manually under RentaGO control.

## 12. AI-Assisted Development

Documented in `docs/AI_ASSISTED_DEVELOPMENT.md`. AI tools are development tools, not owners.

## 13. Backup and Recovery

Database backup, encrypted archive, restore script, uploaded-file backup script, and PC replacement runbook exist. RPO/RTO are targets, not fully measured production guarantees.

## 14. Testing

Current automated regression suite: **12 tests passed** at audit time. Full E2E, concurrency, tenant isolation, provider, and failure-injection suites remain pending.

## 15. Findings by Severity

### CRITICAL

- Repository ownership/history not verified because Git is unavailable.
- Production secrets must be rotated if any ignored diagnostic file or repository history was shared.

### HIGH

- Full tenant/object authorization matrix incomplete.
- Provider delivery/webhook verification incomplete.
- Single-host production availability remains a risk.
- Complete uploaded-file restore drill pending.

### MEDIUM

- Transitive license/SBOM verification pending.
- Cloud account ownership and recovery contacts require confirmation.
- Full E2E/concurrency/failure-injection testing pending.

## 16. Manual Actions Required

1. Verify the private source repository is owned by RentaGO Technologies Pvt. Ltd.
2. Run secret scanning and Git-history review on a machine with Git installed.
3. Rotate any secret exposed through shared history or diagnostic files.
4. Confirm Cloudflare, GoDaddy, SMTP, maps, payment, SMS, and WhatsApp accounts are RentaGO-controlled.
5. Obtain a full legal backup/IP review.

## 17. Legal Professional Review Required

- IP ownership and contractor/developer assignment.
- Open-source license obligations.
- Privacy policy and data-processing terms.
- Customer/vendor contracts and confidentiality.
- GST, invoicing, refund, and accounting treatment.
- Transport, driver, vehicle, and document compliance.

## 18. Final Status

```text
PASS WITH CONDITIONS
```

The protection documentation is in place, but repository ownership, secret-history review, legal review, provider verification, full tenant isolation testing, and complete disaster-recovery validation remain open. No claim of legal protection or full production readiness is made by this report.
