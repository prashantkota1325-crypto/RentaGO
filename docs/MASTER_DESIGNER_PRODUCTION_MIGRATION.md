# Master Designer Production Migration Design

## Purpose

This document describes the reviewed, future Production migration artifact for
Master Designer metadata. It is source documentation only. The migration has
not been executed against Production.

## Artifact

- File: `scripts/migrate_master_designer_production.py`
- Application compatibility baseline: `11ed6f762c9ab09fdea4aa00906462cff9d3f2b3`
- Current repository commit also contains the Phase 1.3 artifact commit
  `af6c14242bd27b65bec0b9ace755a6c9edb8aafd`.
- Execution is review-only by default and requires both `--apply` and
  `RENTAGO_APPROVE_MASTER_DESIGNER_MIGRATION=YES`.

## Objects

The artifact creates, when absent:

- `MASTER_DEFINITIONS`
- `MASTER_FIELD_DEFINITIONS`
- `MASTER_FIELD_OPTIONS`
- `MASTER_FIELD_ALIASES`
- `MASTER_CUSTOM_VALUES`
- `MASTER_CONFIGURATION_VERSIONS`
- `MASTER_CONFIGURATION_AUDIT`

It verifies existing columns, data types, and named constraints before seeding.
Mismatches stop the migration; existing objects are never silently altered.

## Seed Rules

- Master definitions are keyed by stable `MASTER_KEY`.
- Fields are keyed by `(MASTER_ID, TECHNICAL_NAME)`.
- Aliases and options are keyed by their existing unique constraints.
- Generated IDs preserve relationships and are not copied from LAB.
- Version 1 is created only when no version exists for a Master.
- Rate Card import remains disabled.
- No business records are inserted or updated.

## Scope

Master definitions and configuration versions are platform-wide, matching the
current implementation. Custom values are tenant-scoped by
`MASTER_ID`, `TENANT_ID`, `RECORD_ID`, and `FIELD_ID`.

## Safety

- Additive only.
- No `DROP`, `TRUNCATE`, `DELETE`, `UPDATE`, or `MERGE` statements.
- No business-data import.
- No XLSM/XLSX/CSV data import.
- Existing-object mismatches stop safely.
- Rate Card import is not enabled.

## Future Execution Order

1. Human approval.
2. Verify approved source commit and migration checksum.
3. Verify Production Oracle backup and restore capability.
4. Perform read-only Production schema compatibility review.
5. Execute the approved additive migration.
6. Verify objects, constraints, metadata counts, and version 1 publication.
7. Deploy the application release.
8. Restart the application service.
9. Run health, readiness, login, MFA, RBAC, tenant, Master Designer, template,
   import-history, audit, and protected-field checks.
10. Keep the previous application release available for rollback.

## Rollback

Application rollback restores the previous release. Database rollback requires
the verified Oracle backup/restore procedure; no destructive ad-hoc rollback SQL
is supplied.
