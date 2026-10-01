# Late/Post-Trip Booking Entry

## Scope

This source-only change adds an internal RentaGO workflow for entering a trip after it has already occurred. It does not execute a database migration, deploy code, restart services, or send notifications.

## Behavior

- `GET/POST /bookings/late-entry` is limited to authenticated internal RentaGO users with Booking module access.
- The operator must enter the guest, actual pickup/drop timestamps, addresses, reason, and active Vendor/Driver/Vehicle master records.
- Vendor, Driver, and Vehicle are checked against the same tenant and vendor relationship before insert.
- The booking records `booking_punched_at` and late-entry operator metadata separately from the actual trip timestamps.
- The trip is created as completed with `actual_start_dt` and `actual_end_dt` equal to the entered historical times.
- The normal booking path is unchanged.
- Every late entry and mobile signature is written through the existing audit helper.

## Data Changes

`db/migrations/late_post_trip_entry.sql` is repeatable and additive. It adds late-entry metadata to `BOOKINGS` and source/timestamp/operator metadata to `TRIPS` signatures. It is intentionally not invoked by application startup.

## Known Limits

- This path does not create invoices or notifications.
- Signature metadata records capture source and operator, while the existing signature value remains the system's capture marker; no image payload is introduced.

## Phase 2 Driver Mobile

Completed late/post-trip Driver Mobile provides Guest Feedback, Safety
Feedback, Guest Signature, and Driver Signature. Driver feedback is stored on
the existing trip record with server timestamp and submitter metadata. Start,
end, live-tracking, and SOS routes reject post-trip rows server-side.
