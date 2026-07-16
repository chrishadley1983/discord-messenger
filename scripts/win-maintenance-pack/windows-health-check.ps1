# Monthly Windows component-store health check (portable pack version).
# Runs DISM ScanHealth + SFC before Patch Tuesday so store corruption is caught
# BEFORE a cumulative update lands on it (Jul 2026: a CU installed onto a corrupt
# store and took out networking on two machines).
# Posts a one-line green/red summary to Discord #alerts (webhook from config.json).
# Runs as SYSTEM via the WindowsHealthCheck-Monthly scheduled task.

$ErrorActionPreference = 'Continue'
$base = 'C:\ProgramData\WindowsMaintenance'
$logDir = Join-Path $base 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$log = Join-Path $logDir "health_$stamp.log"
Start-Transcript -Path $log -Force

function Get-Webhook {
    $cfg = Join-Path $base 'config.json'
    if (Test-Path $cfg) {
        try { return (Get-Content $cfg -Raw | ConvertFrom-Json).webhook } catch { return $null }
    }
    return $null
}

function Post-Discord([string]$msg) {
    $hook = Get-Webhook
    if (-not $hook) { Write-Host 'No webhook found; skipping Discord post.'; return }
    try {
        Invoke-RestMethod -Method Post -Uri $hook -ContentType 'application/json' -Body (@{ content = $msg } | ConvertTo-Json) -TimeoutSec 30 | Out-Null
        Write-Host 'Posted to Discord.'
    } catch {
        Write-Host ("Discord post failed: {0}" -f $_.Exception.Message)
    }
}

$host_ = $env:COMPUTERNAME
$problems = @()

Write-Host "=== DISM ScanHealth ($(Get-Date)) ==="
$dismOut = & dism.exe /online /cleanup-image /scanhealth 2>&1 | Out-String
Write-Host $dismOut
if ($dismOut -match 'No component store corruption detected') {
    $dismStatus = 'clean'
} elseif ($dismOut -match 'repairable') {
    $dismStatus = 'CORRUPT (repairable)'
    $problems += 'DISM: component store corruption detected (repairable) - run RestoreHealth BEFORE next Windows update'
} elseif ($LASTEXITCODE -ne 0) {
    $dismStatus = "ERROR (exit $LASTEXITCODE)"
    $problems += "DISM ScanHealth failed with exit code $LASTEXITCODE"
} else {
    $dismStatus = 'UNKNOWN'
    $problems += 'DISM ScanHealth output not recognised - check log'
}
Write-Host "DISM status: $dismStatus"

Write-Host ""
Write-Host "=== SFC /scannow ($(Get-Date)) ==="
# SFC writes UTF-16 with interleaved nulls to stdout; strip them before matching.
$sfcRaw = & sfc.exe /scannow 2>&1 | Out-String
$sfcOut = $sfcRaw -replace "`0", ''
Write-Host $sfcOut
if ($sfcOut -match 'did not find any integrity violations') {
    $sfcStatus = 'clean'
} elseif ($sfcOut -match 'successfully repaired') {
    $sfcStatus = 'repaired violations'
    $problems += 'SFC: found + repaired integrity violations (see CBS.log) - store may need RestoreHealth'
} elseif ($sfcOut -match 'unable to fix') {
    $sfcStatus = 'UNFIXABLE violations'
    $problems += 'SFC: found corrupt files it could NOT fix - run DISM RestoreHealth then SFC again BEFORE next Windows update'
} else {
    $sfcStatus = "UNKNOWN (exit $LASTEXITCODE)"
    $problems += "SFC output not recognised (exit $LASTEXITCODE) - check log"
}
Write-Host "SFC status: $sfcStatus"

Write-Host ""
if ($problems.Count -eq 0) {
    Post-Discord (":white_check_mark: **Windows health check** ($host_): component store clean, SFC clean. Safe for next Patch Tuesday.")
} else {
    $detail = ($problems | ForEach-Object { "- $_" }) -join "`n"
    Post-Discord (":rotating_light: **Windows health check** ($host_): PROBLEMS FOUND - fix before next Windows update!`n$detail`nLog: $log")
}

# Keep last 12 logs
Get-ChildItem $logDir -Filter 'health_*.log' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 12 | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "Done ($(Get-Date))."
Stop-Transcript
