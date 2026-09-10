# RentaGO Secret Scanning Runbook

## Current Status

Local `.env` presence was identified without exposing values. Git history was not checked.

**NOT VERIFIED — GIT UNAVAILABLE IN CURRENT ENVIRONMENT**

## Manual Action Required

On the RentaGO development computer, install an approved secret scanner and scan:

- Working tree.
- Git history.
- All branches and tags.
- Deployment archives.
- Backup archives where permitted.

Scan categories:

- Database passwords.
- SMTP passwords.
- API keys.
- Payment credentials.
- WhatsApp/SMS credentials.
- Cloudflare credentials.
- Private keys.
- Session/encryption secrets.
- Access tokens.

Never paste secret values into reports, tickets, chat, or AI tools. Record only the category, location, exposure status, rotation status, and owner.

If a production secret appears in Git history:

```text
CRITICAL — SECRET ROTATION REQUIRED
```

Removing the latest file is not sufficient; rotate the provider credential and assess history exposure.
