@echo off
cd /d "%~dp0"

REM Check if already running on port 5000
netstat -an | findstr ":5000.*LISTENING" >nul
if %errorlevel%==0 (
    echo Dashboard already running on http://localhost:5000
    start http://localhost:5000
    exit /b 0
)

REM Start via service manager (headless, single instance)
python -c "from service_manager import start_service; r=start_service('peter_dashboard', headless=True); print('Started' if r['success'] else r.get('error','Failed'))"

timeout /t 2 >nul
start http://localhost:5000
