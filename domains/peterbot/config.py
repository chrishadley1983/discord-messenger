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

# Memory integration (Second Brain)
# peterbot-mem has been replaced by Second Brain (Supabase + pgvector)

# Circuit breaker (protects against Supabase outages)
CIRCUIT_FAILURE_THRESHOLD = 5      # Consecutive failures before opening circuit
CIRCUIT_RECOVERY_TIMEOUT = 60      # Seconds before testing recovery

# Buffer settings
RECENT_BUFFER_SIZE = 20

# Capture store (local SQLite queue for reliability)
CAPTURE_STORE_DB = os.path.expanduser("~/.peterbot/capture_store.db")
CAPTURE_MAX_RETRIES = 5
CAPTURE_SENT_RETENTION_DAYS = 7
CAPTURE_FAILED_RETENTION_DAYS = 30

# Context cache
CONTEXT_CACHE_TTL_SECONDS = 300  # 5 minutes
CONTEXT_CACHE_MAX_ENTRIES = 200

# Response capture
RESPONSE_TIMEOUT = 600
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

# CLI execution settings
CLI_TOTAL_TIMEOUT = 1200      # Max seconds for conversation CLI execution (20 min)
CLI_MAX_TURNS = 50            # Max agentic turns for conversations (quality over speed)
CLI_SCHEDULED_MAX_TURNS = 50  # Max agentic turns for scheduled jobs (same as conversations)
# No --max-budget-usd flag needed: CLI runs on subscription, not API billing.
# The subscription's own rate limits are the safety net.
CLI_MODEL = "opus"                # Opus for conversations (better at autonomous multi-step tasks)
CLI_SCHEDULED_MODEL = "opus"  # Opus for scheduled jobs (4.6 hangs on open-ended skills like self-reflect)
CLI_COMMAND = os.environ.get("PETERBOT_CLI_COMMAND", "claude")  # CLI binary
CLI_WORKING_DIR = PETERBOT_SESSION_PATH  # ~/peterbot (where CLAUDE.md lives)

# --- Provider Priority (3-tier cascade) ---
# cc (primary account) → cc2 (secondary account) → Kimi (API fallback)
# Each Claude account uses a different CLAUDE_CONFIG_DIR.
# cc uses the default (~/.claude), cc2 uses a secondary config dir.
CLI_CC_CONFIG_DIR = os.environ.get("PETERBOT_CC_CONFIG_DIR", "")  # Empty = default ~/.claude
CLI_CC2_CONFIG_DIR = os.environ.get("PETERBOT_CC2_CONFIG_DIR", "/mnt/c/Users/Chris Hadley/.claude-secondary")

# Provider priority order — tried left to right on credit exhaustion
PROVIDER_PRIORITY = ["claude_cc", "claude_cc2", "kimi"]

# --- Kimi Fallback ---
# Kimi 2.5 (Moonshot AI) as degraded-mode fallback when Anthropic credits are exhausted.
# OpenAI-compatible API. No MCP tools, no CLAUDE.md auto-load, but pre-fetched data still injected.
KIMI_API_BASE = "https://api.moonshot.ai/v1"
KIMI_MODEL = "kimi-k2.5"
KIMI_MAX_TOKENS = 4096
KIMI_TIMEOUT = 120

# --- Second Brain Auto-Save ---
# Skills whose output is auto-saved to Second Brain after execution.
# High-value, searchable content that builds a useful knowledge archive.
SECOND_BRAIN_SAVE_SKILLS: set[str] = {
    "daily-recipes",
    "health-digest",
    "nutrition-summary",
    "weekly-health",
    "morning-briefing",
    "news",
    "youtube-digest",
    "knowledge-digest",
}

# --- Document Detection (ad-hoc auto-save) ---
# Heuristics for detecting generated documents in conversation responses.
DOCUMENT_MIN_LENGTH = 800      # Minimum characters to consider as document
DOCUMENT_MIN_HEADERS = 2       # Minimum markdown headers (# or ##) required
