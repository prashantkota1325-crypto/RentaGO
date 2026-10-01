# Trusted Driver Device Integration Architecture

The backend trusted-device foundation is extended into the existing Flutter
Android app through a MethodChannel:

```text
Flutter Driver App
  -> Android Keystore MethodChannel
  -> Ed25519 public key / signature
  -> existing /auth/driver-devices/validate endpoint
```

The private key remains in Android Keystore. Dart receives only the device ID,
public key, and signature result. Offline trip operations remain disabled.
