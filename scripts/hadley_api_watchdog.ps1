# HadleyAPI Health Watchdog
# Runs every 60s via Scheduled Task. If /health fails twice in a row, restarts the NSSM service.
# Logs to Discord-Messenger\logs\watchdog.log

$LogFile = "C:\Users\Chris Hadley\claude-projects\Discord-Messenger\logs\watchdog.log"
$HealthUrl = "http://localhost:8100/health"
$ServiceName = "HadleyAPI"
$TimeoutSec = 5
$StateFile = "C:\Users\Chris Hadley\claude-projects\Discord-Messenger\logs\watchdog_state.txt"

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Out-File -Append -FilePath $LogFile -Encoding utf8
}

# Check health endpoint
$healthy = $false
try {
    $resp = Invoke-WebRequest -Uri $HealthUrl -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
    if ($resp.StatusCode -eq 200) { $healthy = $true }
} catch {
    # request failed or timed out
}

if ($healthy) {
    # Clear any previous failure state
    if (Test-Path $StateFile) { Remove-Item $StateFile -Force }
    exit 0
}

# Not healthy — check if this is the second consecutive failure
if (Test-Path $StateFile) {
    # Second failure in a row — restart the service
    Write-Log "RESTART: $ServiceName unresponsive for 2 consecutive checks. Restarting..."

    # Get the service PID and kill the process tree (handles hung uvicorn)
    $svc = Get-WmiObject Win32_Service -Filter "Name='$ServiceName'" -ErrorAction SilentlyContinue
    if ($svc -and $svc.ProcessId -gt 0) {
        $children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $svc.ProcessId }
        foreach ($child in $children) {
            Write-Log "  Killing child PID $($child.ProcessId)"
            Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }

    # Now restart via NSSM
    & nssm restart $ServiceName 2>&1 | Out-Null
    Start-Sleep -Seconds 5

    # Verify it came back
    $back = $false
    try {
        $r = Invoke-WebRequest -Uri $HealthUrl -TimeoutSec $TimeoutSec -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $back = $true }
    } catch {}

    if ($back) {
        Write-Log "RECOVERED: $ServiceName is healthy after restart"
    } else {
        Write-Log "FAILED: $ServiceName still unresponsive after restart"
    }

    Remove-Item $StateFile -Force -ErrorAction SilentlyContinue
} else {
    # First failure — record it, give it one more chance
    Write-Log "WARNING: $ServiceName health check failed. Will restart on next failure."
    "fail" | Out-File -FilePath $StateFile -Encoding utf8
}
