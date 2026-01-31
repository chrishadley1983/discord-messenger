# Uninstall Discord Assistant startup task
# Run this script as Administrator

$taskName = "DiscordAssistant"

$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($task) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "✅ Startup task '$taskName' removed successfully"
} else {
    Write-Host "Task '$taskName' not found"
}
