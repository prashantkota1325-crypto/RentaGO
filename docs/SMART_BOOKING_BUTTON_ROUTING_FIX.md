# Smart Booking Button Routing Fix

## Environment

LAB only. Verified as `development`, `localhost:1521/XEPDB1`, schema `RENTAGO`.
No production database, configuration, service, or live record was touched.

## Root Cause

The Smart Booking workspace route is the static route `GET /bookings/smart`.
The booking-detail route is the dynamic `GET /bookings/{booking_id}` and returns
the normal Booking not found page when an invalid ID is supplied. The Smart
Booking navigation must never pass a booking ID through that dynamic route.

## Current Navigation

The Bookings list button is explicitly:

```html
<a href="/bookings/smart">Smart Booking</a>
```

The static Smart route is declared before `GET /bookings/{booking_id}` in
`app/routes/bookings.py`. The workspace has no JavaScript redirect requiring a
booking ID. Normal mode posts to `/bookings/create`; late mode posts to the
existing `/bookings/late-entry` route.

## Verification

- Static route registration: passed.
- Static route precedes dynamic booking detail: passed.
- Button contains no `booking_id`: passed.
- Smart template loads without an existing booking: passed.
- Temporary LAB HTTP server `GET /bookings/smart`: redirected unauthenticated
  users to `/auth/login`, not Booking not found.
- Invalid booking IDs continue to use the normal booking-detail path.
- Existing normal and late-entry regression tests remain passing.

## Files Changed

- `tests/test_smart_booking_routing.py`
- `docs/SMART_BOOKING_BUTTON_ROUTING_FIX.md`

The application already contained the correct `/bookings/smart` button and
route; this fix adds regression coverage and documents the route boundary.

## Production

Production database: **NOT TOUCHED**.

Production deployment: **NOT DONE**.
