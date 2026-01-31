"""Claude Code Remote domain configuration."""

import os
from pathlib import Path

CHANNEL_ID = int(os.environ.get("CLAUDE_CODE_CHANNEL_ID", 0))
SESSION_PREFIX = "claude-"
DEFAULT_SCREEN_LINES = 40

# Pre-B: Data persistence paths
DATA_DIR = Path(__file__).parent.parent.parent / "data"
SESSION_STORE_PATH = DATA_DIR / "claude_sessions.json"
PROJECTS_PATH = DATA_DIR / "projects.json"
