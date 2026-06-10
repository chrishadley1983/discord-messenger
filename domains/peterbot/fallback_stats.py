"""Instrumentation for legacy-fallback activations (router_v2 / claude -p).

The channel sessions are the primary message path since Mar 2026; router_v2
and `claude -p` only fire when a channel is down. Before the legacy path can
be deleted, we need evidence of how often it actually rescues traffic — every
activation is recorded here and surfaced in #alerts (throttled).

Events land in data/fallback_events.jsonl:
    {"ts": "...", "component": "peter-channel", "reason": "health probe failed"}

Query with:  python -c "from domains.peterbot.fallback_stats import summary; print(summary())"
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from logger import logger

EVENTS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "fallback_events.jsonl"
ALERT_THROTTLE_S = 3600

_last_alert: dict[str, float] = {}
_lock = threading.Lock()


def record_fallback(component: str, reason: str) -> None:
    """Record one legacy-fallback activation. Never raises."""
    event = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "component": component,
        "reason": reason[:200],
    }
    try:
        EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with EVENTS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except OSError as e:
        logger.warning(f"fallback_stats: could not persist event: {e}")

    logger.warning(f"LEGACY FALLBACK ACTIVATED: {component} — {reason}")

    now = time.time()
    with _lock:
        if now - _last_alert.get(component, 0.0) < ALERT_THROTTLE_S:
            return
        _last_alert[component] = now

    webhook = os.environ.get("DISCORD_WEBHOOK_ALERTS", "")
    if not webhook:
        return

    def _send() -> None:
        try:
            import httpx

            httpx.post(webhook, json={"content": (
                f"⚠️ **Legacy fallback activated: `{component}`**\n"
                f"Reason: `{reason[:150]}`\n"
                f"A channel session was unhealthy and traffic used the legacy "
                f"path. Counted in `data/fallback_events.jsonl` for the "
                f"router_v2 deprecation decision. (Throttled to 1/h per component.)"
            )}, timeout=10)
        except Exception:
            pass

    threading.Thread(target=_send, daemon=True).start()


def summary(days: int = 30) -> dict:
    """Activation counts per component over the last N days."""
    cutoff = datetime.now() - timedelta(days=days)
    counts: dict[str, int] = {}
    last_seen: dict[str, str] = {}
    try:
        with EVENTS_PATH.open(encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if datetime.fromisoformat(e["ts"]) < cutoff:
                        continue
                    c = e.get("component", "unknown")
                    counts[c] = counts.get(c, 0) + 1
                    last_seen[c] = e["ts"]
                except (ValueError, KeyError):
                    continue
    except OSError:
        pass
    return {"days": days, "activations": counts, "last_seen": last_seen}
