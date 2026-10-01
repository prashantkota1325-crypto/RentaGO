# Phase 2.4 GPS Queue / Batch Forensic Audit

## 1. Executive Finding

The current native service owns GPS capture and a persistent Android
`SharedPreferences` queue. It uploads the entire persisted queue whenever a
new location callback invokes `flushQueue()`.

There is no independent retry timer, connectivity receiver, or queue-drain
worker. A failed upload is retained, but retry occurs only when another GPS
callback arrives or the service is started again.

## 2. Exact Source Flow

### Capture

`RentaGoGpsService.handleLocation()`:

- increments the in-memory `sequence`;
- creates `gps_event_id = native-{session}-{sequence}`;
- uses `Location.time` as `captured_at`;
- appends the event to `rentago_native_gps_queue/events`.

### Queue

The queue is a JSON array stored in `SharedPreferences`. It is written before
upload is attempted. The current implementation does not compact, deduplicate,
or atomically update individual queue entries.

### Upload

`flushQueue()` reads the complete JSON array and sends all events to:

```text
/track/session/{session}/batch
```

On any 2xx response it removes the entire `events` key. On non-2xx or an
exception it retains the queue. There is no response-level removal of only
accepted event IDs.

## 3. Tracking Session Dependency

The native service receives `base`, `session`, `token`, and `cookie` through the
MethodChannel when tracking starts. If any of these are blank, `flushQueue()`
returns without uploading. A queued event can therefore remain until the
service receives a valid session context and a later GPS callback triggers a
flush.

## 4. Flutter / Android Lifecycle

The current authoritative path is native Kotlin:

```text
Flutter MethodChannel -> RentaGoGpsService -> FusedLocationProviderClient
-> SharedPreferences queue -> HTTP batch upload
```

The old `flutter_background_service` dependency/startup was removed. The queue
and upload path in `tracking_service.dart` is no longer the authoritative GPS
producer.

## 5. Why `captured_at` and `received_at` Differed by Hours

The native queue preserves the original Android `Location.time` as
`captured_at`, while Oracle assigns `received_at` at batch insertion time.
Events captured earlier remain in `SharedPreferences` when upload is not
possible. When the service later starts with a valid session/backend, it reads
the old queue and submits it together. This explains the reported historical
`captured_at` range and common `received_at` timestamp.

The source does not prove whether the original outage was network loss, service
termination, or missing session context; that specific initiating cause is
**NOT DETERMINABLE FROM CURRENT SOURCE**.

## 6. Why Sequence Values Can Repeat

`sequence` is an in-memory field initialized to `0` whenever the native service
instance is created. It is not restored from the persisted queue or the server.
After service/process restart, new events can reuse sequence values. The queue
also has no explicit duplicate-sequence compaction.

The backend uses `gps_event_id`/session checks for duplicate events, but the
source alone cannot identify whether the reported duplicate sequence rows came
from service restart, multiple sessions, or concurrent queue submissions.
The exact cause of sequences `35/36`, `37/38`, etc. is therefore **NOT
DETERMINABLE FROM CURRENT SOURCE** without their event IDs/session rows.

## 7. Real-Time Capability

Real-time upload is possible only while all of the following hold:

- native callbacks continue;
- session context is present;
- the backend is reachable;
- a callback triggers `flushQueue()`;
- no concurrent flush race occurs.

The current source is not a guaranteed real-time uploader because retry is
callback-driven and the complete queue is uploaded as one batch.

## 8. Files and Functions

- `lib/main.dart`: `_startTracking()`, session creation and MethodChannel start.
- `lib/tracking_service.dart`: native MethodChannel and session persistence.
- `android/app/src/main/kotlin/com/rentago/mobile/RentaGoGpsService.kt`:
  `onCreate()`, `onStartCommand()`, `startLocationUpdates()`,
  `handleLocation()`, `upload()`, `flushQueue()`, `onDestroy()`.
- `app/routes/track.py`: authenticated batch ingestion and Oracle persistence.

## 9. Minimum Required Fix

The next queue-hardening change should:

- persist sequence allocation across service restarts;
- serialize uploads with an in-flight guard;
- remove only server-acknowledged events;
- trigger retry independently of a new GPS callback when connectivity returns;
- preserve original capture timestamps and event IDs;
- retain failed events after partial responses.

This requires Kotlin changes. Backend changes are only required if the existing
batch response does not provide sufficient per-event acknowledgement. Oracle
schema changes are not inherently required.

## 10. Final Status

```text
GPS CAPTURE: IMPLEMENTED
QUEUE: PERSISTENT BUT NOT FULLY HARDENED
UPLOAD: CALLBACK-TRIGGERED BATCH UPLOAD
REAL-TIME UPLOAD: NOT GUARANTEED
LOCK-SCREEN: PHYSICAL CALLBACKS PREVIOUSLY OBSERVED
PRODUCTION: UNTOUCHED
```
