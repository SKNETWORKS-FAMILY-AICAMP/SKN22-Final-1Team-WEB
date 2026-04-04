@echo off
SETLOCAL EnableDelayedExpansion

:: Change directory to the folder where this script is located
cd /d %~dp0

echo [1/4] Checking requirements...
pip install -r requirements.txt --quiet

echo [2/4] Applying migrations...
python manage.py migrate --noinput

echo [3/4] Starting FastAPI AI Service on port 8001...
START /B "FastAPI AI" python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

echo [4/4] Starting Django Server on port 8000...
echo Launching Browser...
START http://localhost:8000
python manage.py runserver 0.0.0.0:8000

ENDLOCAL
