# RentaGO Year-1 Privacy Technical Controls

## Scope

This document records technical controls for operating RentaGO as a professional car-rental company during Year 1. It is not a legal compliance certification and does not replace CA, CS, lawyer, transport consultant, or customer-contract review.

## Implemented Technical Controls

- HTTPS through the named Cloudflare Tunnel.
- Signed secure sessions and database-backed session invalidation.
- Password hashing for new passwords.
- Role/module authorization and booking-level visibility checks.
- Guest, Driver, Vendor, Corporate, and RentaGO access separation.
- Vendor masking of guest contact/email in Vendor views.
- RentaGO-only planned-route and internal operational views.
- Server-side booking, invoice, payment, file, and report authorization checks in implemented routes.
- File extension and size validation for invoice expense uploads.
- Environment-based SMTP, database, maps, and tunnel configuration.
- Audit logging for account, booking, payment, SLA, policy, approval, exception, escalation, and tenant actions.
- Encrypted Oracle backup archives.
- Database restore drill into temporary schemas.

## Year-1 Pending Technical Controls

- Complete CSRF protection for all cookie-authenticated state-changing forms.
- Complete cross-corporate, cross-vendor, cross-driver, file, report, and export authorization test matrix.
- General API rate limiting beyond mobile PIN attempts.
- Payment gateway webhook signature verification and duplicate callback tests.
- Production SMTP delivery and WhatsApp provider verification.
- Durable off-server backup of uploaded files.
- Cloud-hosted high-availability deployment.

## Data Minimization

- Guest and Corporate users do not receive Vendor contact details in restricted views.
- Vendor users do not receive Guest phone/email or client invoice financial values.
- Driver users receive only assigned/current operational trip information.
- RentaGO internal users receive operational access according to role/module permissions.
- Do not place passwords, OTPs, API keys, card data, CVV, or provider secrets in logs.

## External Action Required

- **EXTERNAL ACTION REQUIRED:** Legal review of Privacy Policy, Terms & Conditions, Cancellation Policy, Refund Policy, data retention, and customer/vendor contracts.
- **EXTERNAL ACTION REQUIRED:** CA/CS review of GST, invoices, credit notes, vendor bills, and payment/refund accounting.
- **EXTERNAL ACTION REQUIRED:** Transport consultant review of vehicle/driver compliance obligations.
- **EXTERNAL ACTION REQUIRED:** Provider verification for SMTP, WhatsApp, SMS, payment gateway, and webhook credentials.
