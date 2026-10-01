# Universal Access 1.1: Secure Token Access

## Purpose

Universal Access 1.1 adds a common manual fallback page at `/access`. It does not replace `/access/<secure-token>`.

The complete Step 3 delivery and Guest/Driver handoff is documented in `docs/SMOOTH_GUEST_DRIVER_LOGIN_1_2.md`.

## Flow

1. Guest or Driver opens `/access`.
2. The user enters only the opaque Secure Token.
3. The server resolves and derives role, user, booking, and tenant context from the token/database.
4. Guest is routed into the existing Guest Trip Portal.
5. Driver is handed to the existing Android app flow, where P-256 trusted-device validation remains mandatory.

## Security

- Existing Universal Access token hashing, expiry, revocation, replay protection, role binding, booking binding, and tenant binding are reused.
- The browser never supplies User ID, role, booking, or tenant context.
- Failed User ID/token combinations receive a generic error.
- Raw tokens are not written to audit logs.
- Driver browser fallback cannot bypass P-256; it opens the existing app handoff.

## Compatibility

- `/access/<secure-token>` remains available.
- Guest eight-tool portal remains unchanged.
- Guest Share Live Location continues using the Universal Access app bridge.
- The frozen GPS engine and `RentaGoGpsService.kt` were not modified.

## Status

Implemented and compiled in LAB. Production deployment remains separate and is not done.

## Step 3 Delivery

After Driver and Vehicle allocation completes Step 3, the existing notification outbox now queues:

- Guest Universal Access: Email + WhatsApp
- Driver Universal Access: WhatsApp only

No new WhatsApp or email provider was added. Actual delivery still depends on the existing SMTP configuration and the existing manual WhatsApp `wa.me` workflow.
