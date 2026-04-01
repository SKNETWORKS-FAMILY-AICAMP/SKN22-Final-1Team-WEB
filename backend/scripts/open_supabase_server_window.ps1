$ErrorActionPreference = "Stop"

$projectRoot = "C:\Workspaces\Teamwork\Final\backend"
$pythonExe = "C:\Users\Playdata\AppData\Local\miniconda3\envs\mirrai\python.exe"

if (-not (Test-Path (Join-Path $projectRoot "manage.py"))) {
    throw "manage.py not found. Current path: $projectRoot"
}

if (-not (Test-Path $pythonExe)) {
    throw "mirrai python not found: $pythonExe"
}

$command = @"
Set-Location '$projectRoot'
`$env:SUPABASE_USE_REMOTE_DB='True'
`$env:SUPABASE_USE_REMOTE_STORAGE='False'
`$env:DEBUG='True'
`$env:MIRRAI_LOCAL_MOCK_RESULTS='True'
`$env:PYTHONUTF8='1'
`$env:PYTHONIOENCODING='utf-8'
& '$pythonExe' manage.py check
& '$pythonExe' manage.py runserver 127.0.0.1:8000 --noreload
"@

Start-Process powershell.exe -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $command)

Write-Host "[MirrAI] A new PowerShell window was opened for the Supabase test server." -ForegroundColor Green
Write-Host "When the server is ready, open http://127.0.0.1:8000/partner/login/"
