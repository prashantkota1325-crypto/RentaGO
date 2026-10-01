# Phase 2.4.1 Independent GPS Queue Uploader

## Implementation

`RentaGoGpsService.kt` now owns an independent scheduled retry executor. It
attempts queue delivery every five seconds without requiring a new Flutter or
GPS callback. Uploads are serialized with an atomic in-flight guard. Sequence
values are recovered from persisted queued events when the service starts.

Existing GPS capture, authentication context, queue format, batch endpoint,
validation, and Oracle persistence were preserved.

## Failure behavior

- Events are persisted before upload.
- Non-2xx responses retain the queue.
- Exceptions retain the queue.
- Successful 2xx responses remove the queued batch.
- Stable `gps_event_id` and sequence values are retained across retries.

## Validation

- Flutter analysis: PASS
- Flutter tests: `1 passed`
- Debug APK build: PASS
- Physical offline/resync test: NOT TESTED
- Physical service restart durability test: NOT TESTED
- Production: untouched

## Status

**PARTIAL** until physical network-off, recovery, and locked-screen delivery
tests demonstrate actual Oracle receipt during the outage/recovery window.
