# Guest Access Failure Handling

- Invalid, expired, or revoked links return a controlled access-unavailable
  response.
- Missing Guest contact information prevents access issuance.
- Email/WhatsApp provider failures remain in the existing notification outbox
  retry/manual workflow.
- If Backend, Email, and WhatsApp are all unavailable, no new Guest credential
  is issued. There is no insecure Booking ID, Trip Reference, or Driver QR
  fallback.
- Provider credentials and raw access tokens are not logged.
