# Late Booking Driver Mobile Completion

## Post-Trip Surface

Completed late/offline bookings expose only Guest Feedback, Safety Feedback,
Guest Signature, and Driver Signature on Driver Mobile. Live location, SOS,
start, end, route, and GPS controls are outside the post-trip branch.

## API Enforcement

`POST /mobile/driver/{booking_id}/participant-feedback` accepts Driver feedback
only for a post-trip booking. Start, end, live-tracking, and SOS routes reject
post-trip rows server-side, independently of UI hiding.

## Data and Audit

Driver feedback and safety fields extend the existing `TRIPS` record. Driver
feedback records include the server timestamp and submitting Driver. Existing
signature source metadata remains unchanged: a Guest signature captured from
Driver Mobile is still a Guest signature with Driver Mobile as its source.

## Migration

Driver feedback columns are included in the repeatable late-entry migration,
read-only verification, and lab rollback scripts. Production was not connected
or modified.
