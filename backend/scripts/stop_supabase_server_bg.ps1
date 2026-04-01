$ErrorActionPreference = "Stop"

$projectRoot = "C:\Workspaces\Teamwork\Final\backend"
$pidFile = Join-Path $projectRoot ".tmp_supabase_server\server.pid"

if (-not (Test-Path $pidFile)) {
    Write-Host "[MirrAI] No Supabase test server PID file found." -ForegroundColor Yellow
    return
}

$pid = Get-Content $pidFile | Select-Object -First 1
if (-not $pid) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "[MirrAI] Empty PID file removed." -ForegroundColor Yellow
    return
}

$process = Get-Process -Id $pid -ErrorAction SilentlyContinue
if (-not $process) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    Write-Host "[MirrAI] Process already stopped. PID file removed." -ForegroundColor Yellow
    return
}

Stop-Process -Id $pid -Force
Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
Write-Host "[MirrAI] Supabase test server stopped. PID=$pid" -ForegroundColor Green
