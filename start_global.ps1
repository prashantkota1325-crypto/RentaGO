# RentaGO Web - GLOBAL launcher.
# Starts the app server (0.0.0.0:8000) + a Cloudflare quick tunnel and prints
# a public https://...trycloudflare.com link that works anywhere in the world.
#
# Notes:
# - The quick-tunnel URL is random and CHANGES each time you restart this
#   script (a permanent URL is possible later with a free Cloudflare account).
# - This PC must stay on; the Oracle database runs on this machine.
# - Multi-login policy applies through the tunnel too: different users can be
#   logged in at the same time from anywhere; the same user logging in on a new
#   device logs out the previous one (within ~30 seconds).
$ErrorActionPreference = "Stop"

$py = "C:\Users\Prashant Kota\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$cf = "$env:LOCALAPPDATA\RentaGO\cloudflared.exe"
if (-not (Test-Path $cf)) {
    Write-Host "cloudflared not found at $cf - downloading it first..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path (Split-Path $cf) -Force | Out-Null
    curl.exe -L -sS -o $cf "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
}

# 1) App server on all interfaces (unless one is already listening on 8000)
$listening = (netstat -ano | Select-String ":8000\s.*LISTENING") -ne $null
if (-not $listening) {
    Start-Process $py -ArgumentList "-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000" -WorkingDirectory $PSScriptRoot
    Write-Host "App server starting on 0.0.0.0:8000 ..." -ForegroundColor Yellow
    $appDeadline = (Get-Date).AddSeconds(45)
    do {
        Start-Sleep -Seconds 2
        try { $ready = Invoke-WebRequest -Uri "http://127.0.0.1:8000/auth/login" -UseBasicParsing -TimeoutSec 3 } catch { $ready = $null }
    } while (-not $ready -and (Get-Date) -lt $appDeadline)
    if (-not $ready) { throw "RentaGO did not become ready on port 8000." }
} else {
    Write-Host "App server already running on port 8000." -ForegroundColor DarkGray
}

# 2) Cloudflare quick tunnel -> public https link
$tunnelLog = "$env:TEMP\rentago_tunnel.log"
Start-Process $cf -ArgumentList "tunnel","--url","http://localhost:8000","--no-autoupdate" -RedirectStandardError $tunnelLog -WindowStyle Hidden
$deadline = (Get-Date).AddSeconds(90)
$found = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    $log = Get-Content $tunnelLog -Raw -ErrorAction SilentlyContinue
    if ($log -match "(https://[a-z0-9-]+\.trycloudflare\.com)") {
        $public = $Matches[1]
        $lan = (Get-NetIPAddress -AddressFamily IPv4 |
                Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
                Select-Object -First 1).IPAddress
        Write-Host ""
        Write-Host "==================================================" -ForegroundColor Green
        Write-Host " RENTAGO IS LIVE ANYWHERE IN THE WORLD AT:" -ForegroundColor Green
        Write-Host " $public" -ForegroundColor Cyan
        Write-Host "==================================================" -ForegroundColor Green
        Write-Host " On your local network (PCs/phones/tablets on WiFi):"
        Write-Host "   http://${lan}:8000"
         Write-Host " Log in with your approved account. Email OTP is required where configured."
        Write-Host ""
        Write-Host " Keep this window's tunnel running. Ctrl+C stops the tunnel."
        $found = $true
        break
    }
}
if (-not $found) {
    Write-Host "Tunnel URL not detected in time - check $tunnelLog" -ForegroundColor Red
}
