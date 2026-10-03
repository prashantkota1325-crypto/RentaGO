# Master Designer Security Review

Environment: LAB / SOURCE ONLY

- Authentication: existing session authentication is required.
- Authorization: Designer requires internal access plus Super Admin or Roles
  Matrix `F` access.
- CSRF: existing application middleware protects POST forms.
- Tenant isolation: tenant configuration and custom values use authenticated
  server tenant context; uploaded `TENANT_ID` cannot override it.
- Protected fields: system IDs, tenant fields, credentials, and generated
  values cannot be configured as normal import fields.
- Technical names: strict identifier validation prevents SQL fragments and
  injection through metadata.
- Field types: closed allowlist; arbitrary executable expressions are not
  accepted.
- Aliases: normalized and stored separately; duplicate mappings remain
  ambiguous and stop import.
- Versions: publish creates immutable version records; prior versions become
  `SUPERSEDED`.
- Audit: field changes and publishing write configuration audit records.
- Imports: existing signed preview, source hash, expiry, replay, transaction,
  audit, history, error, RBAC, and CSRF controls remain in use.
- Exports: existing tenant-scoped CSV/XLSX paths are used; formula-like strings
  are neutralized.
- Secrets/data: no credentials, workbook records, or business records are
  stored by the metadata migration.

Rate Card import remains explicitly blocked.
