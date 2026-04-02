$ErrorActionPreference = "Stop"

$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$projectRoot = "C:\Workspaces\Teamwork\Final\backend"
$pythonExe = "C:\Users\Playdata\AppData\Local\miniconda3\envs\mirrai\python.exe"
$logDir = Join-Path $projectRoot ".tmp_supabase_server"
$stdoutLog = Join-Path $logDir "stdout.log"
$stderrLog = Join-Path $logDir "stderr.log"
$pidFile = Join-Path $logDir "server.pid"

Set-Location $projectRoot

if (-not (Test-Path ".\manage.py")) {
    throw "manage.py를 찾을 수 없습니다. 현재 경로: $projectRoot"
}

if (-not (Test-Path $pythonExe)) {
    throw "mirrai python 경로를 찾을 수 없습니다: $pythonExe"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (Test-Path $pidFile) {
    $existingPid = (Get-Content $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($existingPid) {
        $existingProcess = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($existingProcess) {
            Write-Host "[MirrAI] Supabase test server is already running. PID=$existingPid" -ForegroundColor Yellow
            Write-Host "Open http://127.0.0.1:8000/partner/login/"
            return
        }
    }
}

$argumentList = @(
    "manage.py",
    "runserver",
    "127.0.0.1:8000",
    "--noreload"
)

$startInfo = @{
    FilePath = $pythonExe
    ArgumentList = $argumentList
    WorkingDirectory = $projectRoot
    RedirectStandardOutput = $stdoutLog
    RedirectStandardError = $stderrLog
    PassThru = $true
}

$env:SUPABASE_USE_REMOTE_DB = if ([string]::IsNullOrWhiteSpace($env:SUPABASE_USE_REMOTE_DB)) { "False" } else { $env:SUPABASE_USE_REMOTE_DB }
$env:SUPABASE_USE_REMOTE_STORAGE = if ([string]::IsNullOrWhiteSpace($env:SUPABASE_USE_REMOTE_STORAGE)) { "False" } else { $env:SUPABASE_USE_REMOTE_STORAGE }
$env:DEBUG = if ([string]::IsNullOrWhiteSpace($env:DEBUG)) { "True" } else { $env:DEBUG }
$env:MIRRAI_LOCAL_MOCK_RESULTS = if ([string]::IsNullOrWhiteSpace($env:MIRRAI_LOCAL_MOCK_RESULTS)) { "True" } else { $env:MIRRAI_LOCAL_MOCK_RESULTS }
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

& $pythonExe manage.py check | Out-Host

$dbMode = if ($env:SUPABASE_USE_REMOTE_DB -match '^(1|true|yes)$') { "Supabase remote" } else { "local sqlite" }
Write-Host "[MirrAI] DB mode: $dbMode" -ForegroundColor Cyan

$process = Start-Process @startInfo
$process.Id | Set-Content -Path $pidFile -Encoding ascii

Write-Host "[MirrAI] Supabase test server started in background. PID=$($process.Id)" -ForegroundColor Green
Write-Host "Open http://127.0.0.1:8000/partner/login/"
Write-Host "Logs:"
Write-Host " - $stdoutLog"
Write-Host " - $stderrLog"
