# Trip Continuity Offline Design

The existing Flutter client has a bounded `SharedPreferences` GPS queue with
sequence numbers, event IDs, retry retention, and batch acknowledgement. This
is a foundation, not a fully transactional offline database.

Verified supported behavior:

- GPS queue survives normal app state while stored in preferences.
- Batch retry retains events after failed HTTP calls.
- Server deduplicates `(tracking_session_id, gps_event_id)`.

Not verified or implemented:

- Offline Driver authentication/authorization.
- Offline Start/End Trip event acceptance.
- Durable event ledger synchronization beyond GPS.
- Crash-consistent transactional local storage.
- Physical lock-screen and network-disconnect testing.
