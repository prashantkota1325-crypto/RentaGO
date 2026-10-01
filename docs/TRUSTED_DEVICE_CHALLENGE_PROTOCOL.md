# Trusted Device Challenge Protocol

1. Authenticated Driver requests a challenge for the registered device.
2. Server verifies the Driver/device/tenant/Vendor binding.
3. Server returns a short-lived challenge and ID.
4. Android Keystore signs the canonical challenge payload.
5. Server verifies the registered Ed25519 public key.
6. Server atomically marks the challenge used.

The challenge cannot be reused. No Booking ID or Trip Continuity ID is used as
the nonce or credential.
