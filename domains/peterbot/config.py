"""Peterbot domain configuration - memory-enabled Claude Code routing."""

import os

# Channel ID from environment
CHANNEL_ID = int(os.environ.get("PETERBOT_CHANNEL_ID", 0))

# Additional channel IDs that Peterbot responds to (can be set via env or here)
# This is a set of channel IDs where Peterbot will process messages
_extra_channels = os.environ.get("PETERBOT_EXTRA_CHANNEL_IDS", "")
PETERBOT_CHANNEL_IDS = {CHANNEL_ID} if CHANNEL_ID else set()
if _extra_channels:
    PETERBOT_CHANNEL_IDS.update(int(cid.strip()) for cid in _extra_channels.split(",") if cid.strip())

# Dedicated tmux session for peterbot
# Session name derived from path basename: peterbot -> claude-peterbot
PETERBOT_SESSION = "claude-peterbot"
PETERBOT_SESSION_PATH = os.environ.get(
    "PETERBOT_SESSION_PATH",
    "/home/chris_hadley/peterbot"  # Creates ~/peterbot if needed
)

# Memory integration
WORKER_URL = os.environ.get("PETERBOT_MEM_URL", "http://localhost:37777")
MESSAGES_ENDPOINT = f"{WORKER_URL}/api/sessions/messages"
CONTEXT_ENDPOINT = f"{WORKER_URL}/api/context/inject"
PROJECT_ID = "peterbot"

# Buffer settings
RECENT_BUFFER_SIZE = 20

# Retry settings
FAILURE_QUEUE_MAX = 100
RETRY_INTERVAL_SECONDS = 60
MAX_RETRIES = 3

# Response capture
RESPONSE_TIMEOUT = 60
POLL_INTERVAL = 0.5
STABLE_COUNT_THRESHOLD = 3

# Interim updates (show progress while waiting for response)
INTERIM_UPDATE_DELAY = 5.0  # Seconds before first interim update
INTERIM_UPDATE_INTERVAL = 10.0  # Seconds between interim updates

# Context file for large prompts (avoids tmux paste issues)
CONTEXT_FILE = f"{PETERBOT_SESSION_PATH}/context.md"

# Raw log path for debugging
RAW_LOG_PATH = f"{PETERBOT_SESSION_PATH}/raw_output.log"

# Channel ID to name mapping (populated at runtime or configured here)
CHANNEL_ID_TO_NAME = {
    # Add channel mappings as needed, e.g.:
    # 123456789: "#general",
}

# --- Router V2 (Claude CLI --print mode) ---
# V2 is the DEFAULT since Feb 2026. Uses `claude -p --output-format stream-json`
# instead of tmux screen-scraping. Each call is an independent process (no session lock).
#
# To REVERT to tmux (v1): set PETERBOT_ROUTER_V2=0
# Old router.py, parser.py, sanitiser.py are kept in-tree as fallback.
USE_ROUTER_V2 = os.environ.get("PETERBOT_ROUTER_V2", "1").lower() not in ("0", "false", "no")

# CLI execution settings
CLI_TOTAL_TIMEOUT = 300       # Max seconds for full CLI execution (tool chains, research)
# No --max-budget-usd flag needed: CLI runs on subscription, not API billing.
# The subscription's own rate limits are the safety net.
CLI_MODEL = "opus"            # Model flag for claude CLI
CLI_WORKING_DIR = PETERBOT_SESSION_PATH  # ~/peterbot (where CLAUDE.md lives)
