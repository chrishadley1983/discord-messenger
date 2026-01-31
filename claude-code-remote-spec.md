# Claude Code Remote Control Domain - Technical Spec

**Project:** discord-assistant (new domain)  
**Purpose:** Remote control of Claude Code sessions via Discord  
**Target:** Windows/Linux machine running Claude Code in tmux  
**LLM Cost:** $0 (pattern matching only)

---

## Overview

A new domain for the discord-assistant bot that allows Chris to:
1. Send prompts to Claude Code sessions remotely
2. View session output
3. Start/stop sessions
4. Receive notifications when Claude Code needs input

No LLM required - direct pattern matching routes commands to tmux.

---

## Architecture

```
Discord #claude-code
        │
        ▼
┌─────────────────────┐
│      bot.py         │
│  (channel router)   │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ claude_code/router  │
│ (pattern matching)  │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ claude_code/tools   │
│ (tmux commands)     │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│   tmux sessions     │
│  ┌───────────────┐  │
│  │claude-hadley  │  │
│  │claude-family..│  │
│  └───────────────┘  │
└─────────────────────┘


Notification flow (reverse):

┌─────────────────────┐
│   Claude Code       │
│   needs input       │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│  Notification hook  │
│  (curl to webhook)  │
└─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ Discord #claude-code│
│ "🔔 needs input"    │
└─────────────────────┘
```

---

## File Structure

```
domains/
└── claude_code/
    ├── __init__.py
    ├── config.py
    ├── router.py
    └── tools.py
```

---

## Implementation

### `config.py`

```python
import os

CHANNEL_ID = int(os.environ.get("CLAUDE_CODE_CHANNEL_ID", 0))
SESSION_PREFIX = "claude-"
DEFAULT_SCREEN_LINES = 40
```

---

### `tools.py`

```python
import subprocess
import os
from typing import Optional
from .config import SESSION_PREFIX


def get_sessions() -> list[str]:
    """List active Claude Code tmux sessions"""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return []
        return [
            s for s in result.stdout.strip().split("\n")
            if s.startswith(SESSION_PREFIX)
        ]
    except FileNotFoundError:
        return []


def short_name(session: str) -> str:
    """Get display name without prefix"""
    return session.replace(SESSION_PREFIX, "")


def send_prompt(prompt: str, session: Optional[str] = None) -> str:
    """Send a prompt to Claude Code session via tmux"""
    sessions = get_sessions()
    if not sessions:
        return "❌ No active Claude Code sessions"
    
    target = session if session in sessions else sessions[0]
    
    # Send the text (literal mode to handle special chars)
    subprocess.run(["tmux", "send-keys", "-t", target, "-l", prompt])
    # Press enter
    subprocess.run(["tmux", "send-keys", "-t", target, "Enter"])
    
    return f"📤 **[{short_name(target)}]** Sent"


def get_screen(session: Optional[str] = None, lines: int = 40) -> str:
    """Capture recent output from Claude Code session"""
    sessions = get_sessions()
    if not sessions:
        return "❌ No active Claude Code sessions"
    
    target = session if session in sessions else sessions[0]
    
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", target, "-p", "-S", f"-{lines}"],
        capture_output=True,
        text=True
    )
    
    output = result.stdout.strip()
    if not output:
        output = "(empty)"
    
    # Truncate for Discord (2000 char limit minus formatting)
    if len(output) > 1850:
        output = output[-1850:]
    
    return f"📺 **[{short_name(target)}]**\n```ansi\n{output}\n```"


def start_session(path: str) -> str:
    """Start a new Claude Code session in tmux"""
    path = os.path.expanduser(path)
    
    if not os.path.isdir(path):
        return f"❌ Directory not found: `{path}`"
    
    name = f"{SESSION_PREFIX}{os.path.basename(path)}"
    
    if name in get_sessions():
        return f"⚠️ Session `{name}` already exists"
    
    result = subprocess.run(
        ["tmux", "new-session", "-d", "-s", name, "-c", path],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        return f"❌ Failed to create session: {result.stderr}"
    
    subprocess.run(["tmux", "send-keys", "-t", name, "claude", "Enter"])
    
    return f"🚀 Started `{name}`"


def stop_session(session: str) -> str:
    """Stop a Claude Code tmux session"""
    if not session.startswith(SESSION_PREFIX):
        session = f"{SESSION_PREFIX}{session}"
    
    sessions = get_sessions()
    if session not in sessions:
        return f"❌ Session `{session}` not found"
    
    subprocess.run(["tmux", "kill-session", "-t", session])
    return f"🛑 Stopped `{session}`"


def approve(session: Optional[str] = None) -> str:
    """Send 'y' to approve a permission request"""
    sessions = get_sessions()
    if not sessions:
        return "❌ No active Claude Code sessions"
    
    target = session if session in sessions else sessions[0]
    subprocess.run(["tmux", "send-keys", "-t", target, "y"])
    return f"✅ **[{short_name(target)}]** Approved"


def deny(session: Optional[str] = None) -> str:
    """Send 'n' to deny a permission request"""
    sessions = get_sessions()
    if not sessions:
        return "❌ No active Claude Code sessions"
    
    target = session if session in sessions else sessions[0]
    subprocess.run(["tmux", "send-keys", "-t", target, "n"])
    return f"❌ **[{short_name(target)}]** Denied"


def escape(session: Optional[str] = None) -> str:
    """Send Escape key (cancel/interrupt)"""
    sessions = get_sessions()
    if not sessions:
        return "❌ No active Claude Code sessions"
    
    target = session if session in sessions else sessions[0]
    subprocess.run(["tmux", "send-keys", "-t", target, "Escape"])
    return f"⏹️ **[{short_name(target)}]** Escaped"
```

---

### `router.py`

```python
import re
from .tools import (
    get_sessions,
    send_prompt,
    get_screen,
    start_session,
    stop_session,
    approve,
    deny,
    escape,
    short_name,
)
from .config import DEFAULT_SCREEN_LINES, SESSION_PREFIX


# Track active session (persists in memory)
_active_session: str | None = None


def get_active_session() -> str | None:
    """Get the current active session, validating it still exists"""
    global _active_session
    if _active_session and _active_session in get_sessions():
        return _active_session
    _active_session = None
    return None


def set_active_session(session: str) -> str:
    """Set the active session"""
    global _active_session
    
    if not session.startswith(SESSION_PREFIX):
        session = f"{SESSION_PREFIX}{session}"
    
    sessions = get_sessions()
    if session not in sessions:
        available = ", ".join(short_name(s) for s in sessions) if sessions else "none"
        return f"❌ Session `{session}` not found. Available: {available}"
    
    _active_session = session
    return f"🎯 Now targeting **[{short_name(session)}]**"


def get_target_session() -> str | None:
    """Get session to use: active if set, otherwise first available"""
    active = get_active_session()
    if active:
        return active
    sessions = get_sessions()
    return sessions[0] if sessions else None


def handle_message(msg: str) -> str:
    """
    Route Discord message to appropriate action.
    No LLM - pattern matching only.
    """
    text = msg.strip()
    lower = text.lower()
    
    # === Active session management ===
    
    # Set active session: "use hadley" or "use claude-hadley"
    if match := re.match(r"^use\s+(.+)$", lower):
        return set_active_session(match.group(1).strip())
    
    # Show current target
    if lower in ["target", "current", "which"]:
        active = get_active_session()
        if active:
            return f"🎯 Currently targeting **[{short_name(active)}]**"
        sessions = get_sessions()
        if sessions:
            return f"🎯 No active target, will use **[{short_name(sessions[0])}]** (first available)"
        return "❌ No active Claude Code sessions"
    
    # === Session management ===
    
    # List sessions
    if lower in ["sessions", "list", "ls"]:
        sessions = get_sessions()
        if not sessions:
            return "No active Claude Code sessions"
        active = get_active_session()
        lines = []
        for s in sessions:
            marker = " ← active" if s == active else ""
            lines.append(f"• `{short_name(s)}`{marker}")
        return "**Sessions:**\n" + "\n".join(lines)
    
    # View screen/output
    if lower in ["screen", "output", "show", "view", "s"]:
        return get_screen(session=get_target_session(), lines=DEFAULT_SCREEN_LINES)
    
    # View more lines: "screen 100"
    if match := re.match(r"^(?:screen|output|show|view|s)\s+(\d+)$", lower):
        lines = min(int(match.group(1)), 200)
        return get_screen(session=get_target_session(), lines=lines)
    
    # Start session: "start /path/to/project"
    if match := re.match(r"^start\s+(.+)$", text, re.IGNORECASE):
        return start_session(match.group(1).strip())
    
    # Stop session: "stop claude-hadley" or "stop hadley"
    if match := re.match(r"^stop\s+(.+)$", lower):
        return stop_session(match.group(1).strip())
    
    # === Quick actions ===
    
    # Approve permission
    if lower in ["y", "yes", "approve", "ok", "allow"]:
        return approve(session=get_target_session())
    
    # Deny permission
    if lower in ["n", "no", "deny", "reject", "block"]:
        return deny(session=get_target_session())
    
    # Escape/cancel
    if lower in ["esc", "escape", "cancel"]:
        return escape(session=get_target_session())
    
    # === Slash commands / skills passthrough ===
    
    # Forward slash commands directly: "/compact", "/clear", etc.
    if text.startswith("/"):
        return send_prompt(text, session=get_target_session())
    
    # Trigger skill by name: "skill test-plan" -> "/test-plan"
    if match := re.match(r"^skill\s+(.+)$", lower):
        skill_name = match.group(1).strip()
        return send_prompt(f"/{skill_name}", session=get_target_session())
    
    # === Default: forward as prompt ===
    
    return send_prompt(text, session=get_target_session())
```

---

### `__init__.py`

```python
from .router import handle_message
from .config import CHANNEL_ID

__all__ = ["handle_message", "CHANNEL_ID"]
```

---

## Bot Integration

Add to `bot.py`:

```python
from domains.claude_code import handle_message as handle_claude_code, CHANNEL_ID as CLAUDE_CODE_CHANNEL

@bot.event
async def on_message(message):
    # Ignore own messages
    if message.author == bot.user:
        return
    
    # Claude Code domain - direct routing, no LLM
    if message.channel.id == CLAUDE_CODE_CHANNEL:
        response = handle_claude_code(message.content)
        await message.channel.send(response)
        return
    
    # ... other domain routing (nutrition, news, etc.)
```

---

## Notification Hook

### Simple version

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "curl -s -H 'Content-Type: application/json' -d '{\"content\":\"🔔 Claude Code needs input\"}' YOUR_WEBHOOK_URL"
          }
        ]
      }
    ]
  }
}
```

### Rich version with project tag

Create `~/.claude/hooks/discord-notify.sh`:

```bash
#!/bin/bash

WEBHOOK_URL="${DISCORD_WEBHOOK_CLAUDE_CODE}"

# Read hook payload from stdin
INPUT=$(cat)

# Extract message if available
MESSAGE=$(echo "$INPUT" | jq -r '.message // "needs your input"' 2>/dev/null)
PROJECT=$(basename "$(pwd)")

# Send to Discord with project tag
curl -s -H "Content-Type: application/json" \
  -d "{\"content\":\"🔔 **[${PROJECT}]** ${MESSAGE}\"}" \
  "$WEBHOOK_URL"
```

Make executable and reference in settings:

```bash
chmod +x ~/.claude/hooks/discord-notify.sh
```

```json
{
  "hooks": {
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/hooks/discord-notify.sh"
          }
        ]
      }
    ]
  }
}
```

---

## Command Reference

| Command | Action |
|---------|--------|
| `use hadley` | Set active session to `claude-hadley` |
| `target` / `current` / `which` | Show current target session |
| `sessions` / `list` / `ls` | List active sessions (marks active) |
| `screen` / `view` / `s` | Show last 40 lines of output |
| `screen 100` | Show last 100 lines |
| `start /path/to/project` | Start new Claude Code session |
| `stop hadley` | Stop session (prefix added automatically) |
| `y` / `yes` / `approve` | Send 'y' to approve permission |
| `n` / `no` / `deny` | Send 'n' to deny permission |
| `esc` / `escape` / `cancel` | Send Escape key |
| `/compact` | Forward slash command to Claude Code |
| `skill test-plan` | Trigger skill as `/test-plan` |
| (anything else) | Forward as prompt to Claude Code |

---

## Example Flow

```
[On phone, via Discord]

Chris: sessions
Bot:   **Sessions:**
       • `hadley-bricks`
       • `familyfuel`

Chris: use hadley
Bot:   🎯 Now targeting **[hadley-bricks]**

Chris: check the eBay rate limiting logic
Bot:   📤 **[hadley-bricks]** Sent

[Notification arrives]
Bot:   🔔 **[hadley-bricks]** Permission requested: Read src/api/ebay.ts

Chris: y
Bot:   ✅ **[hadley-bricks]** Approved

Chris: screen
Bot:   📺 **[hadley-bricks]**
       ```ansi
       The rate limiting is implemented in...
       Ready for next instruction...
       ```

Chris: start ~/projects/new-thing
Bot:   🚀 Started `claude-new-thing`
```

---

## Prerequisites

- **tmux** installed on the machine running Claude Code
- **jq** installed (for notification hook)
- **curl** available
- Discord bot running with access to the channel
- Claude Code sessions started inside tmux with naming convention `claude-{project}`

---

## Starting Sessions Manually

If you need to start a session outside of Discord:

```bash
# Create session
tmux new-session -d -s claude-hadley-bricks -c /home/chris/hadley-bricks

# Start Claude Code in it
tmux send-keys -t claude-hadley-bricks "claude" Enter

# Attach to view directly (optional)
tmux attach -t claude-hadley-bricks
```

---

## Error Handling

| Error | Response |
|-------|----------|
| No tmux sessions | "❌ No active Claude Code sessions" |
| Session not found | "❌ Session `{name}` not found" |
| Directory not found | "❌ Directory not found: `{path}`" |
| Session already exists | "⚠️ Session `{name}` already exists" |
| tmux not installed | "❌ No active Claude Code sessions" (fails silently) |

---

## Security Notes

- Only you have access to the Discord channel
- tmux sessions run with your user permissions
- No credentials stored in the bot
- Webhook URL should be kept private

---

## Implementation Order

1. Create `domains/claude_code/` folder structure
2. Implement `tools.py` - test tmux commands manually first
3. Implement `router.py` - test pattern matching
4. Add to `bot.py` routing
5. Set up Discord channel and webhook
6. Configure Claude Code notification hook
7. Test end-to-end flow

---

## Future Phases Compatibility

This spec is the foundation for Peterbot. Future phases build on top:

| Phase | What | Relationship to Pre-A |
|-------|------|----------------------|
| Pre-B | Session management | Extends tools.py with persistence |
| Pre-C | Voice/Android Auto | Adds Flask endpoint, same router |
| Ph 0 | Claude-mem install | Orthogonal - hooks into CC lifecycle |
| Ph 1-5 | Personality memory | Fork claude-mem, add capture in relay |

**Key insight:** Claude-mem hooks into Claude Code's internal events (`post-tool-use`, `user-message`), not the transport layer. The relay just simulates keyboard input - observations will be captured regardless of whether you typed directly or sent via Discord.

**Note for Phase 1-5:** Discord messages themselves aren't captured by claude-mem's default hooks. You'll want to add a capture point in the relay layer to feed interaction data to the forked memory system.
