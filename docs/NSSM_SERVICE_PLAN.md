# NSSM Service Setup Plan

## Overview

Convert Discord-Messenger services from fragile `start /B` background processes to proper Windows Services using NSSM (Non-Sucking Service Manager). This provides:
- Automatic restart on crash
- Proper logging with rotation
- Windows Service Manager integration
- Boot-time auto-start
- Clean shutdown handling

## Current Problems

1. **Port mismatch**: Scripts use 8200, code expects 8100
2. **Duplicate processes**: Multiple Python interpreters spawning duplicates
3. **No supervision**: Crashes go unnoticed, no auto-restart
4. **No logging**: stdout/stderr lost when processes die
5. **Fragile startup**: `start /B` processes easily orphaned

## Services to Create

| Service Name | Command | Port | Description |
|--------------|---------|------|-------------|
| HadleyAPI | `python -m uvicorn hadley_api.main:app --host 0.0.0.0 --port 8100` | 8100 | Main API proxy |
| DiscordBot | `python bot.py` | - | Discord bot with scheduler |
| PeterDashboard | `python peter_dashboard/app.py` | 5000 | Dashboard web UI |

**Note**: Peter (Claude Code tmux session) stays in WSL - already working fine.

---

## Implementation Steps

### Step 1: Download NSSM

```powershell
# Download NSSM
Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile "$env:TEMP\nssm.zip"

# Extract to Program Files
Expand-Archive -Path "$env:TEMP\nssm.zip" -DestinationPath "C:\Program Files\nssm" -Force

# Add to PATH (run as admin)
$env:Path += ";C:\Program Files\nssm\nssm-2.24\win64"
[Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\nssm\nssm-2.24\win64", "Machine")
```

### Step 2: Kill Existing Processes

```powershell
# Find and kill existing Python processes for our services
Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
    $cmd -match "uvicorn|bot\.py|dashboard"
} | Stop-Process -Force

# Verify ports are free
netstat -ano | findstr ":8100 :5000"
```

### Step 3: Create Log Directory

```powershell
# Create log directory
New-Item -ItemType Directory -Path "C:\Users\Chris Hadley\Discord-Messenger\logs" -Force
```

### Step 4: Install Hadley API Service

```powershell
# Install service
nssm install HadleyAPI "C:\Users\Chris Hadley\AppData\Local\Programs\Python\Python312\python.exe" "-m uvicorn hadley_api.main:app --host 0.0.0.0 --port 8100"

# Set working directory
nssm set HadleyAPI AppDirectory "C:\Users\Chris Hadley\Discord-Messenger"

# Configure logging
nssm set HadleyAPI AppStdout "C:\Users\Chris Hadley\Discord-Messenger\logs\hadley_api.log"
nssm set HadleyAPI AppStderr "C:\Users\Chris Hadley\Discord-Messenger\logs\hadley_api.log"
nssm set HadleyAPI AppStdoutCreationDisposition 4
nssm set HadleyAPI AppStderrCreationDisposition 4
nssm set HadleyAPI AppRotateFiles 1
nssm set HadleyAPI AppRotateBytes 10485760

# Set restart behavior
nssm set HadleyAPI AppRestartDelay 5000

# Set description
nssm set HadleyAPI Description "Hadley API - Local API proxy for Peter"

# Start service
nssm start HadleyAPI
```

### Step 5: Install Discord Bot Service

```powershell
# Install service
nssm install DiscordBot "C:\Users\Chris Hadley\AppData\Local\Programs\Python\Python312\python.exe" "bot.py"

# Set working directory
nssm set DiscordBot AppDirectory "C:\Users\Chris Hadley\Discord-Messenger"

# Configure logging
nssm set DiscordBot AppStdout "C:\Users\Chris Hadley\Discord-Messenger\logs\discord_bot.log"
nssm set DiscordBot AppStderr "C:\Users\Chris Hadley\Discord-Messenger\logs\discord_bot.log"
nssm set DiscordBot AppStdoutCreationDisposition 4
nssm set DiscordBot AppStderrCreationDisposition 4
nssm set DiscordBot AppRotateFiles 1
nssm set DiscordBot AppRotateBytes 10485760

# Set restart behavior
nssm set DiscordBot AppRestartDelay 5000

# Set description
nssm set DiscordBot Description "Discord Messenger Bot with APScheduler"

# Start service
nssm start DiscordBot
```

### Step 6: Install Peter Dashboard Service

```powershell
# Install service
nssm install PeterDashboard "C:\Users\Chris Hadley\AppData\Local\Programs\Python\Python312\python.exe" "peter_dashboard/app.py"

# Set working directory
nssm set PeterDashboard AppDirectory "C:\Users\Chris Hadley\Discord-Messenger"

# Configure logging
nssm set PeterDashboard AppStdout "C:\Users\Chris Hadley\Discord-Messenger\logs\peter_dashboard.log"
nssm set PeterDashboard AppStderr "C:\Users\Chris Hadley\Discord-Messenger\logs\peter_dashboard.log"
nssm set PeterDashboard AppStdoutCreationDisposition 4
nssm set PeterDashboard AppStderrCreationDisposition 4
nssm set PeterDashboard AppRotateFiles 1
nssm set PeterDashboard AppRotateBytes 10485760

# Set restart behavior
nssm set PeterDashboard AppRestartDelay 5000

# Set description
nssm set PeterDashboard Description "Peter Dashboard - Service status and controls"

# Start service
nssm start PeterDashboard
```

### Step 7: Verify Services

```powershell
# Check all services are running
Get-Service HadleyAPI, DiscordBot, PeterDashboard | Format-Table Name, Status, StartType

# Test API health
Invoke-RestMethod -Uri "http://localhost:8100/health"

# Test Dashboard
Invoke-RestMethod -Uri "http://localhost:5000/" -Method Head

# Check logs
Get-Content "C:\Users\Chris Hadley\Discord-Messenger\logs\hadley_api.log" -Tail 20
```

### Step 8: Remove Old Startup Scripts

```powershell
# Remove from Windows Startup
Remove-Item "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Peterbot*" -Force -ErrorAction SilentlyContinue

# Optionally archive old scripts
Move-Item "C:\Users\Chris Hadley\Discord-Messenger\start_all.bat" "C:\Users\Chris Hadley\Discord-Messenger\archive\start_all.bat.old" -Force
Move-Item "C:\Users\Chris Hadley\Discord-Messenger\start_all_silent.vbs" "C:\Users\Chris Hadley\Discord-Messenger\archive\start_all_silent.vbs.old" -Force
```

---

## Management Commands

### Service Control

```powershell
# Start/Stop/Restart individual services
nssm start HadleyAPI
nssm stop HadleyAPI
nssm restart HadleyAPI

# Or use standard Windows commands
Start-Service HadleyAPI
Stop-Service HadleyAPI
Restart-Service HadleyAPI

# Start all
Start-Service HadleyAPI, DiscordBot, PeterDashboard

# Stop all
Stop-Service HadleyAPI, DiscordBot, PeterDashboard
```

### View Logs

```powershell
# Tail logs in real-time
Get-Content "C:\Users\Chris Hadley\Discord-Messenger\logs\hadley_api.log" -Wait -Tail 50
Get-Content "C:\Users\Chris Hadley\Discord-Messenger\logs\discord_bot.log" -Wait -Tail 50
Get-Content "C:\Users\Chris Hadley\Discord-Messenger\logs\peter_dashboard.log" -Wait -Tail 50
```

### Edit Service Configuration

```powershell
# Open NSSM GUI for a service
nssm edit HadleyAPI
```

### Uninstall Services (if needed)

```powershell
nssm stop HadleyAPI
nssm remove HadleyAPI confirm

nssm stop DiscordBot
nssm remove DiscordBot confirm

nssm stop PeterDashboard
nssm remove PeterDashboard confirm
```

---

## Post-Setup: Peter tmux Session

Peter (Claude Code) still runs in WSL tmux. To auto-start on boot:

### Option A: Windows Task Scheduler (Current)

Keep the existing task or create one:
```powershell
$action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-d Ubuntu -u chris_hadley -- bash -c 'tmux has-session -t peter 2>/dev/null || tmux new-session -d -s peter -c /home/chris_hadley/peterbot claude --dangerously-skip-permissions'"
$trigger = New-ScheduledTaskTrigger -AtStartup
Register-ScheduledTask -TaskName "StartPeterSession" -Action $action -Trigger $trigger -RunLevel Highest
```

### Option B: WSL systemd (if enabled)

Create `/etc/systemd/system/peter.service` in WSL - but Task Scheduler is simpler.

---

## Troubleshooting

### Service won't start

```powershell
# Check Windows Event Log
Get-EventLog -LogName Application -Source "nssm" -Newest 10

# Check service status
nssm status HadleyAPI

# Check log file for errors
Get-Content "C:\Users\Chris Hadley\Discord-Messenger\logs\hadley_api.log" -Tail 50
```

### Port already in use

```powershell
# Find process on port
netstat -ano | findstr ":8100"

# Kill by PID
Stop-Process -Id <PID> -Force
```

### Python path issues

```powershell
# Find correct Python path
Get-Command python | Select-Object Source

# Update service
nssm set HadleyAPI Application "C:\correct\path\to\python.exe"
```

---

## Summary

After completing this plan:

| Before | After |
|--------|-------|
| Manual `start /B` processes | Windows Services with auto-restart |
| No logging | Rotated log files in `logs/` |
| Crashes go unnoticed | Auto-restart within 5 seconds |
| Port 8200/8100 confusion | Consistent port 8100 |
| Startup scripts in shell:startup | Services start at boot automatically |
| Multiple duplicate processes | Single managed process per service |

**Time estimate**: 30-45 minutes including verification.
