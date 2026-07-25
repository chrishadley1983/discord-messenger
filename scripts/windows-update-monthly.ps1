# Monthly deliberate Windows Update install (daytime, post-Patch-Tuesday).
# Auto-install is disabled by policy (AUOptions=2, notify-only) — this task is the
# ONLY thing that installs updates. Runs on the 16th at 10:00 via the
# WindowsUpdate-Monthly scheduled task (SYSTEM), after the day-5 health check has
# verified the component store is clean (see incident-july-cu-corruption).
# Never reboots by itself — posts to Discord #alerts asking for a same-day reboot.

$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\Chris Hadley\claude-projects\discord-messenger'
$logDir = Join-Path $repo 'data\windows_health'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$log = Join-Path $logDir "update_$stamp.log"
Start-Transcript -Path $log -Force

function Get-Webhook {
    $line = Get-Content (Join-Path $repo '.env') -ErrorAction SilentlyContinue | Where-Object { $_ -match '^DISCORD_WEBHOOK_ALERTS=' } | Select-Object -First 1
    if ($line) { return ($line -replace '^DISCORD_WEBHOOK_ALERTS=','').Trim() }
    return $null
}
function Post-Discord([string]$msg) {
    $hook = Get-Webhook
    if (-not $hook) { Write-Host 'No webhook; skipping post.'; return }
    try { Invoke-RestMethod -Method Post -Uri $hook -ContentType 'application/json' -Body (@{ content = $msg } | ConvertTo-Json) -TimeoutSec 30 | Out-Null } catch { Write-Host ("Discord post failed: {0}" -f $_.Exception.Message) }
}

$host_ = $env:COMPUTERNAME

# Safety gate: skip install if the most recent health check found problems.
$lastHealth = Get-ChildItem $logDir -Filter 'health_*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($lastHealth) {
    $h = Get-Content $lastHealth.FullName -Raw
    if ($h -match 'PROBLEMS|CORRUPT|UNFIXABLE') {
        Post-Discord (":no_entry: **Windows update SKIPPED** ($host_): last health check ($($lastHealth.Name)) found component-store problems. Fix those first (DISM /RestoreHealth), re-run the health check, then Start-ScheduledTask WindowsUpdate-Monthly.")
        Write-Host 'Skipping install - last health check was red.'
        Stop-Transcript
        exit 0
    }
    Write-Host ("Health gate OK (last check: {0})" -f $lastHealth.Name)
} else {
    Write-Host 'No previous health check found - proceeding anyway.'
}

Write-Host "=== Ensure PSWindowsUpdate module ==="
if (-not (Get-Module -ListAvailable PSWindowsUpdate)) {
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force -Scope AllUsers | Out-Null
        Install-Module PSWindowsUpdate -Force -Scope AllUsers -Confirm:$false
    } catch {
        Post-Discord (":rotating_light: **Windows update FAILED** ($host_): could not install PSWindowsUpdate module: $($_.Exception.Message)")
        Stop-Transcript; exit 1
    }
}
Import-Module PSWindowsUpdate

Write-Host "=== Checking for updates ==="
$avail = Get-WindowsUpdate -MicrosoftUpdate -ErrorAction SilentlyContinue
if (-not $avail) {
    Post-Discord (":white_check_mark: **Windows update** ($host_): no updates pending this month.")
    Write-Host 'No updates available.'
    Stop-Transcript; exit 0
}
$names = ($avail | ForEach-Object { "- $($_.KB) $($_.Title)" }) -join "`n"
Write-Host "Available:`n$names"
Post-Discord (":arrows_counterclockwise: **Windows update starting** ($host_): installing $($avail.Count) update(s):`n$names")

Write-Host "=== Installing (no auto-reboot) ==="
$result = Install-WindowsUpdate -MicrosoftUpdate -AcceptAll -IgnoreReboot -ErrorAction Continue
$result | Format-Table -AutoSize | Out-String | Write-Host

$failed = @($result | Where-Object { $_.Result -eq 'Failed' })
$rebootNeeded = (Get-WURebootStatus -Silent) -eq $true
if ($failed.Count -gt 0) {
    $fl = ($failed | ForEach-Object { "- $($_.KB) $($_.Title)" }) -join "`n"
    Post-Discord (":rotating_light: **Windows update** ($host_): $($failed.Count) update(s) FAILED:`n$fl`nLog: $log")
} else {
    $rebootMsg = if ($rebootNeeded) { "**Reboot needed - please restart TODAY (daytime), don't leave it pending overnight** (overnight batches)." } else { 'No reboot required.' }
    Post-Discord (":white_check_mark: **Windows update** ($host_): $($result.Count) update(s) installed successfully. $rebootMsg")
}

Write-Host "Done ($(Get-Date))."
Get-ChildItem $logDir -Filter 'update_*.log' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 12 | Remove-Item -Force -ErrorAction SilentlyContinue
Stop-Transcript
