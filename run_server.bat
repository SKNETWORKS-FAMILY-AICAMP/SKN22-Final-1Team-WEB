@echo off
SETLOCAL EnableDelayedExpansion

:: Change directory to the folder where this script is located
cd /d %~dp0

set "ENABLE_TREND_SCHEDULER=false"
for /f "tokens=1,* delims==" %%A in ('findstr /b /i "ENABLE_TREND_SCHEDULER=" ".env"') do (
    set "ENABLE_TREND_SCHEDULER=%%B"
)

echo [1/5] Checking requirements...
pip install -r requirements.txt --quiet

echo [2/5] Applying migrations...
python manage.py migrate --noinput

echo [3/5] Starting FastAPI AI Service on port 8001...
START /B "FastAPI AI" python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

if /I "!ENABLE_TREND_SCHEDULER!"=="true" (
echo [4/5] Trend Scheduler will auto-start inside Django because ENABLE_TREND_SCHEDULER=true
) else (
    echo [4/5] Trend Scheduler is disabled in .env
)

echo [5/5] Starting Django Server on port 8000...
echo Launching Browser...
START http://localhost:8000
python manage.py runserver 0.0.0.0:8000

ENDLOCAL
