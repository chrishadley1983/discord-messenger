"""Pending actions — JSON-backed confirmation state for WhatsApp flows.

Stores proposed schedule changes (and other actions) that need user confirmation
before execution. Actions expire after 5 minutes.
"""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"
PENDING_FILE = DATA_DIR / "pending_actions.json"
EXPIRY_MINUTES = 5


def _load() -> dict:
    """Load pending actions from JSON file."""
    if not PENDING_FILE.exists():
        return {"actions": []}
    try:
        return json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"actions": []}


def _save(data: dict):
    """Save pending actions to JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def cleanup_expired():
    """Remove actions older than EXPIRY_MINUTES."""
    data = _load()
    now = datetime.utcnow()
    data["actions"] = [
        a for a in data["actions"]
        if datetime.fromisoformat(a["expires_at"]) > now
    ]
    _save(data)


def create_pending_action(
    action_type: str,
    sender_number: str,
    sender_name: str,
    description: str,
    api_call: dict,
) -> str:
    """Create a new pending action and return its ID.

    Args:
        action_type: e.g. "schedule_change", "pause"
        sender_number: WhatsApp number of the sender
        sender_name: Human name (chris, abby)
        description: Human-readable description of what will happen
        api_call: Dict with method, url, body keys for the action to execute on confirm

    Returns:
        The action ID (pa_xxxx format)
    """
    cleanup_expired()
    data = _load()

    now = datetime.utcnow()
    action_id = f"pa_{uuid.uuid4().hex[:8]}"

    action = {
        "id": action_id,
        "type": action_type,
        "sender_number": sender_number,
        "sender_name": sender_name,
        "description": description,
        "api_call": api_call,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=EXPIRY_MINUTES)).isoformat(),
    }

    data["actions"].append(action)
    _save(data)
    return action_id


def get_pending_for_sender(sender_number: str) -> list:
    """Get all non-expired pending actions for a sender number."""
    cleanup_expired()
    data = _load()
    now = datetime.utcnow()
    return [
        a for a in data["actions"]
        if a["sender_number"] == sender_number
        and datetime.fromisoformat(a["expires_at"]) > now
    ]


def get_pending_by_id(action_id: str) -> dict | None:
    """Get a single pending action by ID, or None if not found/expired."""
    cleanup_expired()
    data = _load()
    for a in data["actions"]:
        if a["id"] == action_id:
            return a
    return None


def resolve_action(action_id: str, approved: bool) -> dict | None:
    """Remove and return a pending action.

    Args:
        action_id: The action to resolve
        approved: True if confirmed, False if cancelled (for logging only)

    Returns:
        The resolved action dict, or None if not found
    """
    data = _load()
    for i, a in enumerate(data["actions"]):
        if a["id"] == action_id:
            action = data["actions"].pop(i)
            _save(data)
            return action
    return None
