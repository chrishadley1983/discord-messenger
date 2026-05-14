"""Cost rollup endpoint — merges router_v2 cost log and channel cost log.

router_v2.py writes per-call costs to data/cli_costs.jsonl (claude -p path,
confirmed programmatic after Jun 15 2026).

channel_cost_tail.py writes per-turn costs to data/channel_costs.jsonl
(the 3 Claude Code channel sessions — classification TBD on Jun 15).

This endpoint merges both, filters by window, and breaks down by source,
channel, and model so the daily digest can show a single number plus
where the spend is going.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/costs", tags=["costs"])

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLI_COST_LOG = PROJECT_ROOT / "data" / "cli_costs.jsonl"
CHANNEL_COST_LOG = PROJECT_ROOT / "data" / "channel_costs.jsonl"


def _parse_ts(raw: str) -> datetime | None:
    if not raw:
        return None
    # Trim trailing Z and parse as UTC; fall back to naive parse.
    s = raw.rstrip("Z")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _iter_entries(path: Path, cutoff: datetime):
    if not path.exists():
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                ts = _parse_ts(obj.get("timestamp", ""))
                if ts is None or ts < cutoff:
                    continue
                yield obj
    except Exception as e:
        logger.warning(f"cost_routes: failed reading {path.name}: {e}")


@router.get("/summary")
async def costs_summary(hours: int = Query(24, ge=1, le=24 * 90)):
    """Aggregate USD/GBP cost across router_v2 + channel sessions for the window."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    by_source: dict[str, dict] = {}
    by_channel: dict[str, dict] = {}
    by_model: dict[str, dict] = {}

    router_v2_usd = 0.0
    channels_usd = 0.0
    calls_total = 0

    def _bump(bucket: dict, key: str, cost: float):
        b = bucket.setdefault(key, {"calls": 0, "cost_usd": 0.0})
        b["calls"] += 1
        b["cost_usd"] += cost

    for obj in _iter_entries(CLI_COST_LOG, cutoff):
        cost = float(obj.get("cost_usd") or 0)
        source = obj.get("source") or "router_v2"
        channel = obj.get("channel") or "unknown"
        model = obj.get("model") or "unknown"
        router_v2_usd += cost
        calls_total += 1
        _bump(by_source, source, cost)
        _bump(by_channel, channel, cost)
        _bump(by_model, model, cost)

    for obj in _iter_entries(CHANNEL_COST_LOG, cutoff):
        cost = float(obj.get("cost_usd") or 0)
        source = obj.get("source") or "channel:unknown"
        channel = obj.get("channel") or "unknown"
        model = obj.get("model") or "unknown"
        channels_usd += cost
        calls_total += 1
        _bump(by_source, source, cost)
        _bump(by_channel, channel, cost)
        _bump(by_model, model, cost)

    total_usd = router_v2_usd + channels_usd
    USD_TO_GBP = 0.79

    def _sorted(d):
        return dict(
            sorted(
                ((k, {"calls": v["calls"], "cost_usd": round(v["cost_usd"], 4)}) for k, v in d.items()),
                key=lambda kv: kv[1]["cost_usd"],
                reverse=True,
            )
        )

    return {
        "window_hours": hours,
        "calls": calls_total,
        "total_usd": round(total_usd, 4),
        "total_gbp": round(total_usd * USD_TO_GBP, 4),
        "router_v2": {
            "cost_usd": round(router_v2_usd, 4),
            "note": "claude -p path — programmatic after Jun 15 2026",
        },
        "channels": {
            "cost_usd": round(channels_usd, 4),
            "note": "3 channel sessions — classification TBD, likely interactive subscription",
        },
        "by_source": _sorted(by_source),
        "by_channel": _sorted(by_channel),
        "by_model": _sorted(by_model),
    }
