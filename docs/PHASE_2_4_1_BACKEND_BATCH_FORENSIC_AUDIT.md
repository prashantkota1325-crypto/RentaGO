# Phase 2.4.1 Backend Batch Persistence Forensic Audit

## A. Exact Endpoint

```text
POST /track/session/{tracking_session_id}/batch
```

Implemented in `app/routes/track.py`, function
`tracking_session_batch()`, lines 234 onward.

## B. Android Success Condition

`RentaGoGpsService.kt`, `flushQueue()`, lines 167-172:

- reads only `connection.responseCode`;
- treats every HTTP status from `200` through `299` as success;
- removes the entire persisted `events` queue on any 2xx response;
- does not parse `accepted`, `duplicates`, or `rejected` from the JSON body.

The log label `SERVER_ACCEPTED` therefore means **HTTP 2xx**, not that every
queued GPS event was accepted by the backend.

## C. Backend Response Contract

Early responses:

- `400` for missing token/events or more than 100 events;
- `403` for invalid tracking session/authentication;
- `409` for paused sessions.

Normal completion returns HTTP `200`:

```json
{
  "ok": true,
  "accepted": [],
  "duplicates": [],
  "rejected": [],
  "next_expected_sequence": 1
}
```

The arrays are populated per event, but the Android uploader currently ignores
their contents.

## D. Backend Execution Path

1. Parse JSON and extract `tracking_token` and `events`.
2. Resolve `tracking_sessions` through `_tracking_context()`.
3. Validate tenant, booking, mobile user/session, and booking binding.
4. Reject paused sessions.
5. Validate each point with `validate_point()`.
6. Check duplicate `tracking_session_id + gps_event_id` in `gps_log`.
7. Check latest sequence/timestamp in `gps_latest_positions`.
8. Check configured rapid-movement threshold.
9. Insert accepted event into `gps_log`.
10. Append trip-continuity event when applicable.
11. Publish the realtime event.
12. Merge the latest position into `gps_latest_positions`.
13. Update booking GPS columns/timestamp.
14. Add accepted event ID to the response.
15. Update `tracking_sessions.last_sequence` and `last_seen_at`.
16. Commit once after the loop.
17. Return HTTP `200` with accepted/duplicate/rejected arrays.

Relevant source: `app/routes/track.py:234-323`.

## E. Every 2xx Branch

The normal route has one HTTP 2xx completion branch at lines 320-323. It can
return HTTP 200 when:

- every event is accepted;
- every event is duplicate;
- every event is rejected by validation/order/movement checks;
- any mixture of accepted, duplicate, and rejected events occurs.

## F. Can 2xx Occur Without GPS_LOG Insertion?

**Yes.** If all events are duplicates or rejected, the route still commits and
returns HTTP 200. No new `gps_log` row is inserted in that case.

## G. Accepted/Duplicate/Rejected Interpretation

The backend distinguishes these correctly in its JSON response. The Android
uploader does not inspect the response JSON. It deletes the entire queue for
any 2xx status, including `accepted=[]` with only rejected or duplicate items.

## H. Transaction and Commit Behavior

- Accepted inserts, latest-position merges, booking updates, and session updates
  share one transaction.
- `conn.commit()` occurs at line 320.
- Early validation/session failures close the connection without the normal
  commit.
- There is no route-level exception handler converting an insert/merge failure
  into a successful response; Oracle errors surface as HTTP 500.

## I. Most Likely Root Cause

For session `5a8f48f8-0950-4403-b4ef-a9854925da64`, Oracle shows no GPS rows and
`last_sequence=0`. The queue log reported `SERVER_ACCEPTED`, but that only proves
the Android client saw HTTP 2xx.

The source permits a false-success queue removal if the backend returned HTTP
200 with `accepted=[]` and the events were rejected or duplicate. The current
session evidence alone does not prove which response body was returned, because
the Android client discarded it.

The previous session comparison shows:

- `6e293dae-5b31-4fb1-be41-e8b82251ab21`: 39 GPS rows, sequences 34-72,
  `last_sequence=72`.
- `5a8f48f8-0950-4403-b4ef-a9854925da64`: 0 GPS rows,
  `last_sequence=0`.

The exact rejection/duplicate reason for session `5a8f...` is **NOT
DETERMINABLE FROM CURRENT LOGS**, because the Android upload log records only the
HTTP status and not the response JSON.

## J. Evidence

- Android queue removal condition: `RentaGoGpsService.kt:167-172`.
- Backend response construction: `app/routes/track.py:320-323`.
- Duplicate branch: `app/routes/track.py:259-263`.
- Validation rejection branch: `app/routes/track.py:251-256`.
- Old/suspicious rejection branches: `app/routes/track.py:264-279`.
- LAB Oracle session query showed session `5a8f...` with zero GPS rows and
  `last_sequence=0`.
- LAB Oracle session query showed prior session `6e293...` with 39 rows and
  sequences 34-72.

## K. Exact Source Files

- `android/app/src/main/kotlin/com/rentago/mobile/RentaGoGpsService.kt`
  - `flushQueue()`
- `app/routes/track.py`
  - `_tracking_context()`
  - `tracking_session_batch()`
- `app/gps_validation.py`
  - `validate_point()`

## L. Recommended Fix — Not Implemented

The Android uploader should parse the HTTP 200 JSON before deleting queue data:

- remove events only when their IDs are in `accepted` or `duplicates`;
- retain rejected events and record their rejection reason;
- retain the queue when `accepted` and `duplicates` are both empty;
- log the response counts without logging credentials or tokens.

No code or database changes were made for this audit.

## Final Status

```text
PASS — FORENSIC AUDIT COMPLETE
```

Production was not accessed or modified.
