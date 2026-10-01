# Phase 2.4.2 Snapshot Recovery

`/track/{booking_id}/{who}/{token}/snapshot` returns authoritative pickup/drop,
latest GPS, persisted points, trip status, and freshness. WebSocket clients can
use this snapshot on initial load and reconnect. End-to-end client reconnect
verification was not available.
