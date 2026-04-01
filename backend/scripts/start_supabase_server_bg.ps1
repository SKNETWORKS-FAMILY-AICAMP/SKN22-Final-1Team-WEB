$ErrorActionPreference = "Stop"

$projectRoot = "C:\Workspaces\Teamwork\Final\backend"
$pythonExe = "C:\Users\Playdata\AppData\Local\miniconda3\envs\mirrai\python.exe"
$logDir = Join-Path $projectRoot ".tmp_supabase_server"
$stdoutLog = Join-Path $logDir "stdout.log"
$stderrLog = Join-Path $logDir "stderr.log"
$pidFile = Join-Path $logDir "server.pid"

Set-Location $projectRoot

if (-not (Test-Path ".\manage.py")) {
    throw "manage.py not found. Current path: $projectRoot"
}

if (-not (Test-Path $pythonExe)) {
    throw "mirrai python not found: $pythonExe"
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

$env:SUPABASE_USE_REMOTE_DB = "True"
$env:SUPABASE_USE_REMOTE_STORAGE = "False"
$env:DEBUG = "True"
$env:MIRRAI_LOCAL_MOCK_RESULTS = "True"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

& $pythonExe manage.py check | Out-Host

$process = Start-Process @startInfo
$process.Id | Set-Content -Path $pidFile -Encoding ascii

Write-Host "[MirrAI] Supabase test server started in background. PID=$($process.Id)" -ForegroundColor Green
Write-Host "Open http://127.0.0.1:8000/partner/login/"
Write-Host "Logs:"
Write-Host " - $stdoutLog"
Write-Host " - $stderrLog"
