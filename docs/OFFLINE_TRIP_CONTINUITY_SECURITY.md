# Offline Trip Continuity Security

Continuity creation and Booking linking require internal RentaGO Booking
authorization. Trip Continuity ID and RTT reference are never credentials.
Existing Driver Mobile, tenant, tracking-token, and session checks remain
authoritative. No anonymous offline Driver access or plaintext offline password
was introduced.

Offline Driver authorization is a blocker for enabling emergency creation from
the Flutter client.
