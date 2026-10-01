# Offline Guest Access Security

The current safe behavior during a complete Backend + Email + WhatsApp outage
is: no new Guest credential is issued.

This is intentional. The current system has no trusted offline Driver device
authorization or signed Guest artifact verifier. Adding a Booking ID, Trip
Continuity ID, phone-only, email-only, shared password, or Driver QR fallback
would weaken Guest security and is prohibited.
