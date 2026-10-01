# Active Late Entry Design

## State Model

The existing booking state machine is reused:

```text
Late Entry - Active
  -> Trip In Progress
  -> Trip Completed
```

Historical entries continue to use `Trip Completed` and the Phase 2 post-trip
mode. `entry_mode` distinguishes `OFFLINE_SYSTEM_DOWNTIME_ACTIVE` from the
historical `OFFLINE_SYSTEM_DOWNTIME` mode. `late_entry_type` distinguishes
`CURRENT_TRIP_ACTIVE` from `HISTORICAL_POST_TRIP`.

## Canonical Times

- Booking punch: `bookings.booking_punched_at`
- Historical actual pickup: `bookings.actual_start_at`
- Historical actual drop: `bookings.actual_end_at`
- Driver trip start: `trips.actual_start_dt`
- Driver trip end: `trips.actual_end_dt`

These values are never substituted for one another.

## Shared Lifecycle

Active late entry uses the existing Driver start and end trip routes, existing
`pickup_start_km` and `drop_end_km`, existing `trips` row creation, existing
audit, and existing `track_token`/`gps_log` tracking path. No parallel booking
or trip identity is created.

## GPS Rule

Creating an active late entry does not start GPS. After the Driver starts the
trip, the server prepares the existing tracking link. The existing browser
tracking endpoint and Flutter tracking service remain the ingestion paths.
