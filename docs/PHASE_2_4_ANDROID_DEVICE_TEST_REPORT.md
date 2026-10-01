# Phase 2.4 Android Device Test Report

## Device discovery

- ADB state: `device` (authorized)
- Manufacturer: OnePlus
- Model: CPH2717
- Android: 16
- SDK: 36
- ABI: arm64-v8a
- LAB application ID: `com.rentago.mobile`
- APK configuration: debug, version `1.0.0`, version code `1`
- Location services: device reports GPS/fused providers available
- Fine/background/foreground-service location permissions: granted at inspection
- Battery during inspection: 49%, USB powered

## Installation/build

- Debug build: PASS (`flutter build apk --debug`)
- Package discovery: PASS (`adb shell pm path com.rentago.mobile`)
- Production package or production APK: not used

## Acceptance results

The APK was launched for device discovery only. A valid authenticated driver
trip/session was not available for this automated pass, so the following remain
**BLOCKED / NOT TESTED** rather than PASS:

- Native locked-screen GPS receipt
- Background-app GPS receipt
- Network-off queue and resync
- GPS-disabled recovery
- Permission revocation/recovery
- Token expiry recovery
- WebSocket reconnect
- Server/database/Redis restart recovery
- Long-duration tracking

ADB commands used are recorded in the Phase 2.4 implementation session. No
device wipe, root, factory reset, or unrelated data modification was performed.
