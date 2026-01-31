' Discord-Messenger Bot - Silent Startup Script
' This VBS wrapper runs the bot without showing a command window

Set WshShell = CreateObject("WScript.Shell")
WshShell.Run chr(34) & "C:\Users\Chris Hadley\Discord-Messenger\start-bot.bat" & chr(34), 0
Set WshShell = Nothing
