# Lightweight monitor for Task Scheduler or a Windows service wrapper.
$health = "http://127.0.0.1:8000/health"
try {
    $r = Invoke-WebRequest -Uri $health -UseBasicParsing -TimeoutSec 10
    if ($r.StatusCode -ne 200) { exit 2 }
    exit 0
} catch {
    exit 1
}
