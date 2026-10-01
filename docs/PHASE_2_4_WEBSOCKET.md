# Phase 2.4 WebSocket

Added LAB WebSocket display route:

```text
/track/ws/{booking_id}/{who}/{token}
```

It validates the existing participant/tracking token, sends persisted GPS
history first, then publishes accepted GPS batch points. It does not ingest GPS
and does not replace REST/batch persistence.

Limitations: process-local publisher, no Redis/distributed fanout, no physical
mobile verification, and no production deployment.
