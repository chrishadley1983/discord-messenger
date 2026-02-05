# Claude Code Task Management Functions
# Add to your PowerShell profile: . "C:\Users\Chris Hadley\Discord-Messenger\scripts\claude-task-functions.ps1"
#
# Or add these functions directly to your $PROFILE file:
#   notepad $PROFILE
#   (paste the functions below)

# Set a shared task list ID for multi-session coordination
function Set-ClaudeTaskList {
    param([string]$Name)
    $env:CLAUDE_CODE_TASK_LIST_ID = $Name
    Write-Host "Task list set to: $Name" -ForegroundColor Green
    Write-Host "All Claude Code sessions in this terminal will share this task list." -ForegroundColor DarkGray
}

# Clear the task list ID to use session-scoped tasks
function Clear-ClaudeTaskList {
    Remove-Item Env:\CLAUDE_CODE_TASK_LIST_ID -ErrorAction SilentlyContinue
    Write-Host "Task list cleared - using session-scoped tasks" -ForegroundColor Yellow
}

# Show current task list ID
function Get-ClaudeTaskList {
    if ($env:CLAUDE_CODE_TASK_LIST_ID) {
        Write-Host "Current task list: $env:CLAUDE_CODE_TASK_LIST_ID" -ForegroundColor Cyan
    } else {
        Write-Host "No shared task list set (using session-scoped tasks)" -ForegroundColor DarkGray
    }
}

# Aliases for quick access
Set-Alias -Name ctask -Value Set-ClaudeTaskList
Set-Alias -Name ctaskclear -Value Clear-ClaudeTaskList
Set-Alias -Name ctaskshow -Value Get-ClaudeTaskList

# Project-specific task list shortcuts
function Start-HadleyBricksFeature {
    param(
        [Parameter(Mandatory=$true)]
        [string]$FeatureName
    )
    Set-ClaudeTaskList "hb-$FeatureName"
    Set-Location "C:\Users\Chris Hadley\hadley-bricks-inventory-management"
    Write-Host "Working directory: $(Get-Location)" -ForegroundColor DarkGray
}

function Start-PeterbotFeature {
    param(
        [Parameter(Mandatory=$true)]
        [string]$FeatureName
    )
    Set-ClaudeTaskList "pb-$FeatureName"
    Set-Location "C:\Users\Chris Hadley\Discord-Messenger"
    Write-Host "Working directory: $(Get-Location)" -ForegroundColor DarkGray
}

# Aliases for project shortcuts
Set-Alias -Name hbfeature -Value Start-HadleyBricksFeature
Set-Alias -Name pbfeature -Value Start-PeterbotFeature

# Usage examples (displayed when sourcing the file)
Write-Host ""
Write-Host "Claude Code Task Management Functions Loaded" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Commands:" -ForegroundColor Cyan
Write-Host "  ctask <name>       - Set shared task list (e.g., ctask inventory-export)"
Write-Host "  ctaskclear         - Clear task list (use session-scoped tasks)"
Write-Host "  ctaskshow          - Show current task list"
Write-Host ""
Write-Host "Project shortcuts:" -ForegroundColor Cyan
Write-Host "  hbfeature <name>   - Start Hadley Bricks feature (sets task list + cd)"
Write-Host "  pbfeature <name>   - Start Peterbot feature (sets task list + cd)"
Write-Host ""
Write-Host "Examples:" -ForegroundColor DarkGray
Write-Host "  ctask inventory-export    # Terminal 1: implementation"
Write-Host "  ctask inventory-export    # Terminal 2: testing (shares tasks)"
Write-Host "  hbfeature ebay-sync       # Quick start for HB feature"
Write-Host ""
