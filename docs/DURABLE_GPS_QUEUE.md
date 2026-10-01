# Durable GPS Queue

The Android client persists a bounded queue of GPS events in `SharedPreferences` before upload. Events include a session ID and sequence number. Accepted and duplicate events are removed after a successful batch response; failed uploads remain queued for the next location tick.

Current limitation: `SharedPreferences` is a Phase 1 foundation, not a full transactional mobile database. Offline durability, crash consistency, bounded retry policy, and physical locked-screen validation remain outstanding.
