"""Peterbot domain — Personal assistant via Claude Code channels (primary) or CLI (fallback).

Primary path: Persistent Claude Code sessions via Anthropic channels architecture.
Fallback path: Stateless `claude -p` via router_v2 when channel sessions are down.
"""

from .router_v2 import handle_message, on_startup
from .config import CHANNEL_ID

__all__ = [
    "handle_message",
    "on_startup",
    "CHANNEL_ID",
]
