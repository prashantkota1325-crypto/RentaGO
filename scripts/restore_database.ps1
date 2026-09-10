# Guarded RentaGO Oracle restore. This is intentionally never destructive by default.
param(
    [Parameter(Mandatory=$true)][string]$Archive,
    [switch]$ConfirmRestore
)
$ErrorActionPreference = "Stop"
if (-not $ConfirmRestore) { throw "Restore is destructive. Re-run with -ConfirmRestore after taking a safety backup." }
if (-not (Test-Path -LiteralPath $Archive)) { throw "Backup archive not found" }
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"
function EnvValue($key) {
    $line = Get-Content -LiteralPath $envFile | Where-Object { $_ -match "^$key=" } | Select-Object -Last 1
    return (($line -replace "^$key=", "").Trim().Trim('"').Trim("'"))
}
$dbPassword = EnvValue "RENTAGO_DB_PASSWORD"
$oracleDumpDir = EnvValue "RENTAGO_ORACLE_DUMP_DIR"
$sevenZip = "C:\Program Files\7-Zip\7z.exe"
$sqlplus = "C:\oraclexe\dbhomeXE\bin\sqlplus.exe"
$impdp = "C:\oraclexe\dbhomeXE\bin\impdp.exe"
foreach ($tool in @($sevenZip, $sqlplus, $impdp)) { if (-not (Test-Path -LiteralPath $tool)) { throw "Required Oracle/7-Zip tool not found: $tool" } }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$temp = Join-Path $env:TEMP "rentago_restore_$stamp"
$parfile = Join-Path $env:TEMP "rentago_restore_$stamp.par"
$dump = Join-Path $temp "rentago_*.dmp"
$admin = "RGRESTORE_TEST"
$adminPassword = "RestoreDba2026X"
$target = "RENTAGO_RESTORE_TEST"
$passed = $false
New-Item -ItemType Directory -Path $temp -Force | Out-Null
try {
    & $sevenZip x -y -p"$dbPassword" "-o$temp" $Archive | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Encrypted archive extraction failed" }
    $dumpPath = Get-ChildItem -LiteralPath $temp -Filter "*.dmp" | Select-Object -First 1
    if (-not $dumpPath) { throw "No Oracle dump found in archive" }
    if (-not (Test-Path -LiteralPath $oracleDumpDir)) { throw "Oracle Data Pump directory is unavailable" }
    Copy-Item -LiteralPath $dumpPath.FullName -Destination (Join-Path $oracleDumpDir $dumpPath.Name) -Force
    $setup = @"
ALTER SESSION SET CONTAINER = XEPDB1;
BEGIN EXECUTE IMMEDIATE 'DROP USER $admin CASCADE'; EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1918 THEN RAISE; END IF; END;
/
BEGIN EXECUTE IMMEDIATE 'DROP USER $target CASCADE'; EXCEPTION WHEN OTHERS THEN IF SQLCODE != -1918 THEN RAISE; END IF; END;
/
CREATE USER $admin IDENTIFIED BY "$adminPassword";
GRANT CREATE SESSION, RESOURCE, DATAPUMP_IMP_FULL_DATABASE TO $admin;
ALTER USER $admin QUOTA UNLIMITED ON USERS;
CREATE USER $target IDENTIFIED BY "Restore_Test_Only_2026";
GRANT CREATE SESSION, RESOURCE TO $target;
ALTER USER $target QUOTA UNLIMITED ON USERS;
SELECT username FROM dba_users WHERE username IN ('$admin', '$target');
EXIT;
"@
    $setupOutput = ($setup | & $sqlplus "/ as sysdba") -join "`n"
    if ($LASTEXITCODE -ne 0) { throw "Temporary restore users could not be created" }
    if ($setupOutput -notmatch $target) { throw "Temporary restore target schema was not created" }
    @(
        "userid=$admin/$adminPassword@XEPDB1"
        "directory=DATA_PUMP_DIR"
        "dumpfile=$($dumpPath.Name)"
        "logfile=rentago_restore_$stamp.log"
        "remap_schema=RENTAGO:$target"
        "table_exists_action=REPLACE"
        "transform=OID:N"
        "exclude=IDENTITY_COLUMN"
    ) | Set-Content -LiteralPath $parfile -Encoding ASCII
    $arg = 'PARFILE="' + $parfile + '"'
    $result = Start-Process -FilePath $impdp -ArgumentList $arg -RedirectStandardOutput (Join-Path $temp "import.log") -RedirectStandardError (Join-Path $temp "import.error.log") -Wait -PassThru -NoNewWindow
    if ($result.ExitCode -ne 0) { throw "Controlled Data Pump import failed. See $temp" }
    $check = @"
ALTER SESSION SET CONTAINER = XEPDB1;
SET HEADING OFF FEEDBACK OFF PAGESIZE 0;
SELECT 'USERS=' || COUNT(*) FROM $target.USERS;
SELECT 'BOOKINGS=' || COUNT(*) FROM $target.BOOKINGS;
SELECT 'SLA_DEFINITIONS=' || COUNT(*) FROM $target.SLA_DEFINITIONS;
EXIT;
"@
    $checkResult = ($check | & $sqlplus "/ as sysdba") -join "`n"
    if ($LASTEXITCODE -ne 0 -or $checkResult -notmatch 'USERS=') { throw "Restore verification query failed" }
    Write-Host $checkResult
    Write-Host "CONTROLLED_RESTORE_TEST_PASSED"
    $passed = $true
} finally {
    $cleanup = @"
ALTER SESSION SET CONTAINER = XEPDB1;
DROP USER $target CASCADE;
DROP USER $admin CASCADE;
EXIT;
"@
    $cleanup | & $sqlplus "/ as sysdba" | Out-Null
    Remove-Item -LiteralPath $parfile -Force -ErrorAction SilentlyContinue
    if ($passed) { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue }
    if ($dumpPath) { Remove-Item -LiteralPath (Join-Path $oracleDumpDir $dumpPath.Name) -Force -ErrorAction SilentlyContinue }
}
