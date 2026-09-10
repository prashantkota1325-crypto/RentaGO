# RentaGO Oracle backup: Data Pump export + AES-256 7-Zip archive.
# Requires expdp.exe and 7z.exe. Does not delete source database data.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$envFile = Join-Path $root ".env"

if (-not (Test-Path -LiteralPath $envFile)) { throw ".env not found" }
function EnvValue($key) {
    $line = Get-Content -LiteralPath $envFile | Where-Object { $_ -match "^$key=" } | Select-Object -Last 1
    if (-not $line) { return "" }
    return ($line -replace "^$key=", "").Trim().Trim('"').Trim("'")
}
$dbUser = EnvValue "RENTAGO_DB_USER"
$dbPassword = EnvValue "RENTAGO_DB_PASSWORD"
$dbHost = EnvValue "RENTAGO_DB_HOST"
$dbPort = EnvValue "RENTAGO_DB_PORT"
$dbService = EnvValue "RENTAGO_DB_SERVICE"
$oracleDumpDir = EnvValue "RENTAGO_ORACLE_DUMP_DIR"
$backupRoot = EnvValue "RENTAGO_BACKUP_DIR"
if (-not $dbUser -or -not $dbPassword) { throw "Database credentials are not configured" }
if (-not $oracleDumpDir -or -not (Test-Path -LiteralPath $oracleDumpDir)) { throw "RENTAGO_ORACLE_DUMP_DIR must point to the Oracle DATA_PUMP_DIR folder" }
if (-not $backupRoot) { throw "RENTAGO_BACKUP_DIR is not configured" }
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$work = Join-Path $backupRoot $timestamp
$archive = Join-Path $backupRoot "RentaGO_$timestamp.7z"
$expdp = "C:\oraclexe\dbhomeXE\bin\expdp.exe"
if (-not (Test-Path -LiteralPath $expdp)) { $expdp = "expdp.exe" }
$sevenZip = (Get-Command 7z.exe -ErrorAction SilentlyContinue).Source
if (-not $sevenZip -and (Test-Path -LiteralPath "C:\Program Files\7-Zip\7z.exe")) { $sevenZip = "C:\Program Files\7-Zip\7z.exe" }
if (-not $sevenZip) { throw "7z.exe is required for encrypted backup archives" }
New-Item -ItemType Directory -Path $work -Force | Out-Null
$parfile = Join-Path $env:TEMP "rentago_export_$timestamp.par"
$dump = Join-Path $oracleDumpDir "rentago_$timestamp.dmp"
$log = Join-Path $work "export.log"
$errorLog = Join-Path $work "export.error.log"
@(
    "userid=$dbUser/`"$dbPassword`"@XEPDB1"
    "directory=DATA_PUMP_DIR"
    "dumpfile=rentago_$timestamp.dmp"
    "logfile=rentago_$timestamp.log"
    "schemas=$dbUser"
    "exclude=STATISTICS"
) | Set-Content -LiteralPath $parfile -Encoding ASCII
$parArg = 'PARFILE="' + $parfile + '"'
$process = Start-Process -FilePath $expdp -ArgumentList $parArg -RedirectStandardOutput $log -RedirectStandardError $errorLog -Wait -PassThru -NoNewWindow
if ($process.ExitCode -ne 0) { throw "Oracle Data Pump export failed. See $log and $errorLog" }
if (-not (Test-Path -LiteralPath $dump)) { throw "Data Pump completed without a dump file at $dump" }
& $sevenZip a -t7z -mhe=on -p"$dbPassword" "$archive" "$work\*" "$dump" | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Encrypted archive creation failed" }
Remove-Item -LiteralPath $work -Recurse -Force
Remove-Item -LiteralPath $dump -Force
Remove-Item -LiteralPath $parfile -Force -ErrorAction SilentlyContinue
Write-Host "Encrypted backup created: $archive"
