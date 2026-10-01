# Guest Email / WhatsApp Flow

One Guest Trip Access record produces one secure HTTPS link. Email and WhatsApp
outbox rows reference the same `guest_trip_access_id`; separate Guest trips or
tokens are not created per channel.

The existing notification architecture is reused:

- Email is queued for the existing worker/SMTP path.
- WhatsApp is queued as the existing manual `wa.me` link because no configured
  WhatsApp provider was found.
- No provider credentials were invented.
- No delivery, read, or open event is claimed without provider confirmation.

Actual Email/WhatsApp delivery was not tested in LAB.
