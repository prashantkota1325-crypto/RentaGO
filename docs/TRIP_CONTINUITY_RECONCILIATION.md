# Trip Continuity Reconciliation

The continuity foundation permits `booking_id` to remain NULL and later stores
the authoritative link through `POST /bookings/{booking_id}/trip-continuity/link`.
The link operation is tenant-scoped, idempotent, updates booking/trip
continuity columns, and appends `BOOKING_LINKED`.

Automatic matching of offline records to bookings is intentionally not enabled.
Uncertain matches must remain unresolved rather than being silently merged.
Future reconciliation must validate tenant, Vendor, Driver, Vehicle, Guest,
timestamps, event sequence, duplicate keys, and audit the decision.
