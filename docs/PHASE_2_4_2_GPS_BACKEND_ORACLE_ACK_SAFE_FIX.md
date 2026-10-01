# Phase 2.4.2 GPS Backend / Oracle ACK-Safe Fix

## Root cause

The previous physical session exposed two separate issues:

1. The LAB backend had positional-bind defects in the `gps_log` insert and
   latest-position merge. These were corrected before this phase.
2. The Android uploader treated every HTTP 2xx as `SERVER_ACCEPTED` and removed
   the entire queue without reading `accepted`, `duplicates`, or `rejected`.

## Changes

`RentaGoGpsService.kt` now parses the batch JSON response. It removes only
events whose stable `gps_event_id` appears in `accepted` or `duplicates`.
Rejected, malformed, empty-ack, 401/403, 5xx, timeout, and network-failure
responses retain the queue.

Stable event IDs and sequence numbers are unchanged across retries.

## Validation

- Backend: `79 passed, 9 skipped`
- Flutter analysis: clean
- Flutter tests: `1 passed`
- Debug APK: built successfully
- Physical post-change offline/resync test: not yet run
- Oracle locked-screen proof after this change: not yet run

## Security

Trusted-device authentication, P-256/Ed25519 handling, `/track` contract,
Oracle schema, and production configuration were not changed.

## Final Status

```text
PARTIAL — implementation and automated validation complete;
physical offline/retry and locked-screen Oracle proof pending.
```
