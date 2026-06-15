$ErrorActionPreference = 'Stop'
Write-Host "=== Prolific re-login helper ===" -ForegroundColor Cyan
Write-Host ""

Write-Host "1/5  Stopping DiscordBot service..."
Stop-Service DiscordBot
Write-Host "     done" -ForegroundColor Green

Write-Host "2/5  Killing any Chrome-Prolific processes..."
$killed = 0
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
    Where-Object { $_.CommandLine -like '*Chrome-Prolific*' } |
    ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force; $killed++ } catch {}
    }
Write-Host "     killed $killed Chrome-Prolific process(es)" -ForegroundColor Green
Start-Sleep -Seconds 1

Write-Host ""
Write-Host "3/5  Launching login script. A Chrome window will pop up." -ForegroundColor Yellow
Write-Host "     Log in to Prolific in that window, then go to https://app.prolific.com/studies"
Write-Host "     The script will auto-exit once it detects /studies."
Write-Host ""
Set-Location "C:\Users\Chris Hadley\claude-projects\discord-messenger"
python -m domains.prolific.login

Write-Host ""
Write-Host "4/5  Restarting DiscordBot service..."
Start-Service DiscordBot
Write-Host "     done" -ForegroundColor Green

Write-Host ""
Write-Host "5/5  All done. Close this window when you're ready." -ForegroundColor Cyan
Read-Host "Press Enter to close"
