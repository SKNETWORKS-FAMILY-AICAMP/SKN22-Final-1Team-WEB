$ErrorActionPreference = "Stop"

$utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8

$projectRoot = "C:\Workspaces\Teamwork\Final\backend"
$pythonExe = "C:\Users\Playdata\AppData\Local\miniconda3\envs\mirrai\python.exe"

Set-Location $projectRoot

if (-not (Test-Path ".\manage.py")) {
    throw "manage.py not found. Current path: $projectRoot"
}

if (-not (Test-Path $pythonExe)) {
    throw "mirrai python not found: $pythonExe"
}

$env:SUPABASE_USE_REMOTE_DB = "True"
$env:SUPABASE_USE_REMOTE_STORAGE = "False"
$env:DEBUG = "True"
$env:MIRRAI_LOCAL_MOCK_RESULTS = "True"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "[MirrAI] Starting Supabase integrity check." -ForegroundColor Cyan
Write-Host " - Path: $projectRoot"
Write-Host " - Python: $pythonExe"
Write-Host " - DB: Supabase remote"
Write-Host " - STORAGE: local"
Write-Host " - DEBUG: True"
Write-Host " - MOCK RESULTS: True"

Write-Host "[1/2] Django configuration check" -ForegroundColor Yellow
& $pythonExe manage.py check

Write-Host "[2/2] Seed integrity verification" -ForegroundColor Yellow
& $pythonExe manage.py verify_seed_integrity --strict

Write-Host "[MirrAI] Supabase integrity check completed." -ForegroundColor Green
