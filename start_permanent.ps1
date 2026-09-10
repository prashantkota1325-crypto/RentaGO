# RentaGO supervised local/global launcher.
# Keeps one Uvicorn process and one Cloudflare tunnel running. Press Ctrl+C to stop.
$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$py = "C:\Users\Prashant Kota\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path -LiteralPath $py)) { $py = "python" }
$cf = Join-Path $env:LOCALAPPDATA "RentaGO\cloudflared.exe"
if (-not (Test-Path -LiteralPath $cf)) {
    throw "cloudflared.exe not found. Run start_global.ps1 once to install it."
}

$state = Join-Path $env:TEMP "rentago-supervisor"
New-Item -ItemType Directory -Path $state -Force | Out-Null
$appOut = Join-Path $state "app.out.log"
$appErr = Join-Path $state "app.err.log"
$tunnelLog = Join-Path $state "tunnel.log"
$urlFile = Join-Path $state "current_global_url.txt"
$appProcess = $null
$tunnelProcess = $null

function Start-RentaGOApp {
    if ($script:appProcess -and -not $script:appProcess.HasExited) { return }
    $script:appProcess = Start-Process -FilePath $py -ArgumentList @(
        "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"
    ) -WorkingDirectory $root -RedirectStandardOutput $appOut -RedirectStandardError $appErr -WindowStyle Hidden -PassThru
    Write-Host "RentaGO process started: $($script:appProcess.Id)" -ForegroundColor Yellow
}

function Test-RentaGOReady {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/auth/login" -UseBasicParsing -TimeoutSec 3
        return $r.StatusCode -eq 200
    } catch { return $false }
}

function Start-RentaGOTunnel {
    if ($script:tunnelProcess -and -not $script:tunnelProcess.HasExited) { return }
    Remove-Item -LiteralPath $tunnelLog -Force -ErrorAction SilentlyContinue
    $script:tunnelProcess = Start-Process -FilePath $cf -ArgumentList @(
        "tunnel", "--url", "http://127.0.0.1:8000", "--no-autoupdate"
    ) -RedirectStandardError $tunnelLog -WindowStyle Hidden -PassThru
    Write-Host "Cloudflare tunnel started: $($script:tunnelProcess.Id)" -ForegroundColor Yellow
}

try {
    while ($true) {
        Start-RentaGOApp
        $deadline = (Get-Date).AddSeconds(45)
        while (-not (Test-RentaGOReady) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
        if (-not (Test-RentaGOReady)) {
            Write-Host "RentaGO is not ready; restarting app process." -ForegroundColor Red
            if ($appProcess -and -not $appProcess.HasExited) { Stop-Process -Id $appProcess.Id -Force }
            Start-Sleep -Seconds 3
            continue
        }
        Start-RentaGOTunnel
        Start-Sleep -Seconds 8
        if (Test-Path -LiteralPath $tunnelLog) {
            $log = Get-Content -LiteralPath $tunnelLog -Raw -ErrorAction SilentlyContinue
            $matches = [regex]::Matches($log, "https://[a-z0-9-]+\.trycloudflare\.com")
            if ($matches.Count -gt 0) {
                $url = $matches[$matches.Count - 1].Value
                Set-Content -LiteralPath $urlFile -Value "$url/auth/login" -Encoding ASCII
                Write-Host "Global login: $url/auth/login" -ForegroundColor Green
            }
        }
        Start-Sleep -Seconds 10
        if ($appProcess.HasExited) { Write-Host "RentaGO stopped; supervisor will restart it." -ForegroundColor Red }
        if ($tunnelProcess.HasExited) { Write-Host "Tunnel stopped; supervisor will restart it." -ForegroundColor Red }
    }
} finally {
    if ($tunnelProcess -and -not $tunnelProcess.HasExited) { Stop-Process -Id $tunnelProcess.Id -Force }
    if ($appProcess -and -not $appProcess.HasExited) { Stop-Process -Id $appProcess.Id -Force }
}
