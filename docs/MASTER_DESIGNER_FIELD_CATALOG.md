# Master Designer Field Catalog

This catalog is generated from the existing Master configuration and LAB
metadata tables. It distinguishes physical existing fields from metadata-only
custom fields.

## Status Definitions

- **EXISTING:** maps to an existing Oracle business-table column.
- **PROPOSED:** requested concept with no approved physical column; not added
  automatically.
- **CUSTOM:** stored in `MASTER_CUSTOM_VALUES`, not a physical business column.
- **SYSTEM PROTECTED:** server-controlled or generated; not a normal import field.
- **IMPORT ENABLED:** accepted by the published import configuration.
- **IMPORT DISABLED:** excluded from normal import.

## System Protection

`TENANT_ID`, timestamps, audit identities, generated primary keys, credentials,
passwords, MFA secrets, API keys, database credentials, and encryption secrets
are protected. Tenant ID is never accepted as an ownership override from a
spreadsheet.

## Existing Schema Rule

The existing Oracle columns remain the source of truth for existing fields.
Custom fields use metadata storage. Proposed fields require a separately
approved schema or custom-field design decision and are not silently added to
business tables.

## Rate Cards

Rate Card metadata is present for display/export configuration, but
`import_enabled` is `N`. The reason is the absence of an approved stable source
business key and corresponding uniqueness policy.
