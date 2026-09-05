# Windows maintenance pack installer.
# Sets up: (1) notify-only Windows Update policy (no auto-install, no auto-reboot),
# (2) monthly health check task (5th 03:30), (3) monthly deliberate update task (16th 10:00).
# Both tasks post results to Discord #alerts. Run this from the pack folder; it
# self-elevates. Safe to re-run (idempotent).

$admin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
if (-not $admin) {
    Write-Host 'Relaunching as Administrator (approve the UAC prompt)...'
    Start-Process powershell -Verb RunAs -ArgumentList @('-NoExit','-NoProfile','-ExecutionPolicy','Bypass','-File',"`"$PSCommandPath`"")
    exit
}

$ErrorActionPreference = 'Continue'
$src = $PSScriptRoot
$base = 'C:\ProgramData\WindowsMaintenance'
New-Item -ItemType Directory -Path $base -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $base 'logs') -Force | Out-Null
Start-Transcript -Path (Join-Path $base 'install.log') -Force

Write-Host '=== 1. Copy scripts ==='
Copy-Item (Join-Path $src 'windows-health-check.ps1') $base -Force
Copy-Item (Join-Path $src 'windows-update-monthly.ps1') $base -Force
Write-Host "Scripts copied to $base"

Write-Host '=== 2. Webhook config ==='
$whFile = Join-Path $src 'webhook.txt'
if (Test-Path $whFile) {
    $wh = (Get-Content $whFile -Raw).Trim()
    @{ webhook = $wh } | ConvertTo-Json | Set-Content (Join-Path $base 'config.json') -Encoding ASCII
    Write-Host 'config.json written from webhook.txt'
} elseif (Test-Path (Join-Path $base 'config.json')) {
    Write-Host 'config.json already present - keeping it'
} else {
    Write-Host 'WARNING: no webhook.txt found and no existing config.json - Discord alerts will be skipped.'
    Write-Host "Create $base\config.json with: {""webhook"": ""https://discord.com/api/webhooks/...""}"
}

Write-Host '=== 3. Windows Update policy: notify-only, no auto-reboot ==='
$au = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
New-Item -Path $au -Force | Out-Null
Set-ItemProperty -Path $au -Name 'NoAutoUpdate' -Value 0 -Type DWord
Set-ItemProperty -Path $au -Name 'AUOptions' -Value 2 -Type DWord   # 2 = notify before download
Set-ItemProperty -Path $au -Name 'NoAutoRebootWithLoggedOnUsers' -Value 1 -Type DWord
Get-ItemProperty $au | Select-Object NoAutoUpdate, AUOptions, NoAutoRebootWithLoggedOnUsers | Format-List

Write-Host '=== 4. Register scheduled tasks ==='
foreach ($t in @(
    @{ name = 'WindowsHealthCheck-Monthly'; xml = 'WindowsHealthCheck-Monthly.xml' },
    @{ name = 'WindowsUpdate-Monthly';      xml = 'WindowsUpdate-Monthly.xml' }
)) {
    schtasks /create /f /tn $t.name /xml (Join-Path $src $t.xml)
    Write-Host ("{0}: exit {1}" -f $t.name, $LASTEXITCODE)
}

Write-Host '=== 5. Policy refresh ==='
gpupdate /target:computer /force | Out-Null

Write-Host '=== 6. First health check (DISM+SFC, 10-20 min, result goes to Discord #alerts) ==='
Start-ScheduledTask -TaskName 'WindowsHealthCheck-Monthly'
Write-Host 'Health check started in background.'

Write-Host ''
Write-Host 'INSTALL COMPLETE.'
Write-Host 'Schedule: health check = 5th 03:30; updates install = 16th 10:00 (never auto-reboots).'
Write-Host 'To install updates on demand: Start-ScheduledTask WindowsUpdate-Monthly (elevated).'
Stop-Transcript
