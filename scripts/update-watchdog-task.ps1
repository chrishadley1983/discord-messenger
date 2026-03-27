$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"C:\Users\Chris Hadley\claude-projects\Discord-Messenger\scripts\run-watchdog-hidden.vbs`""
Set-ScheduledTask -TaskName "HadleyAPI-Watchdog" -Action $action
Write-Host "Updated. New action:"
Get-ScheduledTask -TaskName 'HadleyAPI-Watchdog' | Select-Object -ExpandProperty Actions | Format-List
