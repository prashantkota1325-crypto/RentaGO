# RentaGO PC/Server Replacement Runbook

## Current Recovery Position

RentaGO currently runs on one Windows host with Oracle XE 21c and a named Cloudflare Tunnel. The encrypted Oracle database backup has been verified and a controlled restore test has passed.

Current public URL:

```text
https://app.rentago.co.in
```

## Required Recovery Materials

Keep these in separate secure locations:

- Private copy of the RentaGO source directory.
- Latest encrypted Oracle backup archive from `RentaGO_Backups`.
- Uploaded files under `app/uploads`.
- A secure copy of required `.env` values, especially database, SMTP, maps, session secret, and provider credentials.
- Cloudflare tunnel credentials and config:
  - `config.yml`
  - tunnel JSON credentials file
- Oracle XE database passwords.
- 7-Zip and Cloudflare account recovery information.

Do not commit `.env`, Cloudflare JSON credentials, passwords, or unencrypted database dumps.

## Prepare the New PC

Install:

1. Python 3.12.
2. Oracle XE 21c and SQL*Plus/Data Pump tools.
3. 7-Zip.
4. `cloudflared`.

Copy the RentaGO source directory to the new PC and create `.env` from `.env.example` using the secure production values.

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Restore Oracle

1. Start Oracle XE and create/open service `XEPDB1`.
2. Confirm the Oracle `DATA_PUMP_DIR` path.
3. Copy the encrypted backup archive to the new PC.
4. Extract/restore it using the guarded restore procedure:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore_database.ps1 `
  -Archive "C:\Path\RentaGO_YYYYMMDD_HHMMSS.7z" `
  -ConfirmRestore
```

5. Run additive migrations:

```powershell
python .\scripts\migrate.py
```

6. Copy uploaded files into the new `app\uploads` directory.

## Restore Permanent Access

Copy the named tunnel configuration and credentials to the Cloudflare service profile, then install/start the service as Administrator. The tunnel must point to:

```text
http://127.0.0.1:8000
```

The DNS hostname remains:

```text
app.rentago.co.in
```

Do not create a new tunnel unless the existing credentials are unavailable.

## Start RentaGO

Install the application startup task:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_app_start_task.ps1
```

Install the backup and health tasks:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_recovery_tasks.ps1
```

Start the application supervisor and Cloudflare service, then verify:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health
Get-Service cloudflared
Invoke-WebRequest https://app.rentago.co.in/health
```

Expected health response:

```json
{"status":"ok","database":"ok"}
```

## Recovery Validation

Test all of the following before redirecting users:

- Super Admin login and MFA.
- Tenant and membership access.
- Booking list/detail.
- Guest/Driver mobile login.
- GPS tracking.
- Trip lifecycle.
- Invoice and payment records.
- Vendor billing.
- SLA Dashboard and workers.
- Notification queue.
- Uploaded invoice documents.
- Permanent public URL.

## Current Limitations

- Oracle backup archives are automated and encrypted, but uploaded files require a separate backup process.
- SMTP, WhatsApp provider delivery, and payment gateway production verification must be completed separately.
- The local Windows PC remains a single-host availability risk until cloud deployment is completed.
- RPO target is currently approximately 24 hours; RTO target is 2-4 hours after a tested restore.
