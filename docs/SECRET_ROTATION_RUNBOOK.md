# RentaGO Secret Rotation Runbook

## Verification Status

Historical secret exposure is **NOT VERIFIED — GIT UNAVAILABLE IN CURRENT ENVIRONMENT**.

Any rotation must be performed manually by an authorized RentaGO owner. No production credentials were changed during this audit.

## Rotate When Required

Rotate immediately if a secret is:

- Committed to Git history.
- Included in a shared archive.
- Printed in logs.
- Sent to an unapproved developer or tool.
- Stored on a lost/stolen device.
- Exposed by a provider alert.

## Rotation Order

1. Database application user password.
2. Database admin password.
3. `RENTAGO_SECRET` session/signing secret.
4. SMTP mailbox password.
5. Maps/API keys.
6. Payment gateway keys.
7. WhatsApp/SMS provider credentials.
8. Cloudflare Tunnel credentials.
9. Backup encryption/recovery credentials where applicable.

## After Rotation

1. Update deployment environment configuration securely.
2. Restart only the affected service.
3. Test login, MFA, database health, notifications, maps, backups, and tunnel access.
4. Revoke the old credential at the provider.
5. Record the rotation date and responsible RentaGO owner without recording the value.
