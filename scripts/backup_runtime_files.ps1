# Encrypted backup for uploaded documents and runtime file artifacts.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"
function EnvValue($key) {
    $line = Get-Content -LiteralPath $envFile | Where-Object { $_ -match "^$key=" } | Select-Object -Last 1
    return (($line -replace "^$key=", "").Trim().Trim('"').Trim("'"))
}
$backupRoot = EnvValue "RENTAGO_BACKUP_DIR"
$dbPassword = EnvValue "RENTAGO_DB_PASSWORD"
$source = Join-Path $root "app\uploads"
$sevenZip = "C:\Program Files\7-Zip\7z.exe"
if (-not (Test-Path -LiteralPath $source)) { Write-Host "No upload directory exists; nothing to back up."; exit 0 }
if (-not (Test-Path -LiteralPath $sevenZip)) { throw "7z.exe not found" }
if (-not $backupRoot -or -not $dbPassword) { throw "Backup destination or encryption key is not configured" }
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$archive = Join-Path $backupRoot "RentaGO_Files_$timestamp.7z"
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
& $sevenZip a -t7z -mhe=on -p"$dbPassword" "$archive" "$source\*" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Runtime file archive creation failed" }
Write-Host "Encrypted runtime file backup created: $archive"
