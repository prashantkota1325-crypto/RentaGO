# RentaGO Secure Access Delivery Forensic Report

Environment: LAB only
Booking examined: `IN-900020`

## Result

- Token generation: PASS
- Step 3 notification trigger: PASS
- Guest Universal Access token persistence: PASS
- Driver Universal Access token persistence: PASS
- Guest WhatsApp: NOT CONFIGURED
- Driver WhatsApp: NOT CONFIGURED
- Guest Email submission: PASS
- Guest Email delivery: NOT CONFIRMED
- Production touched: NO

## Pipeline

Step 3 calls `notify.notify_step3()` before the booking transaction commits. The composer queues the normal Step 3 notifications and then creates role-bound Universal Access tokens:

- Guest: Email + WhatsApp outbox rows
- Driver: WhatsApp outbox row

For `IN-900020`, both token rows exist and are ACTIVE. The Guest identity is bound to the active `IND-00994` Guest account and the Driver identity is bound to the assigned Driver record.

## WhatsApp

The current LAB configuration reports:

```text
configured: false
mode: manual wa.me links
```

There is no WhatsApp API endpoint, authentication credential, sender, template, provider response, or delivery webhook configured. The worker intentionally marks WhatsApp notifications `Manual` with the stored `wa.me` action link. No automatic WhatsApp delivery is claimed.

Required production configuration is provider-specific and must include the provider endpoint, access credential, sender/phone-number ID, approved template/content policy, and delivery-status webhook. No provider was invented or added in this phase.

## Email

LAB email configuration is present and SMTP DNS resolves. The worker connects using the configured host, port, and SSL/STARTTLS mode and calls `send_message()`.

The existing implementation did not persist a provider Message-ID, bounce event, delivery webhook, or inbox confirmation. Therefore the previous `Sent` state only proved SMTP submission. Future worker writes use `Submitted` for SMTP acceptance; `Delivered` is not claimed.

Required delivery hardening for a future provider-backed implementation is Message-ID persistence, bounce/complaint processing, and provider delivery-status webhook handling.

## Recipient Data

The LAB booking contains Guest email/mobile and Driver mobile values. Recipient values were used to create the outbox rows; secrets and raw tokens are intentionally omitted from this report.

## Security

- Raw Secure Access tokens are not written to normal application logs.
- Guest and Driver tokens remain role/booking/tenant bound.
- WhatsApp/email delivery failures do not weaken token validation.
- Existing `/access` token-only login and Driver P-256 validation remain unchanged.
- GPS, queue, ACK, watchdog, and Oracle persistence code were not modified.
