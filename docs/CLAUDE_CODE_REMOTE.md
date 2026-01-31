# Claude Code Remote Control Domain

**Status:** Implemented
**Channel:** #claude-actions (ID: 1466732449525530818)
**LLM Cost:** $0 (pattern matching only)

## Overview

This domain enables remote control of Claude Code tmux sessions via Discord. Unlike other domains that route through Claude for AI responses, this domain uses direct pattern matching to execute commands immediately.

## Architecture

```
Discord #claude-actions
        |
        v
+---------------------+
|      bot.py         |
|  (special routing)  |
+---------------------+
        |
        v
+---------------------+
| claude_code/router  |
| (pattern matching)  |
+---------------------+
        |
        v
+---------------------+
| claude_code/tools   |
| (tmux commands)     |
+---------------------+
        |
        v
+---------------------+
|   tmux sessions     |
|  +---------------+  |
|  |claude-hadley  |  |
|  |claude-project |  |
|  +---------------+  |
+---------------------+
```

## Files Created

| File | Purpose |
|------|---------|
| `domains/claude_code/__init__.py` | Exports `handle_message` and `CHANNEL_ID` |
| `domains/claude_code/config.py` | Channel ID, session prefix, screen lines config |
| `domains/claude_code/tools.py` | Tmux subprocess functions |
| `domains/claude_code/router.py` | Pattern matching message handler |

## Files Modified

| File | Change |
|------|--------|
| `bot.py` | Added import and special routing for claude_code channel |
| `.env.example` | Added `CLAUDE_CODE_CHANNEL_ID` and `DISCORD_WEBHOOK_CLAUDE_CODE` |

## Command Reference

| Command | Action |
|---------|--------|
| `@hadley: prompt` | Send prompt to session matching "hadley" |
| `@discord:` | Show screen for session matching "discord" |
| `use hadley` | Set active session to `claude-hadley` |
| `target` / `current` / `which` | Show current target session |
| `sessions` / `list` / `ls` | List active sessions (marks active) |
| `screen` / `view` / `s` | Show last 40 lines of output |
| `screen 100` | Show last 100 lines (max 200) |
| `start /path/to/project` | Start new Claude Code session |
| `stop hadley` | Stop session (prefix added automatically) |
| `y` / `yes` / `approve` | Send 'y' to approve permission |
| `n` / `no` / `deny` | Send 'n' to deny permission |
| `esc` / `escape` / `cancel` | Send Escape key |
| `/compact` | Forward slash command to Claude Code |
| `skill commit` | Trigger skill as `/commit` |
| (anything else) | Forward as prompt to Claude Code |

## Environment Variables

Add to `.env`:

```bash
CLAUDE_CODE_CHANNEL_ID=1466732449525530818
DISCORD_WEBHOOK_CLAUDE_CODE=https://discord.com/api/webhooks/...
```

## Notification Hook Setup (Optional)

For bi-directional communication, set up a Claude Code notification hook.

### 1. Create the hook script

Create `~/.claude/hooks/discord-notify.sh`:

```bash
#!/bin/bash
WEBHOOK_URL="${DISCORD_WEBHOOK_CLAUDE_CODE}"
INPUT=$(cat)
MESSAGE=$(echo "$INPUT" | jq -r '.message // "needs your input"' 2>/dev/null)
PROJECT=$(basename "$(pwd)")
curl -s -H "Content-Type: application/json" \
  -d "{\"content\":\"**[${PROJECT}]** ${MESSAGE}\"}" \
  "$WEBHOOK_URL"
```

Make it executable:
```bash
chmod +x ~/.claude/hooks/discord-notify.sh
```

### 2. Configure Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Notification": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "bash ~/.claude/hooks/discord-notify.sh"
      }]
    }]
  }
}
```

## Platform: VS Code + CLI for Remote

**Setup:**
- **Primary**: VS Code Claude Code extension (at desk)
- **Remote**: CLI in tmux via VS Code's WSL terminal (when heading out)

**Workflow:**
1. Normal work: Use extension as usual
2. Before leaving: Open VS Code terminal → start tmux session → `claude`
3. Remote: Control via Discord bot
4. Return: Continue in CLI or close tmux and switch back to extension

**Note:** Extension and CLI sessions don't share history - fresh context when switching. Mitigate with `/compact` summary before switching if needed.

## Starting Sessions

Add this alias to your `~/.bashrc` or `~/.zshrc` in WSL:

```bash
# Quick switch to remote-controllable Claude Code
ccremote() {
    tmux new-session -s "claude-${PWD##*/}" -c "$PWD" \; send-keys "claude" Enter
}
```

Then before leaving your desk:
```bash
cd ~/hadley-bricks
ccremote
# Detach with Ctrl+B, D
```

Sessions follow the naming convention `claude-{project}`:

```bash
# Manual method
tmux new-session -d -s claude-hadley-bricks -c /home/chris/hadley-bricks
tmux send-keys -t claude-hadley-bricks "claude" Enter

# Attach to view directly (optional)
tmux attach -t claude-hadley-bricks
```

Or via Discord:
```
start ~/hadley-bricks
```

## Example Flow

```
[On phone, via Discord #claude-actions]

Chris: sessions
Bot:   **Sessions:**
       - `hadley-bricks`
       - `discord-messenger`

Chris: @hadley: check the eBay rate limiting logic
Bot:   **[hadley-bricks]** Sent

[Notification arrives]
Bot:   **[hadley-bricks]** Permission requested: Read src/api/ebay.ts

Chris: y
Bot:   **[hadley-bricks]** Approved

Chris: @hadley:
Bot:   **[hadley-bricks]**
       ```ansi
       The rate limiting is implemented in...
       Ready for next instruction...
       ```

Chris: @discord: add dark mode support
Bot:   **[discord-messenger]** Sent
```

## Key Design Decisions

1. **No LLM routing** - Direct pattern matching keeps costs at $0 and response instant
2. **Special bot.py routing** - Bypasses the standard domain registry since this domain doesn't use Claude
3. **Session state in memory** - Active session tracked in `_active_session` module variable
4. **Graceful degradation** - All functions handle missing tmux/sessions gracefully
5. **Discord length limits** - Output truncated to 1850 chars for safe 2000 char message limit

## Prerequisites

- **tmux** installed in WSL
- **jq** installed (for notification hook)
- **curl** available
- Discord webhook URL for notifications
- Claude Code sessions started inside tmux with naming convention `claude-{project}`
