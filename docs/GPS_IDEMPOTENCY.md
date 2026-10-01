# GPS Idempotency

Phase 1 uses the logical key:

```text
tracking_session_id + gps_event_id
```

Duplicate events are detected before insertion and returned as duplicates. Sequence numbers are retained for ordering and diagnostics. A database uniqueness constraint is required in the isolated migration before production use.
