' Silent startup script for Peterbot services
' Add shortcut to this file in shell:startup for auto-start on boot

Set WshShell = CreateObject("WScript.Shell")
strPath = "C:\Users\Chris Hadley\Discord-Messenger"

' Start Hadley API
WshShell.CurrentDirectory = strPath
WshShell.Run "python -m uvicorn hadley_api.main:app --host 0.0.0.0 --port 8100", 0, False

' Wait 3 seconds
WScript.Sleep 3000

' Start Peter Dashboard
WshShell.Run "python peter_dashboard/app.py", 0, False

' Wait 2 seconds
WScript.Sleep 2000

' Start Discord Bot
WshShell.Run "python bot.py", 0, False

' Wait 3 seconds
WScript.Sleep 3000

' Start Peter tmux session in WSL
WshShell.Run "wsl -d Ubuntu -u chris_hadley -- bash -c ""tmux has-session -t peter 2>/dev/null || tmux new-session -d -s peter -c /home/chris_hadley/peterbot 'claude --dangerously-skip-permissions'""", 0, False

' Done - show notification (optional)
' MsgBox "Peterbot services started!", vbInformation, "Peterbot Startup"
