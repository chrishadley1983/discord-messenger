"""Pattern matching router for Claude Code commands.

No LLM required - direct pattern matching routes commands to tmux.
Pre-B: Added persistent session store, project registry, activity tracking.
"""

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
    interrupt,
    scroll_up,
    get_status,
    attach_session,
    short_name,
)
from .config import DEFAULT_SCREEN_LINES, SESSION_PREFIX
from .projects import resolve_path, list_projects, add_project, remove_project
from . import session_store


HELP_TEXT = """**Claude Code Remote Commands**

**Session Targeting:**
- `@prefix: prompt` - Send to specific session (e.g. `@hadley: check the API`)
- `@prefix:` - Show screen for that session
- `use <name>` - Set default session
- `sessions` / `ls` - List sessions
- `which` - Show current target

**View Output:**
- `screen` / `s` - Show last 40 lines
- `screen 100` - Show last 100 lines
- `up` / `scroll` - Show earlier history
- `status` - All sessions with last activity times

**Quick Actions:**
- `y` / `n` - Approve/deny permission
- `esc` - Send Escape key
- `ctrl-c` / `interrupt` - Send Ctrl+C

**Session Management:**
- `start <name>` - Start new session (project name or path)
- `stop <name>` - Stop session
- `attach` / `reconnect` - Open terminal window for active session
- `/command` - Forward slash command

**Projects:**
- `projects` / `proj` - List registered projects
- `addproj <name> <path>` - Register project shortcut
- `rmproj <name>` - Remove project shortcut

**Any other text** -> Sent as prompt"""


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
    """Set the active session (with validation and persistence)."""
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
    except Exception:
        return "unknown"


def find_session_by_prefix(prefix: str) -> str | None:
    """Find a session matching the given prefix (fuzzy match).

    Examples:
        'hadley' matches 'claude-hadley-bricks'
        'discord' matches 'claude-discord-messenger'
        'hadley-bricks' matches 'claude-hadley-bricks' exactly
    """
    prefix = prefix.lower()
    sessions = get_sessions()

    # Try exact match first (claude-{prefix})
    exact = f"{SESSION_PREFIX}{prefix}"
    if exact in sessions:
        return exact

    # Try prefix match (claude-{prefix}*)
    for session in sessions:
        session_name = short_name(session).lower()
        if session_name.startswith(prefix):
            return session

    # Try contains match (claude-*{prefix}*)
    for session in sessions:
        session_name = short_name(session).lower()
        if prefix in session_name:
            return session

    return None


def handle_message(msg: str) -> str:
    """
    Route Discord message to appropriate action.
    No LLM - pattern matching only.

    Supports @prefix: syntax to target specific sessions:
        @hadley: check the API  ->  sends to claude-hadley-bricks
        @discord: how does this work  ->  sends to claude-discord-messenger
    """
    text = msg.strip()
    lower = text.lower()

    # === @prefix: targeting ===
    # Match @name: at start of message to target a specific session
    if match := re.match(r"^@(\S+):\s*(.*)$", text, re.DOTALL):
        prefix = match.group(1)
        prompt = match.group(2).strip()

        session = find_session_by_prefix(prefix)
        if not session:
            sessions = get_sessions()
            available = ", ".join(short_name(s) for s in sessions) if sessions else "none"
            return f"No session matching `{prefix}`. Available: {available}"

        session_store.record_activity(session)

        if not prompt:
            # Just @prefix: with no prompt - show the screen
            return get_screen(session=session, lines=DEFAULT_SCREEN_LINES)

        return send_prompt(prompt, session=session)

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
        return add_project(name, path)

    # Remove project: "rmproj hadley"
    if match := re.match(r"^rmproj\s+(\S+)$", lower):
        name = match.group(1).strip()
        return remove_project(name)

    # === Session status with activity times (Pre-B) ===

    if lower in ["status", "stat"]:
        sessions = get_sessions()
        if not sessions:
            return "❌ No active Claude Code sessions"

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
            return "❌ No active Claude Code sessions"
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

    # Start session: "start /path/to/project" OR "start hadley" (project name)
    if match := re.match(r"^start\s+(.+)$", text, re.IGNORECASE):
        name_or_path = match.group(1).strip()
        resolved_path = resolve_path(name_or_path)
        result = start_session(resolved_path)

        # If successful, record metadata and set as active
        if "Started" in result or "🚀" in result:
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
        if "Stopped" in result or "🛑" in result:
            session_store.clear_session(session_name)

        return result

    # Attach to existing session (open terminal window)
    if lower in ["attach", "reconnect", "terminal", "open"]:
        target = _get_target_session()
        if not target:
            return "❌ No active Claude Code sessions"
        session_store.record_activity(target)
        return attach_session(session=target)

    # Attach to specific session: "attach hadley"
    if match := re.match(r"^(?:attach|reconnect|terminal|open)\s+(.+)$", lower):
        session_name = match.group(1).strip()
        session = find_session_by_prefix(session_name)
        if not session:
            sessions = get_sessions()
            available = ", ".join(short_name(s) for s in sessions) if sessions else "none"
            return f"❌ No session matching `{session_name}`. Available: {available}"
        session_store.record_activity(session)
        return attach_session(session=session)

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

    # Interrupt (Ctrl+C)
    if lower in ["ctrl-c", "ctrl+c", "interrupt", "kill"]:
        target = _get_target_session()
        if target:
            session_store.record_activity(target)
        return interrupt(session=target)

    # Scroll up / history
    if lower in ["up", "scroll", "history", "earlier"]:
        target = _get_target_session()
        if target:
            session_store.record_activity(target)
        return scroll_up(session=target)

    # Scroll with amount: "up 50" or "scroll 100"
    if match := re.match(r"^(?:up|scroll|history)\s+(\d+)$", lower):
        lines = min(int(match.group(1)), 200)
        target = _get_target_session()
        if target:
            session_store.record_activity(target)
        return scroll_up(session=target, lines=lines)

    # Help
    if lower in ["help", "commands", "?"]:
        return HELP_TEXT

    # === Slash commands / skills passthrough ===

    # Forward slash commands directly: "/compact", "/clear", etc.
    if text.startswith("/"):
        target = _get_target_session()
        if target:
            session_store.record_activity(target)
        return send_prompt(text, session=target)

    # Trigger skill by name: "skill test-plan" -> "/test-plan"
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


def on_bot_startup() -> str | None:
    """
    Call this when the Discord bot starts.
    Cleans up stale session data and returns a status message.
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
