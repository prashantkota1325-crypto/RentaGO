# Trusted Device Offline Authorization

The LAB backend has the finite `TRUSTED_OFFLINE_AUTHORIZATIONS` foundation.
It binds authorization to device ID, device key ID, Driver, Vendor, tenant,
authorization epoch, issue time, expiry, and status.

Issuing a lease does not enable offline trip operations. Phase 2.3B must add
the signed lease client storage and offline operational policy only after
physical/device verification and the full event protocol are approved.
