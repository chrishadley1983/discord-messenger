"""Configuration for Peter Voice Desktop Client.

Loads secrets from parent .env, user prefs from local config.json.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Paths
VOICE_DIR = Path(__file__).parent
PROJECT_ROOT = VOICE_DIR.parent
CONFIG_FILE = VOICE_DIR / "config.json"
MODELS_DIR = VOICE_DIR / "models"
LOG_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "peter-voice" / "logs"

# Load parent .env
load_dotenv(PROJECT_ROOT / ".env")

# Discord secrets
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
PETERBOT_CHANNEL_ID = int(os.environ["PETERBOT_CHANNEL_ID"])

# Webhook for sending voice messages as "Chris (Voice)"
WEBHOOK_URL = (
    "https://discordapp.com/api/webhooks/"
    "1469418933152120984/"
    "ELkrUqxnk_WFLUj4TU1NFjn5Mauimmu_HUPDGjN5yeuWcwBvyW40cVBzJdebiskMPBny"
)

# Discord API base
DISCORD_API = "https://discord.com/api/v10"

# Bot user ID — discovered on first run, cached in config.json
_bot_user_id: str | None = None


def _load_config() -> dict:
    """Load config.json, creating defaults if missing."""
    defaults = {
        "voice": "bf_emma",
        "speed": 1.0,
        "mode": "ptt",
        "wake_word": "peter",
        "max_speech_chars": 500,
        "voice_replies_only": True,
        "poll_interval_active": 2.0,
        "poll_interval_idle": 5.0,
        "poll_timeout": 60,
        "bot_user_id": None,
    }
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            saved = json.load(f)
        # Merge defaults for any missing keys
        for k, v in defaults.items():
            saved.setdefault(k, v)
        return saved
    # Create default config
    with open(CONFIG_FILE, "w") as f:
        json.dump(defaults, f, indent=4)
    return defaults


def _save_config(cfg: dict) -> None:
    """Persist config to disk."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)


# Load once at import
_config = _load_config()

# User preferences
VOICE = _config["voice"]
SPEED = _config["speed"]
MODE = _config["mode"]  # "ptt" or "wake"
WAKE_WORD = _config["wake_word"]
MAX_SPEECH_CHARS = _config["max_speech_chars"]
VOICE_REPLIES_ONLY = _config["voice_replies_only"]
POLL_INTERVAL_ACTIVE = _config["poll_interval_active"]
POLL_INTERVAL_IDLE = _config["poll_interval_idle"]
POLL_TIMEOUT = _config["poll_timeout"]


def get_bot_user_id() -> str | None:
    """Return cached bot user ID."""
    return _config.get("bot_user_id")


def set_bot_user_id(user_id: str) -> None:
    """Cache bot user ID to config.json."""
    _config["bot_user_id"] = user_id
    _save_config(_config)


def update_preference(key: str, value) -> None:
    """Update a user preference and persist."""
    _config[key] = value
    _save_config(_config)
    # Update module-level vars
    globals()[key.upper()] = value
