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
