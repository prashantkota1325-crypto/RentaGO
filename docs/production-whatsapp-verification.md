# Production WhatsApp Verification

## Current Status

RentaGO currently stores WhatsApp links in the notification outbox and exposes them for manual opening. A production WhatsApp API/provider has not been fully configured or verified.

## Required Provider Verification

Before automated WhatsApp delivery is enabled, verify:

1. Provider account ownership.
2. Business number and sender identity.
3. Template approval for Step 1, Step 2, Step 3, SOS, tracking, cancellation, and SLA events.
4. Country/recipient formatting.
5. Authentication and secret storage.
6. Provider response and delivery status webhooks.
7. Signature verification for inbound webhooks.
8. Idempotency for retries and duplicate prevention.
9. Failure and dead-letter behavior.

Do not enable automated production messaging until these checks pass. Manual `wa.me` links remain available as the Year-1 fallback.
