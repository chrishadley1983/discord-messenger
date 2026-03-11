@echo off
setlocal EnableDelayedExpansion
REM Start all Peterbot services on Windows startup
REM Place shortcut to this file in shell:startup

cd /d "C:\Users\Chris Hadley\claude-projects\Discord-Messenger"

echo Starting Peterbot Services...
echo ==============================

REM Start Docker Desktop and Evolution API (WhatsApp bridge)
echo [1/6] Starting Docker Desktop...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

REM Wait for Docker daemon to be ready (up to 60s)
echo       Waiting for Docker daemon...
set DOCKER_READY=0
for /L %%i in (1,1,30) do (
    if !DOCKER_READY! == 0 (
        docker info >nul 2>&1 && (
            set DOCKER_READY=1
            echo       Docker ready.
        ) || (
            timeout /t 2 /nobreak > nul
        )
    )
)

echo [2/6] Starting Evolution API (WhatsApp bridge)...
cd /d "C:\Users\Chris Hadley\Docker\evolution-api"
docker compose up -d >nul 2>&1
cd /d "C:\Users\Chris Hadley\claude-projects\Discord-Messenger"

REM Start Hadley API (port 8100)
echo [3/6] Starting Hadley API on port 8100...
start /B "Hadley API" python -m uvicorn hadley_api.main:app --host 0.0.0.0 --port 8100

REM Wait for API to start
timeout /t 3 /nobreak > nul

REM Start Peter Dashboard (port 5000)
echo [4/6] Starting Peter Dashboard on port 5000...
start /B "Peter Dashboard" python peter_dashboard/app.py

REM Wait for dashboard to start
timeout /t 2 /nobreak > nul

REM Start Discord Bot
echo [5/6] Starting Discord Bot...
start /B "Discord Bot" python bot.py

REM Wait for bot to start
timeout /t 3 /nobreak > nul

REM Start Peter tmux session in WSL (retry up to 5 times with delays)
echo [6/6] Starting Peter session in WSL...
set TMUX_STARTED=0
for /L %%i in (1,1,5) do (
    if !TMUX_STARTED! == 0 (
        wsl -d Ubuntu -u chris_hadley -- bash -c "tmux has-session -t peter 2>/dev/null || tmux new-session -d -s peter -c /home/chris_hadley/peterbot 'claude --dangerously-skip-permissions'" 2>nul && (
            set TMUX_STARTED=1
            echo       Peter session started.
        ) || (
            echo       Attempt %%i failed, retrying in 10s...
            timeout /t 10 /nobreak > nul
        )
    )
)

echo.
echo ==============================
echo All services started!
echo.
echo Services:
echo   - Docker/Evolution: http://localhost:8085/ (WhatsApp)
echo   - Hadley API:       http://localhost:8100/
echo   - Peter Dashboard:  http://localhost:5000/
echo   - Discord Bot:      Running
echo   - Peter (WSL):      tmux session 'peter'
echo.
echo To view Peter session: wsl -d Ubuntu -u chris_hadley -- tmux attach -t peter
echo ==============================
