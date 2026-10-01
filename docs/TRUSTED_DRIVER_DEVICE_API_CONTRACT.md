# Trusted Driver Device API Contract

Existing backend endpoints reused:

- `POST /auth/driver-devices/provision`
- `POST /auth/driver-devices/validate`
- `POST /auth/driver-devices/{device_id}/revoke`

Validation payload:

```json
{
  "device_id": "...",
  "device_key_id": "...",
  "payload": "device|driver|timestamp",
  "signature": "base64url Ed25519 signature"
}
```

The backend validates device status, expiry, Driver, tenant, Vendor, public-key
signature, and authenticated Driver session.
