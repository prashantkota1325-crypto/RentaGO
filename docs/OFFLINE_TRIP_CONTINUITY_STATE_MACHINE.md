# Offline Trip Continuity State Machine

```text
CREATED / AWAITING_BOOKING
  -> READY
  -> TRIP_STARTED
  -> TRIP_ENDED
  -> BOOKING_LINKED
```

Event ledger entries record `TRIP_CREATED`, `TRIP_STARTED`, `START_ODOMETER`,
`TRACKING_SESSION_STARTED`, `GPS_POINT`, `END_ODOMETER`, `TRIP_ENDED`, and
`BOOKING_LINKED` where the existing backend lifecycle reaches those points.

Offline client-side state transitions remain unsupported until trusted-device
authorization and a durable event sync worker are implemented.
