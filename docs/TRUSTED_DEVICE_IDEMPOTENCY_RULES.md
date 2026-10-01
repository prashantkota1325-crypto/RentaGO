# Trusted Device Idempotency Rules

- Device provisioning rejects an already-provisioned device ID.
- Device key ID and public key have unique LAB indexes.
- Challenge IDs are one-time-use.
- Challenge replay is rejected after `USED` transition.
- Offline event idempotency and sequence rules remain Phase 2.3B/2.3C scope.
