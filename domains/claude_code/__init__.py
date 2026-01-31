"""Claude Code Remote domain - control Claude Code sessions via Discord."""

from .router import handle_message, on_bot_startup
from .config import CHANNEL_ID

__all__ = ["handle_message", "on_bot_startup", "CHANNEL_ID"]
