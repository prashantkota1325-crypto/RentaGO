# Late Booking Entry Design

## Canonical Time Model

- `bookings.booking_date`: server-created booking record date used by the existing model.
- `bookings.booking_punched_at`: server-side database timestamp for the actual booking punch.
- `bookings.late_entry_entered_at`: server-side timestamp for the authorized late-entry operation.
- `bookings.actual_start_at` / `actual_end_at`: explicit historical actual service timestamps for offline entries.
- `trips.actual_start_dt` / `actual_end_dt`: existing trip-level actual timestamps and the canonical trip-sheet values.
- `trips.feedback_submitted_on`, signature `*_at`: server-side feedback/signature event timestamps.

The booking punch time is never used as the trip start or drop time. The late-entry form accepts historical trip times, while the database assigns entry timestamps with `SYSTIMESTAMP`.

## State and Authorization

Late entries use `is_late_entry='Y'`, `entry_mode='OFFLINE_SYSTEM_DOWNTIME'`, a mandatory reason, and completed trip state. Only internal users with Booking module access can submit the route. Tenant, Vendor, Driver, Vehicle, assignment, active-state, and compliance checks run before insertion.

## Mobile Mode

Completed late entries are loaded as `post_trip_mode`. Guest mobile exposes feedback/safety feedback and Guest Signature. Driver mobile exposes feedback/safety feedback, Guest Signature, and Driver Signature. Normal start/end/share-location/GPS actions are outside that branch and no tracking session is created by late entry.

## Signature Source

The existing trip signature columns are extended with source, timestamp, and operator metadata. A Guest signature captured from Driver Mobile remains a Guest signature; only its source is `Driver Mobile`.

## Migration Safety

`db/migrations/late_post_trip_entry.sql` is repeatable and source-only. `verification.sql` is read-only and `rollback.sql` is intended only for an isolated lab database. None are executed by application startup or this implementation.
