# RentaGO Production Readiness Freeze

Environment: LAB/source only

Production URL: `https://app.rentago.co.in`

Production touched: **NO**

## Frozen Components

The following validated components are frozen for production-readiness work:

- Locked-screen Live GPS
- `RentaGoGpsService.kt`
- GPS callback watchdog
- Persistent GPS queue
- ACK-safe GPS upload
- GPS sequence handling
- GPS Oracle persistence
- GPS latest-position handling
- Universal Access
- Token-only login
- Secure Access Token validation
- Guest Trip Portal
- Guest 8 Tools
- Share Live Location
- Driver Trip Portal
- Driver Availability
- Activate IDEAL NOW
- Eligible Bookings
- Deactivate IDEAL NOW
- P-256 trusted-device validation
- Admin routing
- Vendor routing
- RentaGO routing
- Token expiry, revocation, and replay protection
- Existing validated RBAC and security logic

## Current Evidence

- Guest Universal Access physical LAB flow passed.
- Driver Universal Access physical LAB flow passed.
- Guest locked-screen GPS passed with callbacks, HTTP 200 uploads, ACK removal, Oracle persistence, watchdog recovery, and post-unlock recovery.
- Driver P-256 trusted-device validation passed in LAB.
- Guest and Driver Trip Portal routing passed in LAB.
- Admin, Vendor, and RentaGO dashboard routing passed in LAB.
- Guest token-only `/access` flow passed in LAB.
- Existing `/access/<secure-token>` compatibility passed.
- Token replay, expiry, revocation, malformed, tampered, and wrong-identity rejection checks passed.

## Delivery Policy

### WhatsApp

WhatsApp Business API integration is deferred.

```text
Guest WhatsApp: NOT CONFIGURED
Driver WhatsApp: NOT CONFIGURED
```

LAB uses manual `wa.me` outbox links. No fake provider acceptance or delivery confirmation is generated.

### Email

SMTP acceptance is reported as:

```text
SUBMITTED
```

The system does not claim `DELIVERED` without provider delivery, bounce, or webhook confirmation.

## Deployment Separation

- LAB source and LAB Oracle are the only environment used for this work.
- Production database, authentication, GPS data, DNS, App Links, signing keys, and messaging configuration were not modified.
- Production deployment was not performed.
- Production release signing identity, `assetlinks.json`, and Play/MDM distribution remain separate release dependencies.

## Freeze Result

```text
Production touched: NO
WhatsApp configured: NO
Core PASS modules modified: NO
Regression: PASS (84 tests, 0 failures, 9 skipped)
```
