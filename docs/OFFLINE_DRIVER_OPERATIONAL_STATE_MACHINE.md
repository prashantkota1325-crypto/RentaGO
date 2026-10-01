# Offline Driver Operational State Machine

The required states are documented but not enabled:

```text
ONLINE
OFFLINE_AUTHORIZED
TRIP_OFFLINE_READY
TRIP_OFFLINE_ACTIVE
TRIP_OFFLINE_ENDED
SYNC_PENDING
```

Current implementation supports online active-late trip states and server-side
Trip Continuity events only. It does not transition a Driver Mobile session to
`OFFLINE_AUTHORIZED`.
