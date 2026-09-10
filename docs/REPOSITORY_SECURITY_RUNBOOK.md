# RentaGO Repository Security Runbook

## Ownership Target

The authoritative private repository must be owned by an account controlled by RentaGO Technologies Pvt. Ltd., not by an individual developer, AI tool, contractor, or hosting provider.

## Human Verification Steps

Run on a machine with Git installed:

```powershell
```

Verify:

- Repository is private.
- Organization/account is controlled by RentaGO.
- At least two RentaGO-controlled administrators exist.
- MFA is enabled on the repository account.
- Developers use individual accounts.
- No shared Git credentials exist.
- Branch protection and review rules are enabled for the production branch.
- Deploy keys/tokens are scoped and rotatable.

## Secret History Review

Before considering the repository protected, scan current files and Git history using an approved secret scanner. If a real credential appears anywhere in history, rotate it at the provider first; deleting the latest file is not sufficient.

Do not paste secret findings into tickets, chat, or audit reports. Record only the secret category, file/commit location, rotation status, and owner.

## Protected Files

The repository must not contain:

- `.env` or `.env.*` except `.env.example`.
- Database passwords.
- SMTP passwords.
- Maps/API keys.
- Payment credentials.
- WhatsApp/SMS credentials.
- Cloudflare credentials JSON.
- Private keys or certificates.
- Cookies and runtime logs.
- Production database dumps.
