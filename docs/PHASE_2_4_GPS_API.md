# Phase 2.4 GPS API

LAB endpoints currently used:

- `POST /track/{booking_id}/{who}/{token}/session/start`
- `POST /track/session/{tracking_session_id}/batch`
- `POST /track/session/{tracking_session_id}/end`
- `GET /track/{booking_id}/{who}/{token}/snapshot`

Batch events require `gps_event_id`, `sequence_number`, `lat`, `lon`, and an
ISO-8601 `captured_at`. Optional telemetry includes accuracy, speed, and
heading. The response separates `accepted`, `duplicates`, and `rejected`
events and returns `next_expected_sequence`.

The existing browser `/ping` endpoint remains for compatibility. The native
driver path uses the session batch endpoint.
