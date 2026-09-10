# RentaGO Backup and Recovery

## Current Protection

- Application code is stored in the project directory and should be copied to a private source repository.
- Oracle data is backed up with `scripts/backup_database.ps1` using Oracle Data Pump.
- Uploaded documents are backed up with `scripts/backup_runtime_files.ps1` as a separate encrypted archive.
- The backup script requires `expdp.exe` and `7z.exe`; the archive is AES-256 encrypted with the database password.
- `/health` checks application and Oracle availability.
- `start_permanent.ps1` supervises the application and quick tunnel processes.

## Backup Procedure

Run from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup_database.ps1
```

Copy encrypted archives to a second location. Recommended retention: daily backups for 30 days, weekly backups for 12 weeks, and monthly backups for 12 months.

Install the Windows tasks from an elevated PowerShell window:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_recovery_tasks.ps1
```

The database and uploaded-file backups run daily at 02:00 and the health monitor runs every five minutes while the Windows user session is active.

Install the application startup supervisor from an elevated PowerShell window:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_app_start_task.ps1
```

Do not commit `.env`, passwords, API keys, cookies, or unencrypted database dumps.

## Restore Procedure

The supplied restore script is deliberately guarded and does not overwrite a database automatically. A restore requires:

1. Confirming the target database and backup timestamp.
2. Taking a safety backup of the target.
3. Reviewing schema/data impact and Data Pump remap options.
4. Running the reviewed Data Pump import.
5. Running `python scripts/migrate.py`.
6. Running application, login, booking, trip, invoice, payment, and report smoke tests.

## Portability to Another PC

1. Install Python 3.12 and Oracle XE/client tools.
2. Copy the application from the private repository/backup.
3. Restore the encrypted Oracle dump to the target database.
4. Create a new `.env` from `.env.example` and populate secrets through a secure channel.
5. Run migrations.
6. Run `start_permanent.ps1`.
7. For fixed global access, install a named Cloudflare Tunnel and point the permanent DNS hostname to `http://127.0.0.1:8000`.

## Recovery Targets

- Target RPO: 24 hours until scheduled cloud/remote backups are enabled.
- Target RTO: 2-4 hours after a tested restore procedure is completed.
- Current quick tunnels are not permanent and cannot be used as the disaster-recovery identity.

## Permanent Cloudflare Tunnel

After the domain is managed by Cloudflare:

```powershell
cloudflared tunnel login
cloudflared tunnel create rentago
cloudflared tunnel route dns rentago app.<YOUR_DOMAIN>
```

Copy `deploy/cloudflared/config.yml.example` to `config.yml`, replace the placeholders, validate it, and install the tunnel as a Windows service. Do not commit the credentials JSON file.
