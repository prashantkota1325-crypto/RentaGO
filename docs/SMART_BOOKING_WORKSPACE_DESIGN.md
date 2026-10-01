# Smart Booking Workspace Design

## UX Architecture

`/bookings/smart` is a shared operator workspace with two modes: Normal Booking
and Late/Post-Trip Entry. The page follows Search -> Select -> Auto-fill ->
Confirm -> Create. Normal mode submits to the existing `/bookings/create`
workflow. Late mode submits to the existing audited `/bookings/late-entry`
workflow; it does not duplicate the late-entry implementation.

## Data and Auto-Fill

Corporate, Guest, Vendor, Driver, and Vehicle suggestions use existing
tenant-scoped booking lookup endpoints. Guest selection fills contact, email,
company, entity, and identity fields. Company selection fills company ID and
entity. Pickup geocoding reuses the existing location service. Repeat lookup
reads only a booking in the authenticated tenant and creates no booking by
itself.

## Commercial Authority

The workspace requests a rate preview from the existing server-side rate-card
function. It never calculates price, tax, discount, or total in JavaScript.
Final creation remains authoritative in the existing backend flow.

The repository currently provides only the base `customer_rate(company_id,
vehicle_type)` lookup. No unified tax/GST/discount/total calculator exists in
the booking creation path, so the workspace labels those values as calculated
during confirmation instead of fabricating numbers.

## Security

All lookup routes use the existing authentication, module permission, corporate
portal, vendor portal, and tenant rules. Duplicate detection is tenant-scoped.
Client IDs, prices, mode, late-entry reason, and allocation values remain
subject to existing server-side validation.

Normal creation, duplicate detection, repeat lookup, and rate preview require
Booking module access and `_can_modify_booking`. Internal RentaGO users retain
their existing broad operator scope; external users require tenant membership.
Late entry additionally requires internal RentaGO identity and full Booking
module access.

## Late Entry

Late mode reveals actual pickup/drop timing, Vendor, Driver, Vehicle, and
mandatory reason fields. The existing Phase 2 server route assigns booking
punch timestamps and preserves actual trip timestamps. No GPS session is
created by the workspace.
