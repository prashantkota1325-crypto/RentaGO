# Production Email Verification

## Current Configuration

- SMTP host: `smtpout.secureserver.net`
- Port: `465`
- Security: SSL
- Sender mailbox: configured through `RENTAGO_SMTP_USER`
- Sender display name: `RENTAGO_SMTP_FROM_NAME`
- Credentials: `.env` only; never commit or log them.

## Verification Procedure

1. Confirm the mailbox password in GoDaddy Webmail.
2. Confirm the sender mailbox can send to itself and to a separate Gmail/Outlook test address.
3. Log in to RentaGO and trigger an MFA email.
4. Confirm receipt, sender display name, subject, OTP expiry, and no duplicate messages.
5. Trigger a Step 1 notification and verify the outbox status changes from `Queued` to `Sent`.
6. Test an invalid SMTP password in staging only and confirm retry/failure status without secrets in logs.
7. Restore the correct credential and manually retry the notification.

## Current Status

SMTP connection/authentication has been tested. Final mailbox delivery and spam/quarantine behavior remain provider-side verification actions.
