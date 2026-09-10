# Install daily backup and frequent health-check tasks for the current Windows user.
# Run this script from an elevated PowerShell window.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backup = Join-Path $root "scripts\backup_database.ps1"
$fileBackup = Join-Path $root "scripts\backup_runtime_files.ps1"
$monitor = Join-Path $root "scripts\monitor_rentago.ps1"
$pwsh = (Get-Command powershell.exe).Source
$backupAction = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$backup`""
$fileBackupAction = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$fileBackup`""
$monitorAction = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$monitor`""
$backupTrigger = New-ScheduledTaskTrigger -Daily -At 2:00AM
$monitorTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName "RentaGO Daily Encrypted Backup" -Action $backupAction -Trigger $backupTrigger -Principal $principal -Description "Daily encrypted Oracle Data Pump backup for RentaGO" -Force | Out-Null
Register-ScheduledTask -TaskName "RentaGO Uploaded Files Backup" -Action $fileBackupAction -Trigger $backupTrigger -Principal $principal -Description "Daily encrypted backup of RentaGO uploaded documents" -Force | Out-Null
Register-ScheduledTask -TaskName "RentaGO Health Monitor" -Action $monitorAction -Trigger $monitorTrigger -Principal $principal -Description "Checks RentaGO health endpoint every five minutes" -Force | Out-Null
Write-Host "Recovery tasks installed."
