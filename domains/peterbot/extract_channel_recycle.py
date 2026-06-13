"""Extract-channel session recycler.

The extract-channel is a PERSISTENT Claude Code session (Haiku) that backs
/claude/extract. Each extraction adds a user+assistant turn to its context;
there is no per-request /clear in the MCP-notification channel architecture,
so after enough extractions the session hits 100% context and wedges —
inject->reply stops returning, every call times out empty, and (before the
circuit breaker) everything that extracts slowed ~20x (school sync 17 min,
Second Brain seeding crawled). Observed 13 Jun 2026.

This recycler keeps the FAST path healthy: it restarts the stateless
session before context fills (requests_out threshold) or when a canary
extraction proves it's already wedged. The circuit breaker in
hadley_api/claude_routes.py covers the brief restart window (callers fall
to the CLI, ~5s). Restarting loses nothing — extractions are independent
one-shots.
"""

from __future__ import annotations

import asyncio
import subprocess
import time

import httpx

from logger import logger

EXTRACT_HEALTH = "http://localhost:8106/health"
# Recycle well below the observed ~50-request wedge point so context never
# fills. Count-based (not canary-based) — a canary would itself inflate the
# request count it's trying to monitor. The circuit breaker is the safety
# net for any wedge that beats this threshold.
RECYCLE_EVERY = 25          # restart after this many requests, when idle
FORCE_RECYCLE_AT = 45       # restart even mid-batch past this (near wedge)
WSL_BASE = "/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger"

_last_session_start: str | None = None


def _restart_session() -> None:
    subprocess.run(
        ["wsl", "bash", "-lc", "tmux kill-session -t extract-channel 2>/dev/null; true"],
        capture_output=True, timeout=20,
    )
    subprocess.Popen(
        ["wsl", "bash", "-lc",
         f'tmux new-session -d -s extract-channel -c $HOME/peterbot '
         f'"bash \\"{WSL_BASE}/extract-channel/launch.sh\\""'],
    )
    logger.warning("extract-channel recycled (session restarted to clear context)")


def _health() -> dict | None:
    try:
        return httpx.get(EXTRACT_HEALTH, timeout=5).json()
    except Exception as e:
        # distinguish a mid-restart bounce from a genuinely dead session
        logger.debug(f"extract-channel /health unreachable: {e}")
        return None


def check_and_recycle() -> dict:
    """One recycle-decision pass (sync; wrap in to_thread)."""
    h = _health()
    if h is None:
        # server not answering — the channel watchdog relaunches dead
        # sessions; don't double-act here
        return {"action": "skip", "reason": "no health"}

    reqs = int(h.get("requests_out", 0))
    pending = int(h.get("pending", 0))

    if reqs >= FORCE_RECYCLE_AT:
        _restart_session()
        return {"action": "force_recycle", "requests": reqs}

    if reqs >= RECYCLE_EVERY and pending == 0:
        _restart_session()
        return {"action": "recycle", "requests": reqs}

    return {"action": "ok", "requests": reqs, "pending": pending}


def register(scheduler, minutes: int = 4) -> None:
    async def _job():
        try:
            await asyncio.to_thread(check_and_recycle)
        except Exception as e:
            logger.debug(f"extract-channel recycle check failed: {e}")

    scheduler.add_job(
        _job, "interval", minutes=minutes,
        id="extract_channel_recycle", max_instances=1,
        coalesce=True, replace_existing=True,
    )
    logger.info(f"Extract-channel recycler registered (every {minutes} min)")
