@echo off
REM Start all Peterbot services on Windows startup
REM Place shortcut to this file in shell:startup

cd /d "C:\Users\Chris Hadley\Discord-Messenger"

echo Starting Peterbot Services...
echo ==============================

REM Start Hadley API (port 8100)
echo [1/4] Starting Hadley API on port 8100...
start /B "Hadley API" python -m uvicorn hadley_api.main:app --host 0.0.0.0 --port 8100

REM Wait for API to start
timeout /t 3 /nobreak > nul

REM Start Peter Dashboard (port 5000)
echo [2/4] Starting Peter Dashboard on port 5000...
start /B "Peter Dashboard" python peter_dashboard/app.py

REM Wait for dashboard to start
timeout /t 2 /nobreak > nul

REM Start Discord Bot
echo [3/4] Starting Discord Bot...
start /B "Discord Bot" python bot.py

REM Wait for bot to start
timeout /t 3 /nobreak > nul

REM Start Peter tmux session in WSL
echo [4/4] Starting Peter session in WSL...
wsl -d Ubuntu -u chris_hadley -- bash -c "tmux has-session -t peter 2>/dev/null || tmux new-session -d -s peter -c /home/chris_hadley/peterbot 'claude --dangerously-skip-permissions'"

echo.
echo ==============================
echo All services started!
echo.
echo Services:
echo   - Hadley API:      http://localhost:8100/
echo   - Peter Dashboard: http://localhost:5000/
echo   - Discord Bot:     Running
echo   - Peter (WSL):     tmux session 'peter'
echo.
echo To view Peter session: wsl -d Ubuntu -u chris_hadley -- tmux attach -t peter
echo ==============================
