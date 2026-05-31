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

# DOM-read interval — pure JS evaluation on a persistent open page, no HTTP
# to Prolific between reads. Cheap enough that 5s is comfortable. Jitter just
# avoids perfectly periodic reads.
POLL_INTERVAL_SECONDS = 5
POLL_JITTER_SECONDS = 2

# Defence-in-depth — force a full page reload occasionally so we refresh
# cookies / reset Prolific's SPA state / detect a silently-broken session.
PAGE_RELOAD_INTERVAL_SECONDS = 15 * 60  # 15 minutes

ACTIVE_START_HOUR = 6
ACTIVE_START_MINUTE = 30
ACTIVE_END_HOUR = 23
ACTIVE_END_MINUTE = 30
ACTIVE_TIMEZONE = "Europe/London"

DISCORD_WEBHOOK = (
    os.environ.get("DISCORD_WEBHOOK_PROLIFIC")
    or os.environ.get("DISCORD_WEBHOOK_ALERTS")
)

SEEN_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "prolific_seen.db"

NAV_TIMEOUT_MS = 20_000
RENDER_WAIT_MS = 3_500

# How often to re-alert Discord while the session is still expired.
# Local log warnings happen every reload (15 min) — Discord pings are noisier
# so throttle them.
SESSION_EXPIRED_ALERT_INTERVAL_S = 3 * 60 * 60  # 3 hours

# Hard timeouts so a dead CDP socket or hung Chrome can't freeze the scheduler
# forever. Playwright's own evaluate/connect have no implicit deadline; without
# these, max_instances=1 silently drops every subsequent tick.
CDP_CONNECT_TIMEOUT_S = 10.0
EVALUATE_TIMEOUT_S = 15.0
