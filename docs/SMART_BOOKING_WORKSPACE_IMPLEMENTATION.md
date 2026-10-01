# Smart Booking Workspace Implementation

## Files

- `app/routes/bookings.py`: shared workspace page, tenant-scoped duplicate/repeat/rate APIs, lookup hardening.
- `app/templates/bookings/smart.html`: responsive progressive-disclosure workspace.
- `app/templates/bookings/list.html`: Smart Booking entry point.
- `tests/test_smart_booking_workspace.py`: source-level workspace coverage.

## APIs

- `GET /bookings/smart`
- `GET /bookings/smart/duplicates`
- `GET /bookings/smart/repeat/{booking_id}`
- `GET /bookings/smart/rate`

Existing lookup and creation APIs are reused. No new database tables or columns
were added for Phase 3.0.

Phase 3.1 tightened Booking module and `_can_modify_booking` checks on normal
creation, Smart duplicate/repeat/rate APIs, and corporate/guest/vendor/driver/
vehicle lookup routes. Internal RentaGO users use the existing broad-scope
policy; external users remain tenant-scoped.

## Modes

Normal mode posts to `/bookings/create`. Late/Post-Trip mode is permission
gated in the UI and posts to `/bookings/late-entry`, preserving Phase 2
authorization, timestamps, reason, historical validation, audit, and mobile
restrictions.

## Known Limitations

- Full contract/SLA/vendor recommendation cards are not yet modeled because no
  single existing recommendation API was identified.
- The rate preview exposes the existing base rate lookup; final commercial
  totals remain in the existing booking/pricing flow.
- Browser/device UI verification was not available.
- No schema migration was required.
- The existing pricing engine exposes only base rate through `customer_rate`;
  no unified tax/GST/discount/total service was found.
- Authenticated HTTP creation tests require valid LAB credentials and were not
  run with fabricated or extracted users.
