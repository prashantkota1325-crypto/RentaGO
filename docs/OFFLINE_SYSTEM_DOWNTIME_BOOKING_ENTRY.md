# Offline / System-Downtime Booking Entry

This internal-only workflow records a trip accepted or completed while the
booking system was unavailable. It is not a normal booking shortcut and is not
available to Corporate, Vendor, Guest, or Driver users.

The operator supplies historical `actual_start_at` and `actual_end_at` values.
The database supplies `booking_punched_at`, `late_entry_entered_at`, audit,
signature, and feedback submission timestamps with `SYSTIMESTAMP`; browser
timestamps are never trusted. `entry_mode=OFFLINE_SYSTEM_DOWNTIME` and
`post_trip_reason` preserve the entry state and reason separately from service
timestamps.

Vendor, Driver, and Vehicle are resolved inside the authenticated tenant. The
Driver must belong to the Vendor, and active/compliance checks used by ordinary
allocation apply before insertion. No GPS start or tracking is created.

The result is a completed booking and Trip with historical actual timestamps.
Mobile Guest/Driver post-trip controls are limited to feedback, safety
feedback, signatures, and logout; start, end, share-location, and GPS controls
remain unavailable. Feedback uses the normal ownership, safety notification,
audit, and report visibility paths.

Driver Mobile feedback uses the existing trip record with Driver-specific
feedback and safety columns. Direct live-trip, tracking, and SOS endpoints
reject rows identified as post-trip; this is enforced independently of the
rendered UI.

Migration execution is separate from application startup. Apply
`late_post_trip_entry.sql` only in an approved isolated database, verify with
`verification.sql`, and use `rollback.sql` when required.
