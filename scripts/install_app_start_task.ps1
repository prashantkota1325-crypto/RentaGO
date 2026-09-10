# Run elevated once to start RentaGO automatically when the Windows user logs in.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root "scripts\start_app_supervisor.ps1"
$pwsh = (Get-Command powershell.exe).Source
$action = New-ScheduledTaskAction -Execute $pwsh -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName "RentaGO Application Supervisor" -Action $action -Trigger $trigger -Principal $principal -Description "Starts and supervises the RentaGO application after user login" -Force | Out-Null
Write-Host "RentaGO application startup task installed."
