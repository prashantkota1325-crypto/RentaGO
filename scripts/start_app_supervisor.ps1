# Keeps the local RentaGO application available for the named Cloudflare tunnel.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = "C:\Users\Prashant Kota\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }
$logDir = Join-Path $env:TEMP "rentago-app"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
while ($true) {
    $p = Start-Process -FilePath $py -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000") -WorkingDirectory $root -RedirectStandardOutput (Join-Path $logDir "app.out.log") -RedirectStandardError (Join-Path $logDir "app.err.log") -WindowStyle Hidden -PassThru
    $p.WaitForExit()
    Start-Sleep -Seconds 5
}
