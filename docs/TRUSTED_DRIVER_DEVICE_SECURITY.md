# Trusted Driver Device Security

- Device IDs are not authentication credentials.
- Driver ID, Booking ID, Trip Continuity ID, phone, and email are not device credentials.
- Public keys are verified as Ed25519 keys.
- Payload signatures are verified server-side.
- Authorization expires within a bounded period of 1-30 days.
- Devices can be revoked or suspended.
- Driver, tenant, and Vendor identity are checked during validation.
- Private keys are never accepted or stored by the backend.
- Guest offline access remains disabled.
- Driver QR pairing remains unused.

The current Flutter application has not yet integrated Android Keystore key
generation; Android hardware-backed protection is therefore not claimed.
