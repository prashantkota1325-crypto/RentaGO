# Trip Continuity State Machine

Implemented foundation states:

```text
CREATED / AWAITING_BOOKING
  -> READY
  -> TRIP_STARTED
  -> TRIP_ENDED
  -> BOOKING_LINKED
```

The existing booking/trip status machine remains authoritative for normal and
active-late operational actions. `trip_events` preserves the physical-trip
ledger independently of Booking ID.

Emergency/offline records currently have identity and event persistence, but
full offline Driver activation and reconciliation workflows remain pending.
