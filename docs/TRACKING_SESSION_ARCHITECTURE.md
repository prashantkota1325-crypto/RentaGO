# Tracking Session Architecture

Phase 1 adds a dedicated `tracking_sessions` model separate from login sessions.

The session binds:

- Tracking session ID
- Tenant
- Booking
- Authenticated user
- Participant role
- Hashed tracking token
- Status
- Start/end timestamps
- Last accepted sequence

Tracking session start, batch upload, and end remain authenticated and booking-bound. Production deployment is not authorized.
