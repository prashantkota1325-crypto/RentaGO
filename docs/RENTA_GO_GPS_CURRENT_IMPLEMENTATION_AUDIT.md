# RentaGO GPS Current Implementation Audit

## 1. Executive Summary

RentaGO currently uses a browser-based mobile tracking page for Guest and
Driver GPS collection. The page calls `navigator.geolocation.getCurrentPosition`
immediately and then uses a JavaScript timer targeting 120 seconds.

The backend GPS ingestion path already exists and can be reused by a native
Android/iOS client. The database already stores booking GPS fields and a full
`gps_log` trail.

There is no native Android, iOS, Flutter, React Native, Capacitor, or Ionic
mobile GPS layer in the repository.

The locked-screen limitation is primarily a browser/mobile-OS execution issue,
not a missing database or map capability.

## 2. Current GPS Architecture

```text
Guest/Driver mobile browser
        |
        | navigator.geolocation.getCurrentPosition()
        | JavaScript interval: 120 seconds
        v
/track/{booking_id}/{who}/{token}/ping
        |
        | session, tenant, booking, role and token checks
        v
Oracle bookings table + gps_log table
        |
        +--> booking GPS fields
        +--> GPS trail CSV/detail views
        +--> Tracking dashboard
        +--> location-sync / red-flag calculations
```

Separately, the in-process tracking worker queues tracking links when the
Driver or Guest tracking window opens.

## 3. Browser GPS Implementation

### Primary file

`app/templates/track.html`

### Current implementation

The inline JavaScript uses:

```javascript
navigator.geolocation.getCurrentPosition(send, fail, ...)
```

It then schedules:

```javascript
setInterval(..., 120000)
```

It also sends a location when the document becomes visible again.

### Guest and Driver coverage

- Guest: Same tracking page and API, with `who=guest`.
- Driver: Same tracking page and API, with `who=driver`.

### Current execution behavior

- Active foreground tab: Best effort GPS capture.
- Background tab: Browser-dependent and unreliable.
- Locked screen: Not reliable; mobile operating systems may suspend the page and timer.
- Browser permission denied: Location submission fails.
- Network failure: The current page does not implement a durable offline queue.

## 4. GPS API

### Tracking page

```text
GET /track/{booking_id}/{who}/{token}
```

### GPS submission

```text
POST /track/{booking_id}/{who}/{token}/ping
```

### Current request payload

```json
{
  "lat": 18.5204,
  "lon": 73.8567
}
```

### Authentication and authorization

The endpoint requires:

- Authenticated mobile session cookie.
- Mobile request detection.
- Session-bound `mobile_booking_id`.
- Valid booking `track_token`.
- Correct Guest/Driver role.
- Tenant-scoped booking visibility.
- Correct Driver/Guest relationship.
- Active booking tracking state.

### Processing

`app/routes/track.py:track_ping()`:

- Parses latitude/longitude.
- Rejects coordinates outside valid ranges.
- Loads booking and validates token/state.
- Validates participant session and booking binding.
- Checks tracking window.
- Updates booking GPS fields and timestamp.
- Calculates pickup arrival and route deviation where applicable.
- Calculates Guest/Driver distance and sync status.
- Inserts a `gps_log` record.
- Commits the transaction.

Server time is authoritative for `captured_dt`. No client timestamp is currently
accepted.

## 5. Database GPS Schema

### `bookings`

Relevant fields:

```text
driver_gps
guest_gps
driver_gps_ts
guest_gps_ts
driver_live_location
guest_live_location
track_token
track_sent
location_sync
```

### `gps_log`

Relevant fields:

```text
log_id
booking_id
who
lat
lon
location_sync
location_address
captured_dt
```

Index:

```text
idx_gps_log_booking_time (booking_id, captured_dt)
```

### `user_sessions`

Relevant fields:

```text
session_id
user_id
mobile_booking_id
mobile_expires_at
last_activity
```

The existing schema can store native GPS latitude/longitude submissions.

Missing optional telemetry fields:

- Accuracy.
- Speed.
- Heading.
- Altitude.
- Client timestamp.
- Device identifier.
- Client event/idempotency identifier.

No schema change is required for a minimum native client that sends the
existing latitude/longitude payload. Additive schema/API changes may be useful
later for accuracy and idempotency.

## 6. Tracking Session Architecture

Current model:

```text
User
  -> user_sessions
  -> mobile_booking_id
  -> booking.track_token
  -> /track/.../ping
```

There is no separate `tracking_sessions` table.

Tracking token creation is handled by `app/tracking.py` and booking tracking
routes. The token is stored on the booking.

## 7. Booking → Trip → GPS Relationship

```text
Booking
  -> booking_id
  -> tenant_id
  -> Guest/Driver identity
  -> tracking token
       |
       v
Trip
  -> booking_id
  -> trip status
       |
       v
GPS fields and gps_log
```

Tracking is accepted only for active booking/trip states. Completed and
cancelled states are rejected.

## 8. Guest GPS Architecture

- Login: Mobile User ID/mobile + booking ID + 4-digit PIN.
- Session: Signed session cookie bound to `mobile_booking_id`.
- Tenant: Active `tenant_memberships` record.
- Identity: `users.emp_id` compared with `bookings.emp_guest_id`, with legacy composite fallback.
- Token: Booking `track_token`.
- Endpoint: Shared `/track/.../ping` endpoint.
- Storage: `guest_gps`, `guest_gps_ts`, `gps_log`.
- Stop conditions: Tracking window, cancellation, completion, session expiry/revocation, or invalid token.

Current limitation: Browser execution is not reliable after screen lock.

## 9. Driver GPS Architecture

- Login: Mobile User ID/mobile + booking ID + 4-digit PIN.
- Session: Signed session cookie bound to `mobile_booking_id`.
- Tenant: Active tenant membership.
- Identity: Driver name/mobile relationship, with booking visibility checks.
- Token: Booking `track_token`.
- Endpoint: Shared `/track/.../ping` endpoint.
- Storage: `driver_gps`, `driver_gps_ts`, `gps_log`.
- Stop conditions: Tracking window, cancellation, completion, session expiry/revocation, or invalid token.

Current limitation: Browser execution is not reliable after screen lock.

## 10. GPS Authorization Model

The server authorization chain is:

```text
Authenticated user/session
        ↓
Role
        ↓
Session mobile_booking_id
        ↓
Tenant membership
        ↓
Booking visibility
        ↓
Guest/Driver relationship
        ↓
Tracking token
```

The endpoint does not authorize from booking ID alone.

Observed concerns:

- Driver fallback identity still uses Driver name/mobile matching where no
  stronger driver relationship is available.
- No idempotency key exists for GPS retries.
- GPS log IDs are generated by scanning existing IDs, which can race under
  concurrent submissions.
- The tracking module documentation says the link has no login requirement,
  while the current implementation requires a mobile session. Documentation is
  inconsistent with implementation.

## 11. Map and Trail Architecture

Relevant components:

- `app/routes/maps.py`: map/geocoding/routing facade.
- `app/routes/dashboards.py`: Tracking Dashboard.
- `app/routes/bookings.py`: GPS trail/detail and CSV access.
- `app/templates/bookings/gps_trail.html`: GPS trail display and refresh.
- `app/gps.py`: GPS parsing, distance, and sync calculations.

The Tracking Dashboard reads booking GPS fields and creates map links. The GPS
trail reads `gps_log` records.

The existing map/trail views can consume native-generated points if native
clients continue writing through the existing API.

## 12. WebSocket / Realtime Architecture

No WebSocket, SSE, or EventSource implementation was found.

Current behavior uses:

- Normal server-rendered pages.
- GPS trail page refresh behavior.
- Periodic worker processing.
- Browser-side tracking timer.

No realtime backend change is required for minimum native GPS ingestion. The
existing dashboard may continue using refresh/polling behavior.

## 13. Offline / Network Handling

Current browser implementation:

- Does not maintain a durable offline GPS queue.
- Does not submit batches.
- Does not provide client idempotency keys.
- Does not explicitly handle out-of-order points.
- Retries only through future browser timer calls.
- Stores no durable local GPS queue.

Native clients will need bounded offline buffering and controlled retry.

## 14. Current Locked-Screen Limitation

### Browser limitation

The current implementation relies on browser JavaScript timers and browser
geolocation. Android and iOS may suspend the page, timer, or geolocation when
the screen is locked or the app is backgrounded.

### Backend limitation

The backend can accept GPS submissions, but it cannot collect location when no
client request is sent.

### Authentication limitation

Native clients cannot directly assume browser cookie behavior. They will need a
secure session/token integration using the existing mobile authorization model
or a backward-compatible extension.

### Database limitation

The current database can store latitude/longitude/timestamp data. It lacks
optional accuracy, speed, heading, altitude, client timestamp, and idempotency
fields.

### Realtime limitation

There is no WebSocket/SSE channel. This affects live display freshness, not GPS
ingestion itself.

### Network limitation

The current browser flow loses or delays location when the browser is suspended
or the network is unavailable.

## 15. Native Mobile Readiness

No native mobile GPS layer currently exists.

No Android, iOS, Kotlin, Swift, Flutter, React Native, Capacitor, Ionic, or
native project files were found.

The backend and database are reusable, but a native application layer must be
created in a later phase.

## 16. Security Findings

### HIGH

- Browser GPS cannot be treated as reliable locked-screen tracking.
- No client-side idempotency protection exists for retries.
- GPS log ID generation scans existing IDs and can race under concurrency.

### MEDIUM

- Driver authorization uses name/mobile fallback where no stronger relationship
  is available.
- No accuracy, client timestamp, or device telemetry is retained.
- Tracking module documentation does not match the current session requirement.
- No native mobile authorization/integration test suite exists.

### INFORMATIONAL

- No native mobile code is present.
- No WebSocket/SSE implementation is present.
- Existing map/trail storage is reusable.

## 17. Recommended Minimum Architecture

```text
Android Foreground Location Service
              |
              v
Swift iOS Background Core Location
              |
              v
Existing RentaGO HTTPS GPS API
              |
              v
Existing tenant/session/booking authorization
              |
              v
Oracle bookings + gps_log
              |
              v
Existing tracking dashboard and GPS trail
```

No Traccar dependency is required for the minimum Year-1 solution.

## 18. Required Backend Changes

Minimum native integration may reuse the existing API without schema changes
if native clients submit only latitude and longitude.

Likely future backend work:

- Document native session acquisition and secure cookie/token storage.
- Add safe client-event idempotency if offline retry is required.
- Optionally accept accuracy, speed, heading, altitude, and client timestamp.
- Add server-side rate limits suitable for native clients.
- Add operational tracking-health metrics.

These changes were not implemented.

## 19. Required Android Changes

- Native Kotlin application.
- Android Foreground Service.
- Fused Location Provider.
- Precise/background location permissions as required by Android version.
- Persistent user-visible tracking notification.
- Secure session storage using Android Keystore-backed storage.
- Bounded offline queue and retry.
- Explicit tracking start/stop UI.
- Completion/cancellation shutdown behavior.

## 20. Required iOS Changes

- Native Swift application.
- `CLLocationManager`.
- Background location capability.
- Required Info.plist location descriptions.
- Secure Keychain session storage.
- Background location lifecycle handling.
- Bounded retry behavior.
- Tracking start/stop and trip-completion handling.

Exact 120-second delivery cannot be guaranteed by Android or iOS; the correct
requirement is approximately 120-second tracking subject to OS scheduling.

## 21. Database Changes

```text
NO DATABASE CHANGE REQUIRED
```

for a minimum native client using the existing latitude/longitude API and
storage.

Optional future additive fields for accuracy, speed, heading, client time, and
idempotency were not applied.

## 22. API Compatibility Assessment

The existing API can accept a minimum native payload:

```json
{
  "lat": 18.5204,
  "lon": 73.8567
}
```

Compatibility: **PARTIAL**.

The endpoint can be reused, but native authentication must integrate with the
existing signed mobile session and booking binding. A native client must not
send booking ID alone as authorization.

## 23. Authentication Compatibility

Existing mobile authentication can be reused conceptually:

- Mobile User ID/mobile.
- Booking ID.
- PIN.
- Tenant membership.
- Session-bound booking.
- Existing signed session cookie.

Native implementation will need a secure way to obtain and retain that session
without browser local storage or insecure plaintext storage.

## 24. Tracking Lifecycle

```text
START TRIP
    ↓
START TRACKING
    ↓
SCREEN LOCKED
    ↓
OS-supported background GPS continues
    ↓
GPS API
    ↓
DATABASE
    ↓
LIVE MAP / TRAIL REFRESH
    ↓
TRIP COMPLETED
    ↓
STOP TRACKING
```

The server must continue enforcing all start, stop, tenant, booking, and
session rules.

## 25. Implementation Plan

### Phase A — Native mobile foundation

Create controlled Android/iOS projects outside the production-like host.

### Phase B — Android background GPS

Implement Foreground Service and isolated test backend integration.

### Phase C — iOS background GPS

Implement Core Location background behavior and isolated testing.

### Phase D — GPS API compatibility

Document or minimally extend native authentication and optional metadata.

### Phase E — Offline/retry

Add bounded local queue and idempotency protection.

### Phase F — GPS health monitoring

Add last-received timestamp and stale-session operational visibility.

### Phase G — Live map integration

Reuse existing tracking dashboard/trail; add realtime improvements only if
needed.

### Phase H — Security testing

Test cross-tenant, cross-booking, token replay, session expiry, duplicate,
offline, and locked-screen behavior in an isolated environment.

### Phase I — Production deployment

Perform controlled mobile release and backend rollout after review.

## 26. What MUST NOT Be Changed

- Existing booking lifecycle.
- Existing trip lifecycle.
- Existing tenant and object authorization.
- Existing mobile PIN authentication without a tested compatibility plan.
- Existing `/track/.../ping` contract unless backward-compatible extension is
  required.
- Existing GPS database tables for the minimum implementation.
- Existing tracking dashboard and GPS trail behavior.
- Production Oracle/XEPDB1.
- Production `.env`.
- Cloudflare configuration.
- Production scheduled tasks and workers.

## 27. Risks

- Mobile operating systems can delay background location events.
- Exact 120-second timing cannot be guaranteed.
- Native session storage and API authentication require security review.
- Offline retry can create duplicate GPS records without idempotency.
- Native app permissions may be denied or restricted by users.
- Battery optimization may affect tracking reliability.
- Current driver identity fallback needs review for native authorization.
- App-store background-location policies require compliance review.

## 28. Final Recommendation

1. RentaGO can achieve locked-screen GPS without Traccar: **YES**.
2. Existing GPS backend can be reused: **YES, with native session integration**.
3. Existing GPS database can be reused: **YES for minimum lat/lon tracking**.
4. Existing map/trail can be reused: **YES**.
5. Existing realtime system can be reused: **PARTIALLY**; current system relies on polling/page refresh rather than WebSocket/SSE.
6. Minimum new component: **Native Android Foreground Service and native iOS background-location client**.
7. Future files requiring modification: Native mobile project files, possibly `app/routes/track.py` for backward-compatible native session/metadata support, tests, and documentation.
8. Files that should not be modified unnecessarily: booking workflow, tenant authorization, existing GPS schema, production configuration, Cloudflare, and production worker setup.

No native implementation was created in this phase.
