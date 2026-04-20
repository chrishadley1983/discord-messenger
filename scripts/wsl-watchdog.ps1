# WSL Watchdog — checks WSL health every 5 minutes, restarts if unreachable.
# Install as Windows Scheduled Task:
#   schtasks /create /tn "WSL Watchdog" /tr "powershell -ExecutionPolicy Bypass -File C:\Users\Chris` Hadley\claude-projects\discord-messenger\scripts\wsl-watchdog.ps1" /sc minute /mo 5 /ru SYSTEM
#
# Or via PowerShell:
#   $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"C:\Users\Chris Hadley\claude-projects\discord-messenger\scripts\wsl-watchdog.ps1`""
#   $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 365)
#   Register-ScheduledTask -TaskName "WSL Watchdog" -Action $action -Trigger $trigger -RunLevel Highest -User "SYSTEM"

$ErrorActionPreference = "SilentlyContinue"
$LogFile = "$env:LOCALAPPDATA\wsl-watchdog\watchdog.log"
$WebhookUrl = ""

# Try to load webhook from .env
$envFile = "C:\Users\Chris Hadley\claude-projects\discord-messenger\.env"
if (Test-Path $envFile) {
    $match = Select-String -Path $envFile -Pattern "^DISCORD_WEBHOOK_ALERTS=(.+)" | Select-Object -First 1
    if ($match) {
        $WebhookUrl = $match.Matches.Groups[1].Value.Trim()
    }
}

# Ensure log directory exists
$logDir = Split-Path $LogFile
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts $msg" | Out-File -Append -FilePath $LogFile -Encoding utf8
    # Keep log file under 1MB
    if ((Get-Item $LogFile -ErrorAction SilentlyContinue).Length -gt 1MB) {
        $lines = Get-Content $LogFile | Select-Object -Last 500
        $lines | Set-Content $LogFile -Encoding utf8
    }
}

function Send-Alert($msg) {
    if (-not $WebhookUrl) { return }
    try {
        $body = @{ content = $msg; username = "WSL Watchdog" } | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri $WebhookUrl -Method Post -ContentType "application/json" -Body $body -TimeoutSec 10
    } catch {
        Write-Log "Failed to send alert: $_"
    }
}

# --- Health Check ---
try {
    # Quick check: can we run a command in WSL?
    $result = wsl bash -c "echo OK" 2>&1
    if ($result -match "OK") {
        # WSL is responding — check tmux sessions.
        # Join stdout lines into one string so -notmatch behaves as a boolean
        # regex test. On an array it filters rather than boolean-tests, which
        # made the previous version flag every session as missing.
        $sessionsText = ((wsl bash -c "tmux list-sessions 2>/dev/null" 2>&1) -join "`n")
        $expectedSessions = @("peter-channel", "whatsapp-channel", "jobs-channel")
        $missingSessions = @()

        foreach ($sess in $expectedSessions) {
            if ($sessionsText -notmatch [regex]::Escape($sess)) {
                $missingSessions += $sess
            }
        }

        if ($missingSessions.Count -gt 0) {
            $missing = $missingSessions -join ", "
            Write-Log "WARNING: Missing tmux sessions: $missing"
            Send-Alert "⚠️ **WSL Watchdog**: Missing tmux sessions: $missing. WSL is running but channels are down."
        }
        # else: all healthy, don't log (reduce noise)
        exit 0
    }
} catch {
    # WSL command failed
}

# --- WSL is unreachable ---
Write-Log "CRITICAL: WSL is not responding. Attempting restart..."
Send-Alert "🔴 **WSL Watchdog**: WSL is not responding. Attempting `wsl --shutdown` and restart..."

try {
    # Shutdown WSL
    wsl --shutdown
    Start-Sleep -Seconds 10

    # Restart WSL by running a simple command
    $result = wsl bash -c "echo RESTARTED" 2>&1
    if ($result -match "RESTARTED") {
        Write-Log "WSL restarted successfully"

        # Wait for WSL to fully initialise
        Start-Sleep -Seconds 5

        # Relaunch channel sessions via temp wrapper scripts.
        # Wrapper is written to a Windows temp dir (PS controls the content cleanly)
        # and read by WSL via /mnt/c/ — avoids nested PS+bash quote escaping entirely.
        $channels = @("peter-channel", "whatsapp-channel", "jobs-channel")
        $repoRoot = "/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger"

        foreach ($sess in $channels) {
            $winLauncher = Join-Path $env:TEMP "wsl-relaunch-$sess.sh"
            # Convert "C:\Windows\Temp\wsl-relaunch-peter-channel.sh" to "/mnt/c/Windows/Temp/..."
            $wslLauncher = "/mnt/c/" + (($winLauncher -replace '\\','/') -replace '^[A-Za-z]:/','')
            $content = "#!/bin/bash`nbash '$repoRoot/$sess/launch.sh'`n"
            Set-Content -Path $winLauncher -Value $content -Encoding ascii -NoNewline

            # Now invoke — simple single-line bash command with no nested quotes on PS side.
            # The '&&' lives inside the bash command string, which PS passes as one argv.
            $bashCmd = "chmod +x '$wslLauncher' && tmux new-session -d -s $sess '$wslLauncher'"
            wsl bash -c $bashCmd 2>&1 | Out-Null
            Write-Log "Launched tmux session: $sess"
            Start-Sleep -Seconds 2
        }

        Send-Alert "✅ **WSL Watchdog**: WSL restarted successfully. Channel sessions relaunched."
    } else {
        Write-Log "FAILED: WSL did not restart properly"
        Send-Alert "🔴 **WSL Watchdog**: WSL restart FAILED. Manual intervention required."
    }
} catch {
    Write-Log "FAILED: WSL restart threw exception: $_"
    Send-Alert "🔴 **WSL Watchdog**: WSL restart threw exception: $_. Manual intervention required."
}
