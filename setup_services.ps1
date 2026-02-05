# NSSM Service Setup Script
# Run this script as Administrator to set up the services

$ProjectDir = "C:\Users\Chris Hadley\Discord-Messenger"
$PythonExe = "C:\Users\Chris Hadley\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$LogDir = "$ProjectDir\logs"
$LocalAppData = "C:\Users\Chris Hadley\AppData\Local"
$UserProfile = "C:\Users\Chris Hadley"

# Ensure log directory exists
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force
    Write-Host "Created log directory: $LogDir" -ForegroundColor Green
}

# Function to install a service
function Install-NSSMService {
    param (
        [string]$ServiceName,
        [string]$Arguments,
        [string]$Description,
        [string]$LogFile
    )

    Write-Host "`nInstalling $ServiceName..." -ForegroundColor Cyan

    # Check if service already exists
    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Service $ServiceName already exists. Removing..." -ForegroundColor Yellow
        nssm stop $ServiceName 2>$null
        nssm remove $ServiceName confirm
    }

    # Install service
    nssm install $ServiceName $PythonExe $Arguments

    # Configure working directory
    nssm set $ServiceName AppDirectory $ProjectDir

    # Configure logging
    nssm set $ServiceName AppStdout "$LogDir\$LogFile"
    nssm set $ServiceName AppStderr "$LogDir\$LogFile"
    nssm set $ServiceName AppStdoutCreationDisposition 4
    nssm set $ServiceName AppStderrCreationDisposition 4
    nssm set $ServiceName AppRotateFiles 1
    nssm set $ServiceName AppRotateBytes 10485760

    # Set restart behavior
    nssm set $ServiceName AppRestartDelay 5000

    # Set description
    nssm set $ServiceName Description $Description

    # Set to start automatically
    nssm set $ServiceName Start SERVICE_AUTO_START

    # Set environment variables (critical for services running under Local System)
    nssm set $ServiceName AppEnvironmentExtra "LOCALAPPDATA=$LocalAppData" "USERPROFILE=$UserProfile" "HOME=$UserProfile"

    Write-Host "Installed $ServiceName successfully" -ForegroundColor Green
}

# Install services
Install-NSSMService -ServiceName "HadleyAPI" `
    -Arguments "-m uvicorn hadley_api.main:app --host 0.0.0.0 --port 8100" `
    -Description "Hadley API - Local API proxy for Peter" `
    -LogFile "hadley_api.log"

Install-NSSMService -ServiceName "DiscordBot" `
    -Arguments "bot.py" `
    -Description "Discord Messenger Bot with APScheduler" `
    -LogFile "discord_bot.log"

Install-NSSMService -ServiceName "PeterDashboard" `
    -Arguments "peter_dashboard/app.py" `
    -Description "Peter Dashboard - Service status and controls" `
    -LogFile "peter_dashboard.log"

# Start services
Write-Host "`nStarting services..." -ForegroundColor Cyan
nssm start HadleyAPI
nssm start DiscordBot
nssm start PeterDashboard

# Wait and verify
Write-Host "`nWaiting 5 seconds for services to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Check status
Write-Host "`nService Status:" -ForegroundColor Cyan
Get-Service HadleyAPI, DiscordBot, PeterDashboard | Format-Table Name, Status, StartType

# Test endpoints
Write-Host "`nTesting endpoints..." -ForegroundColor Cyan

try {
    $health = Invoke-RestMethod -Uri "http://localhost:8100/health" -TimeoutSec 5
    Write-Host "HadleyAPI health: OK" -ForegroundColor Green
} catch {
    Write-Host "HadleyAPI health: FAILED - $($_.Exception.Message)" -ForegroundColor Red
}

try {
    $dashboard = Invoke-WebRequest -Uri "http://localhost:5000/" -TimeoutSec 5
    Write-Host "PeterDashboard: OK (Status $($dashboard.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "PeterDashboard: FAILED - $($_.Exception.Message)" -ForegroundColor Red
}

# Check Discord bot connection
Write-Host "`nChecking Discord bot logs..." -ForegroundColor Cyan
$botLog = Get-Content "$LogDir\discord_bot.log" -ErrorAction SilentlyContinue
if ($botLog -match "connected to Gateway") {
    Write-Host "DiscordBot: Connected to Discord Gateway" -ForegroundColor Green
} else {
    Write-Host "DiscordBot: Waiting for connection..." -ForegroundColor Yellow
}

# Check bot's app log
$appLogPath = "$LocalAppData\discord-assistant\logs\$(Get-Date -Format 'yyyy-MM-dd').log"
if (Test-Path $appLogPath) {
    $recentLog = Get-Content $appLogPath -Tail 5 -ErrorAction SilentlyContinue
    if ($recentLog) {
        Write-Host "Recent bot activity found in app log" -ForegroundColor Green
    }
}

Write-Host "`nSetup complete!" -ForegroundColor Green
Write-Host "Log files are in: $LogDir" -ForegroundColor Cyan
Write-Host "Bot app logs are in: $LocalAppData\discord-assistant\logs\" -ForegroundColor Cyan
