# RentaGO Ideal Now Driver/Vendor Allocation Audit

## 1. Executive Summary

RentaGO already has:

- Driver master records.
- Vendor master records.
- `drivers.vendor_id` relationship.
- `vehicles.vendor_id` relationship.
- `bookings.vendor_id` and driver/vehicle fields.
- Tenant-aware booking visibility.
- Vendor-scoped dashboards/resources/billing.
- Server-side allocation routes.
- Audit logging.

RentaGO does not currently have:

- An `IDEAL_NOW` availability state.
- A Driver availability/session table.
- A Driver-facing booking opportunity/acceptance workflow.
- An atomic claim/accept operation for competing Drivers.
- A complete Driver compliance gate before allocation.

The feature is feasible, but it requires a small additive availability/claim
design and carefully scoped allocation logic. No implementation was performed.

## 2. Existing Driver Architecture

### Driver identity

- User identity: `users.user_id`.
- Role: `users.role = Driver`.
- Identity fields: `users.name`, `users.mobile`, `users.emp_id`.
- Mobile authentication: `users.mobile_pin_hash` plus booking-scoped mobile login.
- Session: `user_sessions.mobile_booking_id`.

### Driver master

Table: `drivers`

Relevant fields:

```text
driver_id
tenant_id
vendor_id
driver_name
mobile
license_expiry
police_verification
background_check
compliance_status
status
```

## 3. Existing Vendor Architecture

Table: `vendors`

Relevant fields:

```text
vendor_id
tenant_id
vendor_name
status
kyc_status
agreement_status
```

Vendor identity is derived from the authenticated user's `organization_id`
with the `VEND-*` convention and tenant membership.

The current authorization helper is `authorization_tenant()` in
`app/scope.py`.

## 4. Existing Driver → Vendor Relationship

The authoritative relationship is:

```text
drivers.vendor_id -> vendors.vendor_id
drivers.tenant_id -> tenant context
```

The current allocation flow now scopes Driver and Vehicle lookup/create by:

```text
booking tenant_id + booking vendor_id
```

Driver name/mobile remains a display/legacy identity field and should not be
the long-term sole authorization key.

## 5. Existing Booking Architecture

Table: `bookings`

Relevant allocation fields:

```text
tenant_id
vendor_id
vendor_name
driver_name
driver_contact
vehicle_no
booking_status
status_reason
step2_time
step3_time
alloc_lead_override
vendor_deadline
```

Current booking lifecycle includes:

```text
1-Pending
2-Confirmed
3-Cancelled
Trip In Progress
Trip Completed
```

Exact open/available status terminology is not represented by a dedicated
`OPEN` state; availability is inferred from booking status and reason.

## 6. Existing Allocation Architecture

### Vendor allocation

