@echo off
setlocal

chcp 65001 >nul

cd /d C:\Workspaces\Teamwork\Final\backend

set SUPABASE_USE_REMOTE_DB=False
set SUPABASE_USE_REMOTE_STORAGE=False
set LOCAL_DATABASE_URL=sqlite:///db.sqlite3
set DEBUG=True
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set PYTHON_EXE=C:\Users\Playdata\AppData\Local\miniconda3\envs\mirrai\python.exe

if not exist "%PYTHON_EXE%" (
  echo mirrai python not found: %PYTHON_EXE%
  exit /b 1
)

if not exist manage.py (
  echo manage.py not found.
  exit /b 1
)

echo [MirrAI] preparing local backend server...
echo  - cwd: %CD%
echo  - python: %PYTHON_EXE%
echo  - db: sqlite:///db.sqlite3
echo  - DEBUG: True

"%PYTHON_EXE%" manage.py migrate || exit /b 1
"%PYTHON_EXE%" manage.py check || exit /b 1

echo [MirrAI] starting server at http://127.0.0.1:8000
"%PYTHON_EXE%" manage.py runserver 127.0.0.1:8000 --noreload
