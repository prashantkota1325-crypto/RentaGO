# Trip Continuity Sync Protocol

The LAB foundation uses:

1. Trip Continuity UUID as the physical-trip identity.
2. `trip_events.idempotency_key` for event replay protection.
3. `tracking_session_id + gps_event_id` for GPS replay protection.
4. `event_sequence` and GPS sequence numbers for ordering.
5. Nullable Booking ID on continuity-linked GPS/session records.

The internal API endpoints are:

- `POST /bookings/trip-continuity`
- `POST /bookings/{booking_id}/trip-continuity/link`

They require internal RentaGO Booking permission. Full client-side offline sync
and server reconciliation queues are not yet enabled.
