# RentaGO Lock-Screen GPS Audit

## Scope

Read-only audit of the existing RentaGO web backend and the current Android Flutter client. No production services, databases, credentials, or external providers were changed.

## A. Existing GPS Implementation

- Browser tracking route: `POST /track/{booking_id}/{who}/{token}/ping`.
- Current production-compatible payload persists latitude, longitude, distance, sync status, address, and server capture time.
- Tracking authorization is bound to the authenticated participant, mobile session, booking, role, tenant scope, and tracking token.
- Route-deviation, pickup-arrival, driver/guest sync, and GPS trail logic exist.
- Current browser implementation uses JavaScript geolocation and timers; it is not reliable when the screen is locked.

Status: **PARTIAL**

## B. Existing Flutter Packages

`rentago_mobile_android/` exists and currently uses:

- `geolocator`
- `flutter_background_service`
- `flutter_local_notifications`
- `http`
- `shared_preferences`

The Android client provides RentaGO-branded Driver/Guest login, tracking-link parsing, foreground-service configuration, and location upload payloads containing speed and accuracy.

Status: **PARTIAL**

## C. Android Implementation

- Fine/coarse/background location permissions are declared.
- Foreground service and notification permissions are declared.
- Persistent notification channel setup exists.
- The app stores tracking configuration locally and starts a background location stream.
- The app sends location, speed, and accuracy to the existing tracking endpoint.
- A real device launch test exposed Android foreground-service watchdog restrictions: Android can reject a later background service restart with `ForegroundServiceStartNotAllowedException`.
- The latest service/channel fix has not yet completed a successful locked-screen acceptance test.

Status: **PARTIAL / NOT PRODUCTION-READY**

## D. iOS Implementation

- No `Info.plist` background location configuration exists.
- No `CLLocationManager` or AppDelegate location implementation exists.

Status: **NOT IMPLEMENTED**

## E. Existing Backend API

- Existing endpoint: `POST /track/{booking_id}/{who}/{token}/ping`.
- Server validates coordinates and tracking authorization.
- Server writes booking live-location fields and `gps_log` rows.
- Isolated schema/source additions include speed, accuracy, source, client timestamp, and device-session fields.
- Production runtime was intentionally rolled back to the legacy GPS-only query/insert until production migration approval.

Status: **PARTIAL**

## F. Existing WebSocket Implementation

- Operations dashboard uses HTTP requests/page refreshes rather than push delivery.
- No Redis/Valkey event layer exists.

Status: **NOT IMPLEMENTED**

## G. Existing Database Structure

- `bookings` stores current Driver/Guest GPS and timestamps.
- `gps_log` stores historical captures.
- Isolated database contains the additive GPS telemetry columns.
- No dedicated `tracking_sessions` table exists.
- No database idempotency key exists for location events.
- No database-enforced location-event uniqueness exists.

Status: **PARTIAL**

## H. Existing Offline Storage

- Flutter client stores tracking configuration in `shared_preferences`.
- No durable location event queue exists.
- No offline batch upload or acknowledgement protocol exists.
- Failed location uploads are not persisted for retry.

Status: **NOT IMPLEMENTED**

## I. Existing Notification Implementation

- Existing RentaGO notification outbox and worker are reused for tracking links.
- WhatsApp is represented by a manual `wa.me` link rather than a provider-backed sender.
- No GPS event WebSocket notification path exists.

Status: **PARTIAL**

## J. Existing Permission Handling

- Flutter requests location permission before starting tracking.
- Android manifest declares foreground/background location and notification permissions.
- Android battery optimization guidance is displayed but not programmatically verified.
- Permission changes while tracking and OEM-specific restrictions are not comprehensively handled.

Status: **PARTIAL**

## K. Current Problems

1. Browser GPS cannot guarantee screen-locked operation.
2. Android foreground-service restart behavior is restricted on current Android versions.
3. No completed real-device locked-screen acceptance test.
4. No iOS implementation.
5. No offline queue, retry acknowledgement, or idempotency.
6. No dedicated tracking-session lifecycle.
7. No WebSocket/realtime dashboard distribution.
8. Production speed/accuracy migration is not applied.
9. Existing tracking token/session behavior requires continued authorization and does not yet represent a native-device tracking session.
10. The current Flutter app requires manual tracking-link entry; deep-link onboarding is not implemented.

## L. Required Modifications

- Stabilize Android foreground service startup and recovery while the app is visible.
- Add explicit tracking-session creation/closure tied to assigned trip state.
- Add durable local location queue and bounded retry/idempotency.
- Add server-side speed/accuracy persistence through the approved migration.
- Add stale GPS and heartbeat separation.
- Add WebSocket/event delivery only after the REST persistence path is stable.
- Add Android real-device lock-screen testing across supported OS/OEM versions.
- Implement iOS separately on macOS/Xcode; it is not part of the current Windows phase.
- Replace manual tracking-link entry with secure deep linking after the core flow is validated.

## M. Risks

- Android OEM battery managers may suspend or kill background work.
- Android OS foreground-service restrictions may reject late restarts.
- Locked-screen tracking cannot be claimed without physical-device evidence.
- Offline retries can duplicate GPS records without server idempotency.
- Exposing a tracking endpoint without a dedicated session lifecycle increases token/replay risk.
- A WebSocket layer would add operational complexity and is not currently present.

## N. Testing Requirements

- Android physical-device test with screen on/off/locked.
- Android foreground notification verification.
- Permission revoke/regrant test.
- Battery optimization test.
- Network loss and recovery test.
- Duplicate/out-of-order location test.
- Trip completion stops collection and closes session.
- Backend authorization and tenant/Vendor tests.
- Isolated migration and rollback tests.
- Dashboard freshness and stale-state tests.
- iOS device test on macOS/Xcode before claiming iOS support.

## Current Conclusion

The existing Android client is a valid starting point, but locked-screen GPS is **not yet production-ready**. The next implementation phase should focus on Android foreground-service reliability, tracking-session lifecycle, offline/idempotent synchronization, and isolated physical-device testing. No implementation changes were made during this audit.
