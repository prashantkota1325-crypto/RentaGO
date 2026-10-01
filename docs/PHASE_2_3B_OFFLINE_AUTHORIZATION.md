# Phase 2.3B Offline Authorization

The backend contains trusted-device and offline-authorization database
foundations, but the authorization lease is not yet issued to or consumed by
the Flutter app. No offline Driver authority is granted by this phase.

Required blockers before enabling operation:

- authenticated lease issuance flow
- Android Keystore lease storage/verification
- finite lease consumption
- revocation/expiry behavior on device
- physical Android verification
