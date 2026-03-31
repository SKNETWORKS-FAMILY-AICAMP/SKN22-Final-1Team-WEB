@echo off
setlocal
chcp 65001 >nul

set PROJECT_ROOT=C:\Workspaces\Teamwork\Final\backend
set PYTHON_EXE=C:\Users\Playdata\AppData\Local\miniconda3\envs\mirrai\python.exe

cd /d "%PROJECT_ROOT%"

if not exist manage.py (
  echo manage.py를 찾을 수 없습니다. 현재 경로: %PROJECT_ROOT%
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo mirrai python 경로를 찾을 수 없습니다: %PYTHON_EXE%
  exit /b 1
)

set SUPABASE_USE_REMOTE_DB=True
set SUPABASE_USE_REMOTE_STORAGE=False
set DEBUG=True
set MIRRAI_LOCAL_MOCK_RESULTS=True
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo [MirrAI] backend Supabase 서버 준비 중..
echo  - 경로: %PROJECT_ROOT%
echo  - Python: %PYTHON_EXE%
echo  - DB: Supabase remote
echo  - STORAGE: local
echo  - DEBUG: True
echo  - MOCK RESULTS: True

"%PYTHON_EXE%" manage.py check || exit /b 1
echo [MirrAI] http://127.0.0.1:8000 에서 Supabase 기준 서버를 시작합니다.
"%PYTHON_EXE%" manage.py runserver 127.0.0.1:8000 --noreload
