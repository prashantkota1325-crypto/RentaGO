# Offline Trip Continuity Sync Protocol

The current Part 1 foundation supports server-side Trip Continuity identity,
ordered/idempotent events, and GPS tracking-session linkage. It does not yet
provide a client-to-server offline event synchronization endpoint or trusted
offline Driver authorization.

Existing GPS batch synchronization remains Booking/Tracking Session based. Full
Booking-ID-null reconciliation and conflict resolution are not enabled.
