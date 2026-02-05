@echo off
cd /d "%~dp0"

REM Check if already running on port 5000
netstat -an | findstr ":5000.*LISTENING" >nul
if %errorlevel%==0 (
    echo Dashboard already running on http://localhost:5000
    echo Use stop-dashboard.bat to stop it first.
    pause
    exit /b 1
)

echo Starting Peter Dashboard on http://localhost:5000
python -m uvicorn app:app --host 0.0.0.0 --port 5000 --reload
pause
