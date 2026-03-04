"""Peterbot domain - Personal assistant with memory integration via Claude Code.

This domain routes messages through Claude CLI (--print mode)
with memory context injection from Second Brain (Supabase + pgvector).
"""

from .router_v2 import handle_message, on_startup
from .config import CHANNEL_ID, PETERBOT_SESSION

__all__ = [
    "handle_message",
    "on_startup",
    "CHANNEL_ID",
    "PETERBOT_SESSION",
]
