# Master Designer 1.0 Specification

Environment: LAB / SOURCE ONLY

## Architecture

Master Designer metadata is stored separately from business tables. Existing
`MASTERS` configuration remains the bootstrap source and published metadata is
an overlay consumed by the existing import/export engine.

Metadata tables:

- `MASTER_DEFINITIONS`
- `MASTER_FIELD_DEFINITIONS`
- `MASTER_FIELD_OPTIONS`
- `MASTER_FIELD_ALIASES`
- `MASTER_CUSTOM_VALUES`
- `MASTER_CONFIGURATION_VERSIONS`
- `MASTER_CONFIGURATION_AUDIT`

Adding a custom field does not add an Oracle business-table column. Custom
values are stored by tenant, master, record, and field metadata ID.

## Lifecycle

1. Existing metadata is bootstrapped from `app/routes/masters.py`.
2. Super Admin edits create draft metadata changes.
3. Publish creates an immutable `PUBLISHED` configuration snapshot.
4. The existing importer loads the published snapshot before validation.
5. Previous published snapshots become `SUPERSEDED`.

## Supported Masters

Companies, Corporate Admin Contacts, Company Contacts, Employees, RentaGO
Employees, Vendors, Vehicles, Drivers, Individuals, Contracts, Rate Cards,
Sales Leads, and Settings.

Rate Card import remains disabled because no approved stable business key exists.

## Safety Decisions

- Technical names are restricted to `^[a-z][a-z0-9_]*$`.
- SQL identifiers are never accepted from user input.
- Tenant ownership is always server-derived.
- Protected/generated fields cannot be configured as normal import fields.
- Published metadata is versioned and audited.
- No business records are seeded by the Master Designer migration.
