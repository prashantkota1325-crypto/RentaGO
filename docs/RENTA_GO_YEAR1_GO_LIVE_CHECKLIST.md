# RentaGO Year-1 Go-Live Checklist

Status values: `PASS`, `FAIL`, `PENDING`, `EXTERNAL ACTION`.

## Company and Legal

| Item | Status | Evidence/Owner |
|---|---|---|
| Company identity and ownership verified | EXTERNAL ACTION | Company/CS |
| GST/tax configuration verified | EXTERNAL ACTION | CA |
| Customer contracts approved | EXTERNAL ACTION | Lawyer/CS |
| Vendor agreements approved | EXTERNAL ACTION | Lawyer/CS |
| Privacy Policy published | EXTERNAL ACTION | Lawyer |
| Terms and Conditions published | EXTERNAL ACTION | Lawyer |
| Cancellation and Refund Policy approved | EXTERNAL ACTION | Lawyer/CA |

## Operations

| Item | Status | Evidence/Owner |
|---|---|---|
| Corporate booking lifecycle | PASS | Existing booking workflow |
| Individual booking lifecycle | PASS | Existing booking workflow |
| Guest booking lifecycle | PASS | Existing booking workflow |
| Vendor allocation | PASS | Existing Step 2 workflow |
| Driver allocation | PASS | Existing Step 3 workflow |
| Vehicle allocation | PASS | Existing fleet workflow |
| Trip start/end | PASS | Guest/Driver lifecycle |
| GPS and actual driver path | PASS | GPS trail and 120-second mobile reporting |
| Multi-stop planned route | PASS | Ordered route payload and map |
| Vendor-owned Driver/Vehicle maintenance | PASS | Vendor Resources |
| Vendor → RentaGO invoices | PASS | Isolated vendor billing |
| Client invoice/payment workflow | PASS | Existing invoice/payment modules |
| Feedback and safety incidents | PASS | Existing feedback workflow |

## Security

| Item | Status | Evidence/Owner |
|---|---|---|
| HTTPS active | PASS | Cloudflare named tunnel |
| Password hashing | PASS | `app/security.py` |
| Authentication and sessions | PASS | Signed cookie + `user_sessions` |
| RBAC | PASS | Role/module matrix |
| Server-side object authorization | PENDING | Full matrix testing required |
| Tenant isolation | PENDING | Staged tenant migration in progress |
| CSRF protection | PENDING | Required before broad production use |
| Rate limiting | PENDING | Mobile PIN only; general limits pending |
| Secure file upload/download | PASS | Type/size/path and ownership checks in implemented flow |
| Payment webhook verification | PENDING | Provider integration verification required |

## Backup and Recovery

| Item | Status | Evidence/Owner |
|---|---|---|
| Automated encrypted database backup | PASS | Scheduled Data Pump + AES archive |
| Database restore test | PASS | Temporary-schema restore passed |
| Uploaded-file backup | PENDING | Separate durable file backup required |
| Off-server backup | PENDING | Verify independent cloud/external copy |
| RPO measured | PENDING | Target currently 24 hours |
| RTO measured | PENDING | Target currently 2-4 hours |

## Notifications and Payments

| Item | Status | Evidence/Owner |
|---|---|---|
| Email queue and retry | PASS | Notification outbox worker |
| SMTP delivery verification | PENDING | Mailbox/provider confirmation required |
| WhatsApp provider verification | PENDING | API/templates/provider action required |
| SMS provider verification | PENDING | Provider action required |
| Payment gateway verification | PENDING | Provider/webhook action required |

## Testing

| Item | Status | Evidence/Owner |
|---|---|---|
| Core SLA regression tests | PASS | 8 tests currently pass |
| Full booking-to-payment E2E | PENDING | Run with controlled test accounts |
| Cross-corporate authorization tests | PENDING | Required |
| Cross-vendor authorization tests | PENDING | Required |
| Cross-driver authorization tests | PENDING | Required |
| Concurrency tests | PENDING | Required before multi-worker production |
| Failure-injection tests | PENDING | Required |

## Current Year-1 Decision

```text
GO WITH CONDITIONS
```

The platform can continue controlled Year-1 operational use, but full production approval requires completion of the `PENDING` items and all `EXTERNAL ACTION` items applicable to the operating model. No legal, tax, transport, payment-provider, or messaging-provider item is marked complete by software implementation alone.
