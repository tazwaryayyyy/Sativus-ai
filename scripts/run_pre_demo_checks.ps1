$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root "backend/venv/Scripts/python.exe"

if (!(Test-Path $python)) {
    throw "Python venv not found at $python"
}

Write-Host "[1/4] Health check"
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8080/health" -Method Get -TimeoutSec 5
    Write-Host "Health: $($health.ok)"
}
catch {
    Write-Host "Health endpoint unreachable. Start server first:" -ForegroundColor Yellow
    Write-Host "uvicorn backend.main:app --host 0.0.0.0 --port 8080" -ForegroundColor Yellow
    exit 1
}

Write-Host "[2/4] REST smoke test"
& $python "$root/scripts/smoke_test.py"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[3/4] Live stress test"
if ($env:SATIVUS_ENABLE_LIVE_CHECKS -eq "true") {
    $env:SATIVUS_LIVE_TOTAL = "20"
    $env:SATIVUS_LIVE_CONCURRENCY = "5"
    & $python "$root/scripts/live_stress_test.py"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
else {
    Write-Host "Skipped. Set SATIVUS_ENABLE_LIVE_CHECKS=true to run live scaffold checks." -ForegroundColor Yellow
}

Write-Host "[4/4] Metrics snapshot"
$metrics = Invoke-RestMethod -Uri "http://localhost:8080/metrics" -Method Get -TimeoutSec 10
$metrics | ConvertTo-Json -Depth 5

Write-Host "Pre-demo checks passed." -ForegroundColor Green
