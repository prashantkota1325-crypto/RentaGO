# Late/Post-Trip Audit Model

Late entry is represented by `bookings.is_late_entry = 'Y'` and requires:

- `late_entry_reason`
- `late_entry_entered_by`
- `late_entry_entered_at`
- `booking_punched_at`

The actual service event remains in `trips.actual_start_dt` and `trips.actual_end_dt`; these are not replaced with the entry timestamp.

The existing audit log receives `Late/Post-Trip Booking Entry` with the created booking and trip identifiers. Mobile signatures receive `Guest Mobile` or `Driver Mobile` in their respective `*_signature_source` columns plus timestamp and operator columns.

Late-entry access is restricted server-side to internal RentaGO users with Booking module access. Guest and Driver mobile sessions can access a late completed trip only when assignment and tenant checks pass. Their post-trip controls exclude GPS, trip start, trip end, and SOS actions; allowed actions are feedback, safety contact, and signatures according to role.

Driver Mobile participant feedback is audited with the Driver user, booking, and
server timestamp. Historical post-trip state is enforced in both the mobile
feedback endpoint and live-trip action routes.
