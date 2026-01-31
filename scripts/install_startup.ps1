# Install Discord Assistant as a Windows startup task
# Run this script as Administrator

$taskName = "DiscordAssistant"
$projectPath = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$pythonwPath = (Get-Command pythonw -ErrorAction SilentlyContinue).Source

if (-not $pythonwPath) {
    # Try to find pythonw in common locations
    $possiblePaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311\pythonw.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python310\pythonw.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe",
        "C:\Python311\pythonw.exe",
        "C:\Python310\pythonw.exe"
    )

    foreach ($path in $possiblePaths) {
        if (Test-Path $path) {
            $pythonwPath = $path
            break
        }
    }
}

if (-not $pythonwPath) {
    Write-Error "pythonw.exe not found. Please ensure Python is installed."
    exit 1
}

Write-Host "Using Python: $pythonwPath"
Write-Host "Project path: $projectPath"

# Create the scheduled task
$action = New-ScheduledTaskAction -Execute $pythonwPath -Argument "bot.py" -WorkingDirectory $projectPath
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Remove existing task if present
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# Register new task
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Discord Personal Assistant Bot"

Write-Host "✅ Startup task '$taskName' created successfully"
Write-Host "The bot will start automatically when you log in."
Write-Host ""
Write-Host "To start the bot now, run:"
Write-Host "  pythonw bot.py"
Write-Host ""
Write-Host "To check the task:"
Write-Host "  schtasks /query /tn `"$taskName`""
