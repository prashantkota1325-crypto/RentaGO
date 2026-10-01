# Active Late Entry Security

- Creation remains restricted to internal RentaGO users with full Booking
  access.
- Vendor, Driver, Vehicle, tenant, active-state, and historical compliance
  checks remain in the late-entry route.
- Driver start/end actions use existing Driver assignment checks.
- Guest cannot start an Active Late Entry; Driver Mobile is the start actor.
- Historical post-trip rows remain blocked from start, end, live tracking, and
  SOS actions.
- Active late creation does not create a GPS session. Tracking begins only
  after Driver start through the existing tracking path.
- Audit records preserve late-entry type, reason, booking ID, and actor.

Physical Android lock-screen behavior, real-device GPS continuity, and server
restart/offline recovery were not verified in this phase.
