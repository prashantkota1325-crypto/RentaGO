# Trusted Device Replay Protection

The LAB backend now supports one-time server-issued challenges:

- `POST /auth/driver-devices/challenge`
- `POST /auth/driver-devices/challenge/verify`

Challenges are random, short-lived, device/Driver/Vendor/tenant bound, hashed
in the database, and marked `USED` after successful verification. A used or
expired challenge is rejected. The device signature covers challenge ID,

The broader offline event replay protocol remains reserved for Phase 2.3B/2.3C.
