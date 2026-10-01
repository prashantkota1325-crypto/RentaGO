# Mobile/Web Session Separation

Phase 1 source implementation separates `web` and `mobile` rows in `user_sessions`.

- Web login replaces only the user's `web` session.
- Mobile login replaces only the user's `mobile` session.
- Mobile tracking authorization requires a mobile session bound to the booking.
- Browser login must not revoke an active mobile tracking session.
- The change is source-only until the isolated migration is applied and tested.

Production status: **NOT DEPLOYED**.
