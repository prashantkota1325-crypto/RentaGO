# Offline Driver Operational Security

Offline operation is denied until all trusted-device conditions can be proven:

- Driver previously provisioned
- Device trusted and device-bound
- Offline authorization valid and unexpired
- Device not revoked or suspended
- Tenant/vendor relationship valid
- Cryptographic device identity valid

None of these Phase 2.3A controls are present in the current source. Enabling
offline emergency operation now would create an anonymous or replayable Driver
credential, so it is intentionally not implemented.

Trip Continuity ID remains an operational identifier and is not authentication.
