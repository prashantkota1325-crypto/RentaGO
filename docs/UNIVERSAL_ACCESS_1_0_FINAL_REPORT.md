# Universal Access 1.0 Final Report

Status: **PASS (LAB role validation)**

Guest, Driver, Admin, Vendor, and RentaGO universal role journeys were validated in LAB. Production deployment remains a separate, incomplete release activity.

## Implemented LAB Slice

- Added opaque, cryptographically random Universal Access tokens.
- Tokens are hashed at rest in `UNIVERSAL_ACCESS_TOKENS`.
- Tokens carry role, user, tenant, optional booking, destination, expiry, status, and one-time exchange state.
- Added `/access/{token}` universal entry point.
- Added `/access/download/{token}` fallback page.
- Added `/access/exchange` for Android context handoff.
- Added internal issuance endpoints for booking-bound and dashboard-bound access.
- Guest and Driver Share Live Location now issue a universal access link instead of requiring a manually pasted tracking URL.
- Guest browser fallback uses the existing Guest mobile session and eight-tool portal.
- Driver exchange retains P-256 trusted-device validation.
- Guest exchange does not invoke Driver trusted-device validation.
- Added Android HTTPS App Link intent filter for `app.rentago.co.in`.
- Added LAB custom scheme `rentago://access/<token>` for physical testing.
- Added automatic context loading in the Android app.
- Normal Android mode hides the technical base URL, participant, PIN, and tracking-link fields.
- The existing foreground GPS service was not changed.
- GPS trail display now distinguishes `Captured (IST)` and `Received (IST)`.

## Existing Guest Tools

The existing Guest portal remains the source of truth for:

1. Share Live Location
2. Start Trip
3. SOS Emergency
4. End Trip
5. Guest Feedback
6. Safety Feedback
7. Guest Signature
8. Driver Profile

## Android APK

LAB release-mode artifact:

`C:\RentaGOWork\rentago_mobile_android\build\app\outputs\flutter-apk\app-release.apk`

Build timestamp: `2026-09-29 18:38:28`

The artifact is release-mode but the project currently signs release builds with the debug key. It is not publishable to Google Play or suitable as a permanent production distribution artifact.

## Automated Validation

- Universal token unit/source checks: passed.
- Existing Guest access source tests: passed.
- Existing trusted-device unit tests: passed.
- Existing LAB Oracle integration tests: skipped unless explicitly enabled.
- Python compilation: passed.
- Android release APK build: passed.

## Physical LAB Validation

### Guest

- Universal custom-scheme handoff: passed.
- Booking context: `LT244-BOOKING` loaded automatically.
- Role context: `Guest` loaded automatically.
- Manual tracking URL/base URL/ID/PIN entry: not required.
- Native GPS baseline: passed.
- HTTP upload: `200`.
- Oracle baseline: sequence `1` persisted for session `aa826c88-2e3a-43ff-84b5-3252abd0db6e`.
- Locked-screen callback: passed, with `screenState=LOCKED` and sequences `4-9` observed.
- Locked-screen uploads: HTTP `200` with ACK-safe queue removal.
- Locked-screen Oracle persistence: sequences `1-11` persisted during the interval.
- Post-unlock callback: passed with sequence `12`, watchdog restart and recovery observed.
- Post-unlock Oracle state: sequence `12`, session `ACTIVE`.

### Driver

- Universal custom-scheme handoff: passed.
- Booking context: `LT244-BOOKING` loaded automatically.
- Role context: `Driver` loaded automatically.
- P-256 trusted-device exchange: passed using the existing LAB device binding.
- Manual tracking URL/base URL/ID/PIN entry: not required.
- Native GPS baseline: passed.
- HTTP upload: `200`.
- Oracle baseline: sequence `1` persisted for session `fad3dd29-04d4-4434-8cd5-85521fdf413b`.

### Admin, Vendor, RentaGO

- Universal app handoff reached the dashboard continuation path for each role.
- Admin role token was bound to `admin` / `RENTAGO`.
- Vendor role token was bound to `as8398` / `VEND-V018`.
- RentaGO role token was bound to `pras.k2200` / `RENTAGO`.
- Admin continuation opened `/home` with the internal RentaGO dashboard/navigation context.
- Vendor continuation opened `/home` with `Welcome, AS Travel Solution`, Vendor context, Bookings, Trips, Invoices, Payments, and Dashboard tools.
- RentaGO continuation opened `/home` with `Welcome, Prashant Kota`, Super Admin context, and internal Bookings/Dashboard tools.
- No Guest/Driver mobile context was exposed by these dashboard tokens.

## Blockers

- The realme LAB device is currently disconnected, so universal app-link context handoff and physical GPS validation are pending.
- Production `assetlinks.json` cannot be finalized without the actual release signing certificate fingerprint.
- No production release keystore is configured.
- No Google Play or MDM publisher credentials are configured.
- Production HTTPS/App Link deployment has not been performed and must remain untouched.

## Role Validation Result

- **UNIVERSAL ACCESS ROLE VALIDATION: PASS**
- Guest: PASS
- Driver: PASS
- Admin: PASS
- Vendor: PASS
- RentaGO: PASS
- Production HTTPS App Link verification.
- Production download/Play/MDM distribution.
- Guest eight-tool validation through the universal browser fallback.

## Remaining Release Dependencies

- Production signing identity/keystore.
- Production `/.well-known/assetlinks.json` with the actual release certificate fingerprint.
- Google Play Console or MDM distribution credentials.
- Production HTTPS deployment and App Link verification.

## Production

Production was not contacted or modified.

## Universal Access 1.1 Note

Universal Access 1.1 adds the manual `/access` Secure Token-only fallback. The server derives User ID, role, booking, and tenant from the validated token. Existing `/access/<secure-token>`, Guest, Driver, P-256, Guest 8-tool, and GPS PASS results remain unchanged. Driver manual fallback hands off to the existing Android P-256 flow rather than bypassing trusted-device validation.

## Universal Access 1.1 Status

- `/access` User ID + Secure Token: **PASS** for LAB GET/POST, physical form rendering, and server validation.
- Guest flow: **PASS**; physical form submission opened the existing Guest Trip Portal for `IN-900017`.
- Driver flow: **PASS** for User ID/token validation and physical handoff into the existing Driver Trip Portal with Ideal Now controls; P-256 validation remains mandatory before portal handoff.
- P-256 validation: **PASS** in the existing Driver Universal Access flow.
- Guest 8 tools: **PASS** by existing regression/source validation; unchanged.
- Existing `/access/<secure-token>`: **PASS**.
- Security smoke tests: valid exchange, replay rejection, expired rejection, revoked rejection, malformed/tampered rejection, and wrong User ID rejection passed.
- GPS engine modified: **NO**.
- GPS watchdog modified: **NO**.
- Production touched: **NO**.
- Production ready: **NO**.

## Security Smoke Results

- Valid Guest exchange: HTTP 200.
- Replayed Guest token: HTTP 403.
- Revoked token: HTTP 404.
- Expired token: HTTP 404.
- Malformed/tampered token: rejected as invalid.
- Tokens are opaque and hashed at rest.
- Role and booking context are server-side token fields; URL mutation does not alter them.
