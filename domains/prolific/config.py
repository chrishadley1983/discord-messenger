"""Configuration for the Prolific studies monitor."""

from __future__ import annotations

import os
from pathlib import Path

CDP_PORT = int(os.environ.get("PROLIFIC_CDP_PORT", "9224"))

PROFILE_DIR = Path(
    os.environ.get(
        "PROLIFIC_PROFILE_DIR",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome-Prolific"),
    )
)

CHROME_EXE = Path(
    os.environ.get(
        "PROLIFIC_CHROME_EXE",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    )
)

STUDIES_URL = "https://app.prolific.com/studies"
LOGIN_URL = "https://app.prolific.com/login"

POLL_INTERVAL_SECONDS = 75
POLL_JITTER_SECONDS = 15

ACTIVE_START_HOUR = 8
ACTIVE_END_HOUR = 23
ACTIVE_TIMEZONE = "Europe/London"

DISCORD_WEBHOOK = (
    os.environ.get("DISCORD_WEBHOOK_PROLIFIC")
    or os.environ.get("DISCORD_WEBHOOK_ALERTS")
)

SEEN_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "prolific_seen.db"

NAV_TIMEOUT_MS = 20_000
RENDER_WAIT_MS = 3_500
