# Offline Trip Continuity Design

Part 1 reuses the Trip Continuity foundation. A physical trip has a UUID
identity and operational `RTT-XXXXXX` reference independent of Booking ID.
Normal, Current Active, and Offline Emergency modes are represented separately.

The existing Flutter client has a bounded persistent GPS queue and the backend
has tracking-session/GPS idempotency. Full offline Driver activation is not
enabled because trusted-device/offline authorization is not implemented.
