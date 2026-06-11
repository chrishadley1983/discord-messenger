"""Appliance event detection from Home Mini telemetry.

Every scan, reads recent raw 10s samples from data/energy_telemetry.jsonl,
segments sustained loads above a rolling baseline, classifies them by power
and duration, and upserts into the energy_events table:

- kettle        : +1.6–3.3 kW for ≤ 6 min
- ev_charge     : +4.5 kW+ for ≥ 15 min (or any event inside an Intelligent
                  Go dispatch window)
- oven_or_heater: +1.2–3.3 kW for > 8 min
- high_load     : anything else ≥ 1.2 kW for ≥ 5 min
- spike         : ≥ 3.5 kW shorter than 5 min (shower pump, vacuum, etc.)

A sustained high_load/oven event over ALERT_MINUTES posts a throttled
#alerts warning ("something's been drawing 2kW for 2 hours").
State (last processed timestamp) lives in data/energy_events_state.json.
"""

from __future__ import annotations

import json
import os
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from logger import logger
from .config import SUPABASE_KEY, SUPABASE_URL, TELEMETRY_LOG

STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "energy_events_state.json"
HADLEY_ALERT_URL = "http://localhost:8100/alert"

LOOKBACK_MINUTES = 120
EVENT_DELTA_W = 1200          # rise above baseline that opens an event
EVENT_CLOSE_W = 500           # within this of baseline closes it
MIN_EVENT_SECONDS = 60
ALERT_MINUTES = 75            # sustained-load alert; must stay well below
                              # LOOKBACK_MINUTES*0.9 or it can never fire
ALERT_UNOCCUPIED_MINUTES = 30  # faster alert when nobody seems home
ZIGBEE_API_URL = "http://192.168.0.110:5001"  # Pi zigbee2mqtt bridge

# Current Intelligent Go peak rate fallback for cost estimates (p/kWh)
FALLBACK_RATE_P = 27.0


def _load_samples(since: datetime) -> list[dict]:
    if not TELEMETRY_LOG.exists():
        return []
    out = []
    for line in TELEMETRY_LOG.read_text(encoding="utf-8").splitlines():
        try:
            s = json.loads(line)
        except json.JSONDecodeError:
            continue
        if s.get("readAt") and s.get("demand") is not None and s["readAt"] >= since.isoformat():
            out.append(s)
    out.sort(key=lambda s: s["readAt"])
    return out


def _classify(avg_delta_w: float, duration_s: float, started: datetime) -> str:
    from .dispatches import in_dispatch_window
    if avg_delta_w >= 4500 and duration_s >= 900:
        return "ev_charge"
    if duration_s >= 900 and in_dispatch_window(started):
        return "ev_charge"
    if 1600 <= avg_delta_w <= 3300 and duration_s <= 360:
        return "kettle"
    if avg_delta_w >= 3500 and duration_s < 300:
        return "spike"
    if 1200 <= avg_delta_w <= 3300 and duration_s > 480:
        return "oven_or_heater"
    return "high_load"


def _detect_events(samples: list[dict]) -> list[dict]:
    if len(samples) < 30:
        return []

    demands = [float(s["demand"]) for s in samples]
    # 10th percentile, not median: with a dominant load (EV at 7kW for
    # hours) the median sits ON the load and masks every other event.
    baseline = statistics.quantiles(demands, n=10)[0]

    events = []
    open_event: dict | None = None
    for s in samples:
        d = float(s["demand"])
        ts = datetime.fromisoformat(s["readAt"].replace("Z", "+00:00"))
        if open_event is None:
            if d >= baseline + EVENT_DELTA_W:
                open_event = {"start": ts, "peaks": [d], "last": ts}
        else:
            if d <= baseline + EVENT_CLOSE_W:
                events.append({**open_event, "end": ts})
                open_event = None
            else:
                open_event["peaks"].append(d)
                open_event["last"] = ts

    # an event still open at the window edge is reported without an end
    if open_event is not None:
        events.append({**open_event, "end": None})

    window_start = datetime.fromisoformat(samples[0]["readAt"].replace("Z", "+00:00"))
    out = []
    for e in events:
        end = e["end"] or e["last"]
        duration = (end - e["start"]).total_seconds()
        if duration < MIN_EVENT_SECONDS:
            continue
        avg = sum(e["peaks"]) / len(e["peaks"])
        avg_delta = avg - baseline
        kwh = avg_delta / 1000 * duration / 3600
        # An event already running at the window edge has an unknown true
        # start — totals would understate (EV charges by 3-4x). Mark it and
        # null the energy figures; /energy/ev dispatches are the
        # authoritative source for EV charge totals.
        clipped = (e["start"] - window_start).total_seconds() < 60
        out.append({
            "started_at": e["start"].isoformat(),
            "ended_at": e["end"].isoformat() if e["end"] else None,
            "event_type": _classify(avg_delta, duration, e["start"]),
            "avg_demand_w": round(avg, 0),
            "peak_demand_w": round(max(e["peaks"]), 0),
            "energy_kwh": None if clipped else round(kwh, 3),
            "cost_pence": None if clipped else round(kwh * FALLBACK_RATE_P, 1),
            "detail": {"baseline_w": round(baseline, 0), "duration_s": int(duration),
                       "ongoing": e["end"] is None, "window_clipped": clipped},
        })
    return out


def _store_events(events: list[dict]) -> int:
    """Store COMPLETED events only, deduped by time overlap.

    Ongoing events are never stored (they'd freeze at the first-detection
    snapshot and duplicate on later scans when the detected start shifts) —
    they exist for alerting only; once finished, the next scan stores the
    final, stable version. Dedupe is by overlap with any existing event of
    the same type, which is robust to start-time jitter between scans.
    """
    stored = 0
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    for ev in events:
        if ev["detail"].get("ongoing") or not ev["ended_at"]:
            continue
        existing = httpx.get(
            f"{SUPABASE_URL}/rest/v1/energy_events",
            headers=headers,
            params=[("select", "id"), ("event_type", f"eq.{ev['event_type']}"),
                    ("started_at", f"lte.{ev['ended_at']}"),
                    ("ended_at", f"gte.{ev['started_at']}"),
                    ("limit", "1")],
            timeout=15,
        )
        if existing.status_code == 200 and existing.json():
            continue
        resp = httpx.post(f"{SUPABASE_URL}/rest/v1/energy_events",
                          headers=headers, json=ev, timeout=15)
        if resp.status_code < 300:
            stored += 1
    return stored


def _lounge_occupied() -> bool | None:
    """Occupancy from the lounge motion sensor; None if unreachable."""
    try:
        resp = httpx.get(ZIGBEE_API_URL, timeout=5)
        data = resp.json()
        occ = (data.get("motion_lounge") or {}).get("occupancy")
        return bool(occ) if occ is not None else None
    except Exception:
        return None


def _maybe_alert_sustained(events: list[dict]) -> None:
    occupied = _lounge_occupied()
    threshold_min = ALERT_UNOCCUPIED_MINUTES if occupied is False else ALERT_MINUTES
    for ev in events:
        if not ev["detail"].get("ongoing") or ev["event_type"] == "ev_charge":
            continue
        if ev["detail"]["duration_s"] >= threshold_min * 60:
            try:
                httpx.post(
                    HADLEY_ALERT_URL,
                    headers={"x-api-key": os.environ.get("HADLEY_AUTH_KEY", "")},
                    json={
                        "message": (
                            f"Sustained electrical load: ~{ev['avg_demand_w']:.0f}W for "
                            f"{ev['detail']['duration_s'] // 60} min "
                            f"({ev['event_type']}) — oven/heater left on?"
                            + (" No lounge motion — house may be empty."
                               if occupied is False else "")
                        ),
                        "source": "energy-events",
                        "throttle_minutes": 120,
                    },
                    timeout=10,
                )
            except Exception as e:
                logger.debug(f"sustained-load alert failed: {e}")


def scan_once() -> dict:
    """One event-detection pass (sync; wrap in to_thread)."""
    since = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)
    samples = _load_samples(since)
    events = _detect_events(samples)
    stored = _store_events(events)
    _maybe_alert_sustained(events)
    return {"samples": len(samples), "events_found": len(events), "events_stored": stored}


def register(scheduler) -> None:
    import asyncio

    async def _scan_job():
        try:
            await asyncio.to_thread(scan_once)
        except Exception as e:
            logger.debug(f"energy event scan failed: {e}")

    scheduler.add_job(
        _scan_job, "interval", minutes=5,
        id="energy_event_scan", max_instances=1,
        coalesce=True, replace_existing=True,
    )
    logger.info("Energy event scan registered (every 5 min)")
