$ErrorActionPreference = "Stop"

$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$projectRoot = "C:\Workspaces\Teamwork\Final\backend"
$pythonExe = "C:\Users\Playdata\AppData\Local\miniconda3\envs\mirrai\python.exe"

Set-Location $projectRoot

if (-not (Test-Path ".\manage.py")) {
    throw "manage.py를 찾을 수 없습니다. 현재 경로: $projectRoot"
}

if (-not (Test-Path $pythonExe)) {
    throw "mirrai python 경로를 찾을 수 없습니다: $pythonExe"
}

$env:SUPABASE_USE_REMOTE_DB = "False"
$env:SUPABASE_USE_REMOTE_STORAGE = "False"
$env:LOCAL_DATABASE_URL = "sqlite:///db.sqlite3"
$env:DEBUG = "True"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "[MirrAI] backend 로컬 서버 준비 중.." -ForegroundColor Cyan
Write-Host " - 경로: $projectRoot"
Write-Host " - Python: $pythonExe"
Write-Host " - DB: sqlite:///db.sqlite3"
Write-Host " - DEBUG: True"

& $pythonExe manage.py migrate
& $pythonExe manage.py check

Write-Host "[MirrAI] http://127.0.0.1:8000 에서 서버를 시작합니다." -ForegroundColor Green
& $pythonExe manage.py runserver 127.0.0.1:8000 --noreload
