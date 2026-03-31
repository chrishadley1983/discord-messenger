# Register WSL Watchdog as a Windows Scheduled Task
# Run this script as Administrator

$scriptPath = "C:\Users\Chris Hadley\claude-projects\discord-messenger\scripts\wsl-watchdog.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 365)

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName "WSL Watchdog" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Description "Monitors WSL health every 5 min. Restarts WSL and channel sessions if unresponsive. Alerts to Discord #alerts." -Force

Write-Host "WSL Watchdog registered successfully"
Get-ScheduledTask -TaskName "WSL Watchdog" | Select-Object TaskName, State
