# Trip Continuity Architecture

## Identity Graph

```text
TRIP_CONTINUITY_ID
  |-- Booking ID (nullable until reconciliation)
  |-- Tracking Session ID
  |-- Trip Events
  |-- GPS telemetry
  |-- Odometer / Trip
  |-- Signatures and feedback through the linked booking/trip
```

`trip_continuity_id` is a UUID-backed internal identity. `trip_reference` is a
short `RTT-XXXXXX` operational reference and is not an authentication secret.

## Modes

- `NORMAL`
- `CURRENT_TRIP_ACTIVE`
- `OFFLINE_EMERGENCY`

Existing historical late entries remain distinct through
`HISTORICAL_POST_TRIP` and do not start live tracking.

## Existing Architecture Reuse

The implementation reuses `bookings`, `trips`, `gps_log`, and
`tracking_sessions`. No second booking, trip, or GPS system was created.
