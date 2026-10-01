# Guest Access Security

- Access creation requires internal RentaGO identity and full Booking module
  permission.
- Raw tokens are generated with `secrets.token_urlsafe` and stored as SHA-256
  hashes.
- Access expires after 24 hours; Guest sessions expire after 12 hours or the
  access expiry, whichever comes first.
- Revocation changes access status to `REVOKED` and invalidates subsequent
  access/session validation.
- Tenant and booking IDs are checked server-side.
- Guest sessions are separate from Driver Mobile and tracking sessions.
- The Trip Reference is operational information only and is not a credential.
- No Driver QR, QR scanner, anonymous Guest login, or ID-based password exists.
