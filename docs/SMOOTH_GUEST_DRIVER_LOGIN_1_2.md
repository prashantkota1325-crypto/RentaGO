# Smooth Guest + Driver Login 1.2

## LAB Status

The smooth login path is implemented without changing the proven GPS engine.

- Step 3 creates role-bound Guest and Driver Universal Access tokens when the corresponding identity records exist.
- Guest delivery policy is Email + WhatsApp outbox.
- Driver delivery policy is WhatsApp outbox only.
- `/access` accepts the Secure Token-only fallback.
- `/access/<secure-token>` remains compatible.
- Guest routes to the existing Guest Trip Portal.
- Driver validates P-256 and opens the existing Driver Trip Portal, including Ideal Now and current-trip tools.
- Existing app handoff and locked-screen GPS remain unchanged.

## Delivery Truth

- LAB WhatsApp is `Manual` because no WhatsApp provider is configured.
- SMTP `Sent` historically meant SMTP submission; future SMTP notifications use `Submitted` because inbox delivery is not confirmed.
- No delivery is called `Delivered` without a provider delivery receipt.
- The LAB APK download endpoint is `/access/download/apk`.

## Known Dependencies

- Guest and Driver identity records must exist and be active before Step 3 can bind tokens.
- Driver devices must be provisioned before P-256 validation.
- Production SMTP/WhatsApp providers, signing, HTTPS, App Links, and Play/MDM distribution remain separate production work.

## GPS

`RentaGoGpsService.kt`, the foreground service, Fused Location Provider, HandlerThread, watchdog, queue, ACK handling, backend tracking APIs, and Oracle persistence were not redesigned or modified for this phase.
