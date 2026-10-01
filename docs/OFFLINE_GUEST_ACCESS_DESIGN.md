# Offline Guest Access Design

## Current LAB Decision

Offline Guest Access is **not implemented** in Part 2.3. The existing Guest
Secure Access implementation is backend-issued, token-hash based, and requires
the backend to validate the token and create a Guest Session.

The system therefore must not use Trip Continuity ID, Booking ID, phone, email,
or Driver QR as an outage credential.

## Required Future Foundation

Before enabling offline Guest access, RentaGO needs a trusted-device Driver
authorization model, a RentaGO signing key/public-key verification design, an
offline signed artifact, an offline Guest verifier, and an append-only offline
Guest event queue. None of those are present in the current LAB architecture.
