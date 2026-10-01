# RentaGO Smart Booking Live Button Forensic Report

## Environment

LAB configuration verified:

- Environment: `development`
- Oracle host: `localhost`
- Port: `1521`
- Service: `XEPDB1`
- Schema: `RENTAGO`
- DSN: `localhost:1521/XEPDB1`

## Browser Button Source

Current source template: `app/templates/bookings/list.html:57`.

```html
<a class="btn btn-outline-primary" href="/bookings/smart">Smart Booking</a>
```

- Button text: `Smart Booking`
- Element: `<a>`
- `href`: `/bookings/smart`
- `onclick`: none
- JavaScript redirect: none
- `booking_id`: none

## Current Source Route Table

The current source registers `/bookings/smart` before `/bookings/{booking_id}`.
The Smart template opens a new workspace and posts Normal mode to
`/bookings/create` or Late mode to `/bookings/late-entry`.

## Actual Running LAB Process

Port `8000` is owned by Python process `9976`, started on `21-Sep-2026
12:50:32`. Its live `/openapi.json` was inspected:

- `/bookings/smart`: **absent**
- `/bookings/{booking_id}`: **present**
- Smart API paths: **absent**

Live requests against `http://127.0.0.1:8000` showed:

- `GET /bookings/smart`: `303` to `/auth/login`
- `GET /bookings/smart/duplicates`: `404`
- `GET /bookings/smart/repeat/ZZ-NOACCESS`: `404`

After authentication, the stale process can route `/bookings/smart` through
`/bookings/{booking_id}` with `booking_id=smart`, producing `Booking not found`.

## Fresh LAB Process Comparison

A temporary process from the current source was started on port `18005` and
stopped after testing:

- `/bookings/smart`: present in OpenAPI
- `/bookings/{booking_id}`: present
- `GET /bookings/smart` unauthenticated: `303` to `/auth/login`
- Smart APIs: registered

## Root Cause

The browser-facing LAB service on port `8000` is an older/stale application
instance. It does not contain the Smart Booking route. The current source and a
fresh process are correct, but the existing process was not reloaded.

## Fix Required

Reload/restart the LAB process serving port `8000` from the current source
directory. Do not terminate it automatically during this forensic pass. After
reload, confirm `/openapi.json` contains `/bookings/smart`, then log in and
click the button again.

## Tests

- LAB identity verification: passed.
- Current source route ordering: passed.
- Current source button target: passed.
- Current source template loading: passed.
- Full unittest suite: 55 passed.
- Fresh-process route comparison: passed.
- Browser physical verification: unavailable.

Production database: **NOT TOUCHED**.

Production deployment: **NOT DONE**.
