# RentaGO Android Background GPS Implementation Report

## Status

```text
PHASE 2 BLOCKED
```

## 1. Existing GPS Architecture Reused

Current browser tracking uses:

```text
navigator.geolocation.getCurrentPosition()
        ↓
POST /track/{booking_id}/{who}/{token}/ping
        ↓
bookings GPS fields + gps_log
        ↓
Tracking Dashboard / GPS trail
```

The existing backend endpoint, tenant authorization, mobile session binding,
booking token, database GPS storage, and map/trail logic should be reused.

## 2. Android Architecture

Planned architecture:

```text
Native Android App
        ↓
Android Foreground Location Service
        ↓
Android Location APIs
        ↓
Existing RentaGO GPS API
        ↓
Existing Oracle GPS storage
```

The native service must run only during an authorized active tracking session
and must stop after trip completion, cancellation, expiry, logout, or server
revocation.

## 3. Files Created

No Android project files were created.

Only this planning report was created:

```text
docs/RENTA_GO_ANDROID_BACKGROUND_GPS_IMPLEMENTATION_REPORT.md
```

## 4. Files Modified

No application files were modified.

## 5. Backend Changes

No backend changes were made.

The existing endpoint is compatible with a minimum native client using:

```json
{
  "lat": 0.0,
  "lon": 0.0
}
```

Any future native authentication or idempotency extension requires a separate
design and isolated testing phase.

## 6. Database Changes

No database changes were made.

The existing `bookings` and `gps_log` structures can store the minimum
latitude/longitude/server-time payload.

## 7. Authentication Integration

The existing mobile flow uses:

- User ID or mobile identity.
- Booking ID.
- Four-digit PIN.
- Signed session cookie.
- `user_sessions.mobile_booking_id`.
- Tenant membership.
- Booking identity and tracking-token validation.

A native client will need secure session/token storage and a supported way to
reuse this authorization flow without storing credentials insecurely.

## 8. Authorization Integration

The server remains authoritative for:

- User role.
- Tenant membership.
- Booking visibility.
- Guest/Driver identity.
- Session booking binding.
- Tracking token.
- Active booking state.

The native client must never authorize itself using client-supplied tenant,
organization, booking, driver, or guest identifiers.

## 9. Guest Tracking Flow

```text
Guest mobile authentication
        ↓
Booking-bound mobile session
        ↓
Authorized active booking
        ↓
Native background location
        ↓
/track/{booking_id}/guest/{token}/ping
```

## 10. Driver Tracking Flow

```text
Driver mobile authentication
        ↓
Booking-bound mobile session
        ↓
Authorized assigned booking/trip
        ↓
Android Foreground Location Service
        ↓
/track/{booking_id}/driver/{token}/ping
```

## 11. Locked-Screen Behavior

The current browser implementation cannot reliably continue GPS when the phone
is locked because mobile operating systems may suspend browser JavaScript and
geolocation timers.

The future Android implementation must use a visible Android foreground
location service with a persistent notification.

Exact two-minute delivery cannot be guaranteed. The correct behavior is
approximately 120-second tracking subject to Android scheduling, GPS,
permissions, battery restrictions, and network availability.

## 12. Offline Queue

Not implemented.

Future native work requires a bounded local queue with:

- Maximum queue size.
- Controlled retry/backoff.
- Stale-point handling.
- Duplicate protection.
- Network recovery upload.

## 13. GPS Interval

Future initial configuration should be reviewed in an isolated mobile test:

- Target interval: approximately 120 seconds.
- Fastest interval: configurable and conservative.
- Accuracy: appropriate for vehicle tracking without excessive battery use.

The operating system controls actual delivery timing.

## 14. Battery Considerations

The native service must avoid continuous high-frequency polling and must stop
outside authorized active trips. Android battery optimization behavior must be
tested on representative devices.

## 15. Permission Handling

Future Android work must handle:

- Foreground location permission.
- Precise versus approximate location.
- Background/foreground-service location requirements.
- Location services disabled.
- Permission revocation.
- Battery optimization restrictions.
- Network unavailability.

The application must show tracking state honestly and must not hide the
foreground service.

## 16. Security Controls

Required future controls:

- HTTPS only.
- Secure token/session storage using Android Keystore-backed storage.
- No passwords or PINs stored in the app.
- Server-side booking and tenant authorization.
- Coordinate validation.
- Session expiry and revocation handling.
- Replay/duplicate protection for offline retries.
- No secrets in logs.

## 17. Tests Performed

Discovery checks performed:

- Existing GPS source inspection.
- Existing mobile/session inspection.
- Existing backend route inspection.
- Existing schema inspection.
- Native project search.
- Android toolchain availability inspection.

No application, database, or mobile tracking tests were executed.

## 18. Tests Not Performed

- Android build.
- Android emulator/device test.
- Foreground service test.
- Locked-screen test.
- Permission test.
- Offline/retry test.
- Network recovery test.
- Native authentication test.
- GPS API integration test.
- Production test.

## 19. Known Limitations

- No native mobile project exists in the repository.
- Java/JDK is not available.
- Gradle is not available.
- Android SDK is not available.
- `adb` is not available.
- Android emulator is not available.
- Android Studio was not detected.
- No isolated backend/test database is available for native integration testing.
- The current machine must not be used to host the test Oracle/application.

## 20. Production Deployment Requirements

Future deployment requires:

- Separate native Android project/build environment.
- Isolated test backend/database first.
- Synthetic Guest/Driver test users and bookings.
- No production credentials in the mobile app.
- Android signing and release-key ownership controlled by RentaGO.
- Production HTTPS API endpoint only after isolated testing.
- Operational monitoring for stale GPS sessions.
- Separate review for app-store background-location permissions.

## Proposed Future File Changes

Only after the Android toolchain and isolated test environment are available:

```text
android/                         # New native Android project
android/app/...                  # Foreground location service and UI
android/...                      # Permissions, secure storage, networking
tests/                           # Backend/native integration coverage
docs/MOBILE_BACKGROUND_GPS_ARCHITECTURE.md
```

Backend changes should be avoided unless the existing session/API contract
cannot safely support native clients.

## Final Status

```text
PHASE 2 BLOCKED
```

No application source, database, credentials, `.env`, production process,
Cloudflare configuration, scheduled task, or Git history was modified.
