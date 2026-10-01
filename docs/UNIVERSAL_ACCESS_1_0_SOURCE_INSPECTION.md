# Universal Access 1.0 Source Inspection

Status: Proposed architecture only. No production changes have been made.

## Existing Components

- Internal RentaGO authentication is served by `/auth/login`.
- Existing portal routes are `/auth/guest-login`, `/auth/driver-login`, `/auth/vendor-login`, and `/auth/corporate-login`.
- Guest and Driver mobile PIN login is served by `/mobile/guest-login` and `/mobile/driver-login`.
- Vendor mobile login is served by `/mobile/vendor-login`.
- Mobile login creates the existing `rentago_session` and `user_sessions` context, including `mobile_booking_id`.
- The Guest Trip Portal is `/mobile/guest` and retains the eight existing Guest tools.
- The Driver mobile portal is `/mobile/driver`.
- Guest Secure Access uses hashed, expiring tokens at `/guest/access/{token}` and creates a separate `rentago_guest_trip` session.
- Tracking sessions are created by `/track/{booking_id}/{who}/{token}/session/start` and are bound to the authenticated mobile user and booking.
- Role and tenant authorization is enforced in existing route helpers and must remain authoritative.
- The Android package is `com.rentago.mobile`.
- Android currently has only the launcher intent filter. No App Link intent filter or deep-link handler exists.
- Android currently exposes technical fields for base URL, participant, credentials, and tracking link. The current client can auto-load a booking tracking link after mobile login, but does not yet accept universal access context.
- `RentaGoGpsService.kt` contains the validated foreground GPS engine, callback thread, watchdog, request restart, queue, uploader, and ACK behavior. It is frozen for this phase.
- Android release signing currently uses the debug signing key. No release keystore exists in the source tree.

## Proposed Universal Flow

1. Create an opaque, random, hashed-at-rest Universal Access token bound to role, tenant, optional booking, destination, expiry, revocation state, and one-time exchange state.
2. Add one `/access/{token}` route that validates the token and either establishes an authenticated web context or renders a branded app/download continuation page.
3. Add one authenticated context-exchange endpoint for the Android app. It will return only the minimum short-lived context needed to establish the existing mobile session and tracking session; it will not return a password, PIN, cookie, private key, or database credential.
4. Route Guest tokens to the existing Guest Trip Portal, Driver tokens to the existing Driver experience, and internal/Vendor roles to existing authenticated dashboards.
5. Change the existing Guest `Share Live Location` action to open the universal app context when the app is installed, otherwise open the branded download continuation page.
6. Add Android App Link intent filters for the production domain and a separate LAB-safe configuration. The Android app will parse the short-lived token and call the context-exchange endpoint.
7. Keep technical diagnostic fields behind an explicit LAB/developer mode. Normal users will see only booking, role, GPS state, and Start Live Location.
8. Keep the current `RentaGoGpsService` contract unchanged after the app receives the authenticated booking context.
9. Normalize GPS display timestamps to the selected tenant timezone while retaining distinct captured and received timestamps and unchanged canonical stored values.

## Security Boundaries

- Universal tokens will not contain passwords, PINs, session cookies, private keys, or database credentials.
- Tokens will be hashed at rest, expiry-controlled, revocable, role-bound, booking-bound where applicable, tenant-bound, audited, and exchanged once.
- Driver context exchange will still require the existing P-256 trusted-device validation where Driver GPS is authorized.
- Guest context exchange will use the existing Guest Secure Access/session authorization and will not invoke Driver trusted-device validation.
- Existing RBAC and booking assignment checks remain the final authorization authority.
- Full tokens must not be written to normal production logs.

## Blocking Inputs

- Production App Links cannot be finalized until the actual release signing certificate SHA-256 fingerprint is available.
- A production `/.well-known/assetlinks.json` deployment requires control of `app.rentago.co.in`; it will not be changed during LAB work.
- Google Play/MDM publication requires a production keystore and publisher/MDM credentials. The current debug-signed APK is LAB-only.
- HTTPS is required for the production universal link. The current LAB HTTP address cannot validate browser Geolocation and is not a production App Link target.

## Validation Boundary

The universal-access phase cannot be called PASS until a LAB physical journey proves Guest and Driver universal-link routing, app handoff, automatic booking context, Guest eight-tool access, native GPS start, locked-screen persistence using the frozen service, Oracle persistence, and post-unlock recovery. Admin, Vendor, and RentaGO routing require role-specific credentials and will be validated without weakening RBAC.
