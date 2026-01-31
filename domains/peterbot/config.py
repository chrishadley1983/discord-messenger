"""Peterbot domain configuration - memory-enabled Claude Code routing."""

import os

# Channel ID from environment
CHANNEL_ID = int(os.environ.get("PETERBOT_CHANNEL_ID", 0))

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

# Context file for large prompts (avoids tmux paste issues)
CONTEXT_FILE = f"{PETERBOT_SESSION_PATH}/context.md"
