# Trusted Driver Device State Machine

```text
DEVICE_NOT_PROVISIONED
        -> OFFLINE_AUTHORIZED
        -> OFFLINE_EXPIRED
        -> DEVICE_REVOKED
        -> DEVICE_SUSPENDED
```

Only online provisioning can create a trusted device. Re-provisioning an
existing device requires explicit revocation first. Revocation cannot be
silently reversed by the device.
