# Phase 2.4 GPS and WebSocket Architecture

The LAB source currently uses this transition architecture:

```text
Flutter background location stream
  -> durable local point queue
  -> authenticated tracking-session batch API
  -> Oracle gps_log + gps_latest_positions
  -> process-local realtime publisher
  -> authorized tracking WebSocket
```

Oracle is the historical source of record. The latest-position table is
additive and does not replace `gps_log`. WebSocket delivery is display-only and
must not control collection or queueing. Redis fanout/latest-position recovery
is not available in the current source environment and remains unimplemented.

The next required hardening step is replacing the Dart background location
authority with a native Android foreground location service and exercising the
full physical-device recovery matrix.
