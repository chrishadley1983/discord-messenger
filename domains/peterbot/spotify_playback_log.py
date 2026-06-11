"""Spotify playback poller — captures what recently-played can't see.

Spotify's recently-played API only returns music tracks; podcast episodes
and audiobook chapters never appear in it, so they were invisible to the
Second Brain listening history. This poller snapshots the live player state
every few minutes and appends active playback to
``data/spotify_playback_log.jsonl``. The nightly seed adapter
(second_brain/seed/adapters/spotify_playback.py) aggregates the log into
daily listening summaries, reclassifying audiobooks via the saved-audiobook
library (they surface as shows/episodes in the player API).

No Discord output and failures are quiet — a Spotify hiccup every few polls
is normal (token refresh, no active device) and must not alert.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from logger import logger

LOG_PATH = Path(__file__).resolve().parents[2] / "data" / "spotify_playback_log.jsonl"


def capture_snapshot() -> dict:
    """Poll current playback once; append to the log if something is playing."""
    from domains.peterbot import spotify_service

    snapshot = spotify_service.playback_snapshot()
    if not snapshot.get("playing"):
        return {"logged": False}

    entry = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"), **snapshot}
    entry.pop("playing", None)

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"logged": True, "kind": entry.get("kind"), "name": entry.get("name")}


def register(scheduler, minutes: int = 5) -> None:
    """Register the poller as a quiet infrastructure job."""

    async def _poll_job():
        try:
            await asyncio.to_thread(capture_snapshot)
        except Exception as e:
            logger.debug(f"Spotify playback poll failed: {e}")

    scheduler.add_job(
        _poll_job,
        "interval",
        minutes=minutes,
        id="spotify_playback_poll",
        max_instances=1,
        replace_existing=True,
    )
    logger.info(f"Spotify playback poller registered (every {minutes} min)")
