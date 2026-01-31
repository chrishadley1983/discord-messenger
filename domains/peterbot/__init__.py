"""Peterbot domain - Personal assistant with memory integration via Claude Code.

This domain routes messages through a dedicated Claude Code tmux session
with memory context injection from peterbot-mem.
"""

from .router import handle_message, on_startup
from .config import CHANNEL_ID, PETERBOT_SESSION

# Keep PeterbotDomain for reference/fallback, but not used in normal routing
from .domain import PeterbotDomain

__all__ = [
    "handle_message",
    "on_startup",
    "CHANNEL_ID",
    "PETERBOT_SESSION",
    "PeterbotDomain",  # Legacy - kept for reference
]
