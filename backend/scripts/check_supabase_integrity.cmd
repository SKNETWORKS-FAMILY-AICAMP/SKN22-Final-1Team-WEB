@echo off
setlocal
chcp 65001 >nul

set PROJECT_ROOT=C:\Workspaces\Teamwork\Final\backend
set PYTHON_EXE=C:\Users\Playdata\AppData\Local\miniconda3\envs\mirrai\python.exe

cd /d "%PROJECT_ROOT%"

if not exist manage.py (
  echo manage.py not found. Current path: %PROJECT_ROOT%
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo mirrai python not found: %PYTHON_EXE%
  exit /b 1
)

set SUPABASE_USE_REMOTE_DB=True
set SUPABASE_USE_REMOTE_STORAGE=False
set DEBUG=True
set MIRRAI_LOCAL_MOCK_RESULTS=True
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo [MirrAI] Starting Supabase integrity check.
echo  - Path: %PROJECT_ROOT%
echo  - Python: %PYTHON_EXE%
echo  - DB: Supabase remote
echo  - STORAGE: local
echo  - DEBUG: True
echo  - MOCK RESULTS: True

echo [1/2] Django configuration check
"%PYTHON_EXE%" manage.py check || exit /b 1

echo [2/2] Seed integrity verification
"%PYTHON_EXE%" manage.py verify_seed_integrity --strict || exit /b 1

echo [MirrAI] Supabase integrity check completed.
