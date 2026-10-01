# Guest Secure Trip Access

Guest access is issued by an authorized internal RentaGO Booking user through
`POST /bookings/{booking_id}/guest-access`. The server creates one
`GUEST_TRIP_ACCESS_ID` linked to the Booking and Trip Continuity ID, generates
a cryptographically random token, and stores only its SHA-256 hash.

The token is short-lived, tenant-scoped, Guest-scoped, revocable, and exchanged
for a separate `guest_trip_sessions` cookie. Trip Continuity ID, Booking ID,
phone, and email are never accepted as credentials. No Driver QR pairing exists.

The Guest view is available at `/guest/access/{token}` and `/guest/trip` after
session creation. It displays only the authorized booking's trip information.
Provider delivery is queued through the existing notification outbox.
