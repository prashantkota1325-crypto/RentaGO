# Offline Guest Access Disabled Policy

## Decision

`GUEST_OFFLINE_ACCESS = DISABLED` by design.

When the RentaGO backend is unavailable, an already trusted Driver Mobile
continuation may be considered only by a future approved offline Driver
authorization architecture. A Guest must not authenticate or access a trip
without a RentaGO-issued secure Guest credential and server-authorized Guest
session.

## Prohibited Fallbacks

The system must not use Trip Continuity ID, Booking ID, phone, email, local
OTP, shared password, Driver-generated token, Driver QR, anonymous access, or a
locally generated Guest credential as authentication.

Driver QR pairing is not implemented or retained as a Guest access path.

## Online Behavior

When the backend is available, Guest access uses the existing hashed,
expiring, revocable `GUEST_TRIP_ACCESS` credential and `GUEST_TRIP_SESSIONS`.
Email/WhatsApp delivery remains governed by the existing notification outbox.

## Outage Behavior

If no previously issued offline-capable artifact exists, new Guest access is
unavailable during a complete backend/communication outage. This is an
intentional security result, not a missing insecure fallback.

## Future Gate

Changing this policy requires separate approval and implementation of trusted
Driver-device authorization, signed artifacts, offline verification, replay
protection, local Guest event storage, synchronization, and physical security
testing.
