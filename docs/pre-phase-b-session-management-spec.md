# Pre-Phase B: Session Management - Technical Spec

**Project:** discord-assistant (claude_code domain enhancement)  
**Purpose:** Persistent session handling across restarts, project shortcuts, activity tracking  
**Prerequisite:** Pre-Phase A complete  
**Complexity:** Low-medium (few hours)

---

## Overview

Extends the claude_code domain with:
1. **Session persistence** - Active session survives bot restart
2. **Project registry** - Friendly names map to paths (`hadley` → full path)
3. **Auto-reconnect** - Bot startup scans for existing tmux sessions
4. **Activity tracking** - Last interaction timestamp per session
5. **Session state** - Know if session is idle/working/waiting

---

## Current State (Pre-A)

- Sessions are manual: user starts tmux, user starts claude
- Active session tracking is in-memory (`_active_session` in router.py)
- Lost on bot restart
- Must type full paths for `start`

---

## File Structure

```
domains/
└── claude_code/
    ├── __init__.py        # Update exports
    ├── config.py          # Add new config
    ├── router.py          # Update to use store
    ├── tools.py           # Unchanged from Pre-A
    ├── session_store.py   # NEW - persistence layer
    └── projects.py        # NEW - project registry
data/
└── claude_sessions.json   # NEW - state file (gitignored)
```

---

## Implementation

### `config.py` (updated)

```python
import os
from pathlib import Path

CHANNEL_ID = int(os.environ.get("CLAUDE_CODE_CHANNEL_ID", 0))
SESSION_PREFIX = "claude-"
DEFAULT_SCREEN_LINES = 40

# Pre-B additions
DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
SESSION_STORE_PATH = DATA_DIR / "claude_sessions.json"
```

---

### `projects.py` (new)

```python
"""
Project registry - friendly names to paths.
Stored in JSON for persistence. Manage via Discord commands.
"""

import json
from pathlib import Path
from typing import Optional
from .config import DATA_DIR


PROJECTS_PATH = DATA_DIR / "projects.json"


def _load() -> dict[str, str]:
    """Load projects from disk."""
    if PROJECTS_PATH.exists():
        try:
            return json.loads(PROJECTS_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save(projects: dict[str, str]):
    """Save projects to disk."""
    PROJECTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROJECTS_PATH.write_text(json.dumps(projects, indent=2))


def resolve_path(name_or_path: str) -> str:
    """
    Resolve a project name to its path.
    If not found in registry, returns the input unchanged (assumes it's a path).
    """
    projects = _load()
    return projects.get(name_or_path.lower().strip(), name_or_path)


def list_projects() -> dict[str, str]:
    """Return all registered projects."""
    return _load()


def add_project(name: str, path: str) -> str:
    """Add or update a project. Returns confirmation message."""
    projects = _load()
    name = name.lower().strip()
    projects[name] = path
    _save(projects)
    return f"✅ Registered `{name}` → `{path}`"


def remove_project(name: str) -> str:
    """Remove a project. Returns confirmation message."""
    projects = _load()
    name = name.lower().strip()
    if name not in projects:
        return f"❌ Project `{name}` not found"
    del projects[name]
    _save(projects)
    return f"🗑️ Removed `{name}`"


def get_project(name: str) -> Optional[str]:
    """Get path for a project, or None if not found."""
    projects = _load()
    return projects.get(name.lower().strip())
```

---

### `session_store.py` (new)

```python
"""
Persistent session state - survives bot restarts.
Stores: active session, last activity timestamps, session metadata.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from .config import SESSION_STORE_PATH


def _load() -> dict:
    """Load state from disk."""
    if SESSION_STORE_PATH.exists():
        try:
            return json.loads(SESSION_STORE_PATH.read_text())
        except json.JSONDecodeError:
            return _default_state()
    return _default_state()


def _save(state: dict):
    """Save state to disk."""
    SESSION_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_STORE_PATH.write_text(json.dumps(state, indent=2))


def _default_state() -> dict:
    return {
        "active_session": None,
        "last_activity": {},  # session_name → ISO timestamp
        "session_meta": {},   # session_name → {started_at, project_path, ...}
    }


# --- Public API ---

def get_active_session() -> Optional[str]:
    """Get the stored active session name."""
    return _load().get("active_session")


def set_active_session(session: Optional[str]):
    """Set the active session (persists to disk)."""
    state = _load()
    state["active_session"] = session
    _save(state)


def record_activity(session: str):
    """Update last activity timestamp for a session."""
    state = _load()
    state["last_activity"][session] = datetime.now().isoformat()
    _save(state)


def get_last_activity(session: str) -> Optional[str]:
    """Get last activity timestamp for a session."""
    return _load().get("last_activity", {}).get(session)


def get_all_activity() -> dict[str, str]:
    """Get all last activity timestamps."""
    return _load().get("last_activity", {})


def set_session_meta(session: str, **kwargs):
    """Store metadata for a session (started_at, project_path, etc.)."""
    state = _load()
    if session not in state["session_meta"]:
        state["session_meta"][session] = {}
    state["session_meta"][session].update(kwargs)
    _save(state)


def get_session_meta(session: str) -> dict:
    """Get metadata for a session."""
    return _load().get("session_meta", {}).get(session, {})


def clear_session(session: str):
    """Remove all stored data for a session (call when session stops)."""
    state = _load()
    state["last_activity"].pop(session, None)
    state["session_meta"].pop(session, None)
    if state["active_session"] == session:
        state["active_session"] = None
    _save(state)


def clear_stale_sessions(active_sessions: list[str]):
    """Remove stored data for sessions that no longer exist in tmux."""
    state = _load()
    
    # Clean last_activity
    state["last_activity"] = {
        k: v for k, v in state["last_activity"].items() 
        if k in active_sessions
    }
    
    # Clean session_meta
    state["session_meta"] = {
        k: v for k, v in state["session_meta"].items() 
        if k in active_sessions
    }
    
    # Clear active if it's gone
    if state["active_session"] and state["active_session"] not in active_sessions:
        state["active_session"] = None
    
    _save(state)
```

---

### `router.py` (updated)

```python
import re
from datetime import datetime
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
from .projects import resolve_path, list_projects
from . import session_store


def _get_active_session() -> str | None:
    """Get active session, validating it still exists in tmux."""
    stored = session_store.get_active_session()
    if stored and stored in get_sessions():
        return stored
    # Stored session is gone - clear it
    if stored:
        session_store.set_active_session(None)
    return None


def _set_active_session(session: str) -> str:
    """Set the active session (with validation)."""
    if not session.startswith(SESSION_PREFIX):
        session = f"{SESSION_PREFIX}{session}"
    
    sessions = get_sessions()
    if session not in sessions:
        available = ", ".join(short_name(s) for s in sessions) if sessions else "none"
        return f"❌ Session `{session}` not found. Available: {available}"
    
    session_store.set_active_session(session)
    session_store.record_activity(session)
    return f"🎯 Now targeting **[{short_name(session)}]**"


def _get_target_session() -> str | None:
    """Get session to use: active if set, otherwise first available."""
    active = _get_active_session()
    if active:
        return active
    sessions = get_sessions()
    return sessions[0] if sessions else None


def _format_time_ago(iso_timestamp: str) -> str:
    """Format timestamp as relative time."""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        delta = datetime.now() - dt
        
        if delta.total_seconds() < 60:
            return "just now"
        elif delta.total_seconds() < 3600:
            mins = int(delta.total_seconds() / 60)
            return f"{mins}m ago"
        elif delta.total_seconds() < 86400:
            hours = int(delta.total_seconds() / 3600)
            return f"{hours}h ago"
        else:
            days = int(delta.total_seconds() / 86400)
            return f"{days}d ago"
    except:
        return "unknown"


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
        return _set_active_session(match.group(1).strip())
    
    # Show current target
    if lower in ["target", "current", "which"]:
        active = _get_active_session()
        if active:
            last = session_store.get_last_activity(active)
            time_str = f" (last: {_format_time_ago(last)})" if last else ""
            return f"🎯 Currently targeting **[{short_name(active)}]**{time_str}"
        sessions = get_sessions()
        if sessions:
            return f"🎯 No active target, will use **[{short_name(sessions[0])}]** (first available)"
        return "❌ No active Claude Code sessions"
    
    # === Project management (Pre-B) ===
    
    # List registered projects
    if lower in ["projects", "proj"]:
        projects = list_projects()
        if not projects:
            return "No projects registered. Use `addproj <name> <path>` to add one."
        lines = [f"• `{name}` → `{path}`" for name, path in projects.items()]
        return "**Registered projects:**\n" + "\n".join(lines)
    
    # Add project: "addproj hadley /mnt/c/Users/Chris/Projects/hadley-bricks"
    if match := re.match(r"^addproj\s+(\S+)\s+(.+)$", text, re.IGNORECASE):
        name = match.group(1).strip()
        path = match.group(2).strip()
        from .projects import add_project
        return add_project(name, path)
    
    # Remove project: "rmproj hadley"
    if match := re.match(r"^rmproj\s+(\S+)$", lower):
        name = match.group(1).strip()
        from .projects import remove_project
        return remove_project(name)
    
    # Status - all sessions with activity
    if lower in ["status", "stat"]:
        sessions = get_sessions()
        if not sessions:
            return "No active Claude Code sessions"
        
        # Clean up stale stored data
        session_store.clear_stale_sessions(sessions)
        
        active = _get_active_session()
        activity = session_store.get_all_activity()
        
        lines = []
        for s in sessions:
            marker = " ← **active**" if s == active else ""
            last = activity.get(s)
            time_str = f" ({_format_time_ago(last)})" if last else " (no activity)"
            lines.append(f"• `{short_name(s)}`{time_str}{marker}")
        
        return "**Session status:**\n" + "\n".join(lines)
    
    # === Session management ===
    
    # List sessions (simpler than status)
    if lower in ["sessions", "list", "ls"]:
        sessions = get_sessions()
        if not sessions:
            return "No active Claude Code sessions"
        active = _get_active_session()
        lines = []
        for s in sessions:
            marker = " ← active" if s == active else ""
            lines.append(f"• `{short_name(s)}`{marker}")
        return "**Sessions:**\n" + "\n".join(lines)
    
    # View screen/output
    if lower in ["screen", "output", "show", "view", "s"]:
        target = _get_target_session()
        if target:
            session_store.record_activity(target)
        return get_screen(session=target, lines=DEFAULT_SCREEN_LINES)
    
    # View more lines: "screen 100"
    if match := re.match(r"^(?:screen|output|show|view|s)\s+(\d+)$", lower):
        lines = min(int(match.group(1)), 200)
        target = _get_target_session()
        if target:
            session_store.record_activity(target)
        return get_screen(session=target, lines=lines)
    
    # Start session: "start /path/to/project" OR "start hadley"
    if match := re.match(r"^start\s+(.+)$", text, re.IGNORECASE):
        name_or_path = match.group(1).strip()
        resolved_path = resolve_path(name_or_path)
        result = start_session(resolved_path)
        
        # If successful, record metadata and set as active
        if result.startswith("🚀"):
            import os
            session_name = f"{SESSION_PREFIX}{os.path.basename(resolved_path)}"
            session_store.set_session_meta(
                session_name,
                started_at=datetime.now().isoformat(),
                project_path=resolved_path,
                friendly_name=name_or_path if name_or_path != resolved_path else None
            )
            session_store.set_active_session(session_name)
            session_store.record_activity(session_name)
        
        return result
    
    # Stop session: "stop claude-hadley" or "stop hadley"
    if match := re.match(r"^stop\s+(.+)$", lower):
        session_name = match.group(1).strip()
        if not session_name.startswith(SESSION_PREFIX):
            session_name = f"{SESSION_PREFIX}{session_name}"
        
        result = stop_session(session_name)
        
        # If successful, clear stored data
        if result.startswith("🛑"):
            session_store.clear_session(session_name)
        
        return result
    
    # === Quick actions ===
    
    # Approve permission
    if lower in ["y", "yes", "approve", "ok", "allow"]:
        target = _get_target_session()
        if target:
            session_store.record_activity(target)
        return approve(session=target)
    
    # Deny permission
    if lower in ["n", "no", "deny", "reject", "block"]:
        target = _get_target_session()
        if target:
            session_store.record_activity(target)
        return deny(session=target)
    
    # Escape/cancel
    if lower in ["esc", "escape", "cancel"]:
        target = _get_target_session()
        if target:
            session_store.record_activity(target)
        return escape(session=target)
    
    # === Slash commands / skills passthrough ===
    
    if text.startswith("/"):
        target = _get_target_session()
        if target:
            session_store.record_activity(target)
        return send_prompt(text, session=target)
    
    if match := re.match(r"^skill\s+(.+)$", lower):
        skill_name = match.group(1).strip()
        target = _get_target_session()
        if target:
            session_store.record_activity(target)
        return send_prompt(f"/{skill_name}", session=target)
    
    # === Default: forward as prompt ===
    
    target = _get_target_session()
    if target:
        session_store.record_activity(target)
    return send_prompt(text, session=target)


def on_bot_startup():
    """
    Call this when the Discord bot starts.
    Cleans up stale session data and logs active sessions.
    """
    sessions = get_sessions()
    session_store.clear_stale_sessions(sessions)
    
    active = _get_active_session()
    if active:
        return f"♻️ Restored active session: **[{short_name(active)}]**"
    elif sessions:
        return f"🔍 Found {len(sessions)} session(s): {', '.join(short_name(s) for s in sessions)}"
    else:
        return None  # No message needed
```

---

### `__init__.py` (updated)

```python
from .router import handle_message, on_bot_startup
from .config import CHANNEL_ID

__all__ = ["handle_message", "on_bot_startup", "CHANNEL_ID"]
```

---

## Bot Integration

Update `bot.py` to call startup hook:

```python
from domains.claude_code import handle_message as handle_claude_code, on_bot_startup as claude_code_startup, CHANNEL_ID as CLAUDE_CODE_CHANNEL

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    
    # Claude Code domain startup
    startup_msg = claude_code_startup()
    if startup_msg:
        channel = bot.get_channel(CLAUDE_CODE_CHANNEL)
        if channel:
            await channel.send(startup_msg)
    
    # ... rest of on_ready
```

---

## Command Reference

### New commands (Pre-B)

| Command | Action |
|---------|--------|
| `projects` | List registered project shortcuts |
| `addproj <n> <path>` | Register a project shortcut |
| `rmproj <n>` | Remove a project shortcut |
| `status` | All sessions with last activity times |
| `states` | All sessions with detected state |
| `start hadley` | Start session using project shortcut |

### Updated commands

| Command | Change |
|---------|--------|
| `use {session}` | Now persists across bot restarts |
| `start {path}` | Now accepts project shortcuts |
| `stop {session}` | Now clears stored session data |

### Unchanged commands

All Pre-A commands work exactly as before.

---

## Data Files

`data/claude_sessions.json` (auto-created, gitignore it):

```json
{
  "active_session": "claude-hadley-bricks",
  "last_activity": {
    "claude-hadley-bricks": "2026-01-30T14:23:45.123456",
    "claude-familyfuel": "2026-01-30T09:15:00.000000"
  },
  "session_meta": {
    "claude-hadley-bricks": {
      "started_at": "2026-01-30T08:00:00.000000",
      "project_path": "/mnt/c/Users/Chris/Projects/hadley-bricks",
      "friendly_name": "hadley",
      "last_state": "idle",
      "last_state_check": "2026-01-30T14:24:00.000000"
    }
  }
}
```

`data/projects.json` (auto-created, gitignore it):

```json
{
  "hadley": "/mnt/c/Users/Chris/Projects/hadley-bricks",
  "family": "/mnt/c/Users/Chris/Projects/familyfuel"
}
```

---

## Example Flow

```
[Bot restarts after crash]

Bot: ♻️ Restored active session: **[hadley-bricks]**

Chris: status
Bot:   **Session status:**
       • `hadley-bricks` (2h ago) ← **active**
       • `familyfuel` (5h ago)

Chris: projects
Bot:   **Registered projects:**
       • `hadley` → `/mnt/c/Users/Chris/Projects/hadley-bricks`
       • `family` → `/mnt/c/Users/Chris/Projects/familyfuel`

Chris: start family
Bot:   ⚠️ Session `claude-familyfuel` already exists

Chris: use family
Bot:   🎯 Now targeting **[familyfuel]**

Chris: check the meal plan schema
Bot:   📤 **[familyfuel]** Sent

[Later, bot restarts again]

Bot: ♻️ Restored active session: **[familyfuel]**
```

---

## Testing Checklist

- [ ] `projects` lists registered shortcuts
- [ ] `start hadley` resolves path and creates session
- [ ] `use hadley` persists after bot restart
- [ ] `status` shows all sessions with timestamps
- [ ] `stop hadley` clears stored data
- [ ] Bot startup restores active session
- [ ] Bot startup cleans up stale sessions (sessions that no longer exist)
- [ ] Activity timestamps update on each interaction

---

## Session State Detection

Automatically detect whether Claude Code is working or waiting for input by parsing tmux output. Polls every 60 seconds for long-running processes.

### State Definitions

| State | Detection | Meaning |
|-------|-----------|---------|
| `idle` | Prompt visible: `>` or `❯` at end | Waiting for user input |
| `working` | No prompt, output changing | Claude is processing |
| `permission` | Contains "Allow" / "Deny" / "(y/n)" | Waiting for approval |
| `error` | Contains error patterns | Something went wrong |
| `unknown` | Can't determine | Fallback state |

### File Structure Update

```
domains/
└── claude_code/
    ├── __init__.py
    ├── config.py
    ├── router.py
    ├── tools.py
    ├── session_store.py
    ├── projects.py
    └── state_monitor.py   # NEW
```

### `state_monitor.py` (new file)

```python
"""
Session state detection - polls tmux output to detect Claude Code state.
Runs every 60 seconds for active sessions.
"""

import re
import asyncio
from datetime import datetime
from typing import Optional
from enum import Enum

from .tools import get_sessions, short_name
from . import session_store


class SessionState(Enum):
    IDLE = "idle"
    WORKING = "working"
    PERMISSION = "permission"
    ERROR = "error"
    UNKNOWN = "unknown"


# Patterns to detect state
IDLE_PATTERNS = [
    r'>\s*$',           # Standard prompt
    r'❯\s*$',           # Alternative prompt
    r'\$\s*$',          # Bash prompt (if claude exited)
]

PERMISSION_PATTERNS = [
    r'\(y/n\)',
    r'\[y/N\]',
    r'\[Y/n\]',
    r'Allow\s+Deny',
    r'approve.*deny',
    r'permission.*request',
]

ERROR_PATTERNS = [
    r'Error:',
    r'ERROR',
    r'failed',
    r'Exception',
    r'Traceback',
]


def detect_state(output: str) -> SessionState:
    """Analyze tmux output to determine session state."""
    if not output or not output.strip():
        return SessionState.UNKNOWN
    
    lines = output.strip().split('\n')
    recent = '\n'.join(lines[-10:])
    last_line = lines[-1] if lines else ""
    
    # Check for permission request first (highest priority)
    for pattern in PERMISSION_PATTERNS:
        if re.search(pattern, recent, re.IGNORECASE):
            return SessionState.PERMISSION
    
    # Check for errors
    for pattern in ERROR_PATTERNS:
        if re.search(pattern, recent, re.IGNORECASE):
            return SessionState.ERROR
    
    # Check for idle prompt
    for pattern in IDLE_PATTERNS:
        if re.search(pattern, last_line):
            return SessionState.IDLE
    
    return SessionState.WORKING


def get_state_emoji(state: SessionState) -> str:
    return {
        SessionState.IDLE: "💤",
        SessionState.WORKING: "⚙️",
        SessionState.PERMISSION: "🔐",
        SessionState.ERROR: "❌",
        SessionState.UNKNOWN: "❓",
    }.get(state, "❓")


def get_screen_raw(session: str, lines: int = 20) -> str:
    """Get raw tmux output without formatting."""
    import subprocess
    import os
    
    IS_WINDOWS = os.name == 'nt'
    TMUX_PREFIX = ["wsl"] if IS_WINDOWS else []
    
    result = subprocess.run(
        [*TMUX_PREFIX, "tmux", "capture-pane", "-t", session, "-p", "-S", f"-{lines}"],
        capture_output=True,
        text=True
    )
    return result.stdout


async def check_session_state(session: str) -> tuple[SessionState, str]:
    """Check state of a single session."""
    output = get_screen_raw(session, lines=20)
    state = detect_state(output)
    return state, output


async def poll_all_sessions() -> dict[str, SessionState]:
    """Check state of all active sessions."""
    sessions = get_sessions()
    states = {}
    
    for session in sessions:
        state, _ = await check_session_state(session)
        states[session] = state
        
        session_store.set_session_meta(
            session,
            last_state=state.value,
            last_state_check=datetime.now().isoformat()
        )
    
    return states


def get_stored_state(session: str) -> Optional[SessionState]:
    """Get last known state from store."""
    meta = session_store.get_session_meta(session)
    state_str = meta.get("last_state")
    if state_str:
        try:
            return SessionState(state_str)
        except ValueError:
            return None
    return None


# --- State change notifications ---

_previous_states: dict[str, SessionState] = {}


async def check_and_notify(notify_callback) -> list[str]:
    """
    Poll sessions and notify on important state changes.
    notify_callback: async function(message: str)
    """
    global _previous_states
    
    sessions = get_sessions()
    notifications = []
    
    for session in sessions:
        state, output = await check_session_state(session)
        prev_state = _previous_states.get(session)
        
        if prev_state != state:
            name = short_name(session)
            
            if state == SessionState.PERMISSION:
                msg = f"🔐 **[{name}]** needs permission"
                notifications.append(msg)
                if notify_callback:
                    await notify_callback(msg)
            
            elif prev_state == SessionState.WORKING and state == SessionState.IDLE:
                msg = f"✅ **[{name}]** finished, waiting for input"
                notifications.append(msg)
                if notify_callback:
                    await notify_callback(msg)
            
            elif state == SessionState.ERROR:
                msg = f"❌ **[{name}]** encountered an error"
                notifications.append(msg)
                if notify_callback:
                    await notify_callback(msg)
        
        _previous_states[session] = state
    
    # Clean up gone sessions
    for session in list(_previous_states.keys()):
        if session not in sessions:
            del _previous_states[session]
    
    return notifications
```

### `router.py` addition

Add to `handle_message`:

```python
    # Session state
    if lower in ["state", "states"]:
        sessions = get_sessions()
        if not sessions:
            return "No active Claude Code sessions"
        
        from .state_monitor import get_stored_state, get_state_emoji, SessionState
        
        lines = []
        for s in sessions:
            state = get_stored_state(s) or SessionState.UNKNOWN
            emoji = get_state_emoji(state)
            active_marker = " ← active" if s == _get_active_session() else ""
            lines.append(f"• {emoji} `{short_name(s)}` - {state.value}{active_marker}")
        
        return "**Session states:**\n" + "\n".join(lines)
```

### Bot Integration - Polling Loop

Add to `bot.py`:

```python
from domains.claude_code.state_monitor import check_and_notify

async def start_state_monitor():
    """Poll session states every 60 seconds."""
    channel = bot.get_channel(CLAUDE_CODE_CHANNEL)
    
    async def notify(msg: str):
        if channel:
            await channel.send(msg)
    
    while True:
        try:
            await check_and_notify(notify)
        except Exception as e:
            print(f"State monitor error: {e}")
        
        await asyncio.sleep(60)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    
    # Start state monitoring loop
    bot.loop.create_task(start_state_monitor())
    
    # ... rest of on_ready
```

### Updated Command Reference

| Command | Action |
|---------|--------|
| `state` / `states` | Show all sessions with detected state |
| `addproj <name> <path>` | Register a project shortcut |
| `rmproj <name>` | Remove a project shortcut |

### Automatic Notifications

Posts to `#claude-code` when:

| Transition | Message |
|------------|---------|
| Any → Permission | 🔐 **[hadley]** needs permission |
| Working → Idle | ✅ **[hadley]** finished, waiting for input |
| Any → Error | ❌ **[hadley]** encountered an error |

### Example Output

```
Chris: states
Bot:   **Session states:**
       • ⚙️ `hadley-bricks` - working ← active
       • 💤 `familyfuel` - idle

[60 seconds later, automatically]
Bot:   ✅ **[hadley-bricks]** finished, waiting for input

Chris: states
Bot:   **Session states:**
       • 💤 `hadley-bricks` - idle ← active
       • 💤 `familyfuel` - idle
```

---

## Future Considerations (not in this spec)

- **Configurable poll interval** - Faster polling when session is working
- **Output diff detection** - Compare outputs between polls to confirm "working" state
