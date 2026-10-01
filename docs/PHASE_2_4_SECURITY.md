# Phase 2.4 Security

GPS batch authorization derives booking, participant, tenant, and mobile
session scope from the server-side `tracking_sessions` record. The submitted
IDs do not establish authorization. Existing trusted-device and Ed25519
components remain unchanged.

Validation includes coordinate bounds, finite numeric values, required ISO
timestamps, positive sequence numbers, duplicate protection, old-event
protection, and configurable maximum movement speed.
