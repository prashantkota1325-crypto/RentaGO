# Phase 2.4 Failure Recovery

Implemented in LAB source:

- Location points are queued locally before upload.
- Upload uses retry-safe `session_id + gps_event_id`/sequence data.
- Batch responses remove accepted and duplicate points while retaining failed
  points.
- Server persistence is Oracle `gps_log`; current position is additive
  `gps_latest_positions`.
- Older sequence/timestamp points and implausible movement are rejected.

Not yet physically validated: network-off recovery, database restart, server
restart, Redis restart, token expiry, screen lock, and long-duration tracking.
