# Active Late Entry Implementation

## Backend

- `POST /bookings/late-entry` accepts `late_entry_type`.
- `HISTORICAL_POST_TRIP` preserves the existing completed-entry path.
- `CURRENT_TRIP_ACTIVE` creates a normal Booking ID with status `Late Entry - Active`, assigned Vendor/Driver/Vehicle, historical pickup time, and server punch/activation timestamps.
- Active entries require a valid starting odometer before creation.
- Driver Mobile uses the existing start-driver route and `pickup_start_km`.
- Driver Mobile uses the existing end-driver route and `drop_end_km`.
- Historical post-trip guards do not apply to active late entries.

## Database

Added to `BOOKINGS` through the existing repeatable migration:

- `late_entry_type`
- `late_entry_remarks`
- `is_late_entry_activated`
- `late_entry_activated_by`
- `late_entry_activated_at`

Existing actual-time, odometer, trip, GPS, and tracking-session columns were
reused. No new table or parallel identity was created.

## Mobile

The existing web Driver Mobile page displays `ACTIVE LATE ENTRY`, Start Trip,
Start Odometer, End Trip, and End Odometer through existing endpoints. The
existing Flutter app can consume the tracking link and run its current durable
GPS batch service; a new Flutter booking-control application was not created.
