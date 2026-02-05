# Start tmux sessions for Peterbot system
# Run this at Windows startup via Task Scheduler

$WslDistro = "Ubuntu"
$WslUser = "chris_hadley"

# Session configurations
$Sessions = @(
    @{
        Name = "claude-peterbot"
        Path = "/home/chris_hadley/peterbot"
        Command = "claude --dangerously-skip-permissions"
    },
    @{
        Name = "claude-discord"
        Path = "/mnt/c/Users/Chris Hadley/Discord-Messenger"
        Command = "claude --dangerously-skip-permissions"
    }
)

Write-Host "Starting tmux sessions..." -ForegroundColor Cyan

foreach ($session in $Sessions) {
    $name = $session.Name
    $path = $session.Path
    $cmd = $session.Command

    # Check if session already exists
    $check = wsl -d $WslDistro -u $WslUser -- tmux has-session -t $name 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Session '$name' already exists" -ForegroundColor Yellow
    } else {
        Write-Host "  Creating session '$name'..." -ForegroundColor Green
        wsl -d $WslDistro -u $WslUser -- tmux new-session -d -s $name -c $path $cmd
        if ($LASTEXITCODE -eq 0) {
            Write-Host "    Started: $name -> $path" -ForegroundColor Green
        } else {
            Write-Host "    Failed to create session '$name'" -ForegroundColor Red
        }
    }
}

Write-Host "`nDone! Sessions:" -ForegroundColor Cyan
wsl -d $WslDistro -u $WslUser -- tmux list-sessions
