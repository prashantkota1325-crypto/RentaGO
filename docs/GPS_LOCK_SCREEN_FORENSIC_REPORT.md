# RentaGO Lock-Screen GPS Forensic Report

## Scope

This is a read-only forensic diagnosis of the current Android Flutter GPS, browser GPS, backend, database, and dashboard paths. No production database, credentials, external services, or production deployment were changed during this audit.

## Failure-Point Map

```text
PHONE GPS                         UNKNOWN for locked Flutter test
  |
OS LOCATION API                   UNKNOWN for locked Flutter test
  |
NATIVE BACKGROUND SERVICE         FAIL / UNSTABLE
  |
FLUTTER LOCATION SERVICE          UNKNOWN
  |
LOCATION EVENT                    PASS for browser; UNKNOWN for locked Flutter
  |
LOCAL QUEUE                       NOT IMPLEMENTED
  |
UPLOAD SERVICE                    FAIL for Flutter session; browser succeeds
  |
REST API                          PASS for browser, 403 for Flutter requests
  |
BACKEND VALIDATION                PASS; rejects invalid/stale participant session
  |
DATABASE                          PASS for accepted browser captures
  |
REALTIME EVENT / WEBSOCKET        NOT IMPLEMENTED
  |
OPERATIONS DASHBOARD              PASS via HTTP/page refresh for stored captures
  |
MAP MARKER                        PASS for stored browser capture
  |
GPS TRAIL / POLYLINE              PASS for stored browser capture; no realtime push
```

## 1. Existing GPS Implementation

- Browser route: `POST /track/{booking_id}/{who}/{token}/ping`.
- Browser JavaScript uses `navigator.geolocation` and a timer.
- Browser captures were observed in `gps_log` and displayed on the GPS Trail page.
- Current browser tracking cannot guarantee operation while the screen is locked.

## 2. Flutter/Android Implementation

- `geolocator` supplies location updates.
- `flutter_background_service` supplies the Android foreground service.
- `flutter_local_notifications` supplies the persistent notification channel.
- Android manifest declares location and foreground-service permissions.
- The client sends location, speed, and accuracy to the existing tracking endpoint.

## 3. Root Evidence: Android Service

The physical Android log showed:

```text
ForegroundServiceStartNotAllowedException
startForegroundService() not allowed due to mAllowStartForeground false
```

The service watchdog attempted to restart the service after the app left the foreground. Android rejected that background restart. This proves that service recovery is not reliable under the current implementation/device behavior.

The service was also observed in `dumpsys activity services`, but that alone does not prove location callbacks continued after lock.

## 4. Root Evidence: Authentication/Upload

The Vultr backend log showed both outcomes for the same tracking endpoint:

```text
POST /track/.../ping 200 OK
POST /track/.../ping 403 Forbidden
```

The `200` requests came from the browser tracking flow. The Flutter/background requests received `403` because the Driver session cookie was invalidated by another Driver login. The current session model deletes prior sessions for the same user during login.

Therefore the Flutter client can generate locations but still fail at the backend authorization stage if a browser Driver login occurs afterward.

## 5. Local Queue

No durable local GPS event queue exists. The Flutter client sends each location directly through HTTP. There is no persisted event ID, sequence number, offline queue, acknowledgement, or retry store.

Status: **FAIL for offline/reliable synchronization requirements**

## 6. REST API

The existing REST endpoint validates:

- Tracking token
- Booking state
- Participant role
- Mobile session binding
- Tenant/object visibility
- Coordinates

The endpoint accepts browser captures successfully. Flutter captures are rejected when the stored mobile session is stale or invalidated.

Status: **PARTIAL**

## 7. Database

- `gps_log` stores browser GPS captures.
- Isolated schema includes speed/accuracy/source fields.
- No dedicated `tracking_sessions` table exists.
- No location-event idempotency key or sequence uniqueness exists.
- No database WebSocket/event state exists.

Status: **PARTIAL**

## 8. WebSocket and Realtime Layer

No WebSocket, Redis, SSE, or broker implementation exists in the repository. Dashboard updates are request/page-refresh based.

Status: **NOT IMPLEMENTED**

## 9. Dashboard and Trail

The Operations GPS Trail page displayed multiple Driver captures, including six stored points in the isolated test. This proves:

- GPS points reached the backend through at least one client path.
- Points were stored in `gps_log`.
- The dashboard/trail rendered stored history.

It does not prove locked-screen Flutter continuity or realtime WebSocket delivery.

## 10. iOS

No iOS project, Core Location implementation, Info.plist background mode, or AppDelegate location configuration exists in the current Android-only Flutter client.

Status: **NOT IMPLEMENTED**

## 11. Exact Root Causes

1. **Android background restart failure:** the foreground-service watchdog restart is rejected by modern Android background-start restrictions.
2. **Flutter upload authorization failure:** browser and Flutter logins compete for one server-side Driver session; the later login invalidates the earlier session, causing Flutter GPS requests to receive `403`.
3. **No offline durability:** location data has no local queue or acknowledgement/retry mechanism.
4. **No realtime distribution:** there is no WebSocket layer; the dashboard cannot receive guaranteed push updates.

## 12. Required Fix Scope

- Start and promote the foreground service while the app is visibly active.
- Prevent service restart assumptions that violate Android background-start rules.
- Design device/session-aware tracking authorization rather than invalidating an active tracking device through an unrelated browser login.
- Add a bounded persistent location queue, event sequence, idempotency, and retry acknowledgement.
- Add server-side tracking-session lifecycle and stale detection.
- Add realtime delivery only after REST persistence is reliable.
- Preserve browser GPS as a compatibility path but do not treat it as locked-screen support.

## 13. Testing Gaps

- No successful five-minute locked-screen Flutter GPS test has been proven.
- No measured sequence continuity before/during/after lock.
- No offline queue test.
- No token refresh test during background operation.
- No duplicate/out-of-order event test.
- No WebSocket test exists because WebSocket is not implemented.
- No iOS test exists.

## 14. Status

**LOCK-SCREEN GPS: NOT FIXED**

The current system proves browser GPS persistence while unlocked and proves backend storage/trail rendering for accepted points. It does not yet prove the required physical locked-screen Flutter trail.

No further implementation changes were made during this forensic audit. The next code phase must address the four root causes above one logical phase at a time, beginning with Android foreground-service continuity and tracking-session authorization.
