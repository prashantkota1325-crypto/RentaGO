# GPS Batch API

Phase 1 adds the isolated-source endpoint:

```text
POST /track/session/{tracking_session_id}/batch
```

The request contains a tracking token and event list. Each event includes:

- `gps_event_id`
- `sequence_number`
- `lat`
- `lon`
- optional telemetry fields where migrated

The response separates accepted and duplicate event IDs. Authorization derives from the authenticated mobile session and tracking session.
