"""Octopus Home Mini live telemetry poller.

Every POLL_SECONDS the poller fetches 10-second telemetry since the last
sample from Kraken's smartMeterTelemetry, then:

1. appends raw samples to data/energy_telemetry.jsonl (ring-trimmed to
   ~RETENTION_HOURS so 10s data doesn't grow unbounded),
2. upserts 1-minute aggregates into Supabase ``energy_live``
   (avg/max/min demand W + Wh delta from the meter's cumulative register),
3. keeps an in-memory "latest" snapshot the API endpoints read for free.

Failures are quiet at debug level (wifi blips are normal) but a stall
counter escalates: STALL_ALERT_POLLS consecutive empty/failed polls posts a
throttled #alerts warning via the Hadley API /alert endpoint — this
pipeline gets the watchdog its predecessors never had.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

import httpx

from logger import logger
from .config import SMART_DEVICE_ID, SUPABASE_KEY, SUPABASE_URL, TELEMETRY_LOG

POLL_SECONDS = 30
RETENTION_HOURS = 48
STALL_ALERT_POLLS = 20  # ~10 min of nothing → alert
HADLEY_ALERT_URL = "http://localhost:8100/alert"

_TELEMETRY_QUERY = """
query($d: String!, $s: DateTime!, $e: DateTime!) {
  smartMeterTelemetry(deviceId: $d, grouping: TEN_SECONDS, start: $s, end: $e) {
    readAt demand consumption consumptionDelta costDeltaWithTax
  }
}
"""

# In-memory state shared with API endpoints (single bot process)
latest: dict = {"read_at": None, "demand_w": None, "updated_at": None}
_last_read_at: datetime | None = None
_stall_count = 0
_alerted = False

# Minute buffer: samples accumulate per minute across polls and a minute is
# only upserted once a LATER minute has samples (i.e. it is complete). A
# straight per-poll upsert with merge-duplicates REPLACED rows, keeping only
# the last poll's 1-3 samples per minute — /energy/today under-counted kWh
# by 50-85% (caught by the Jun 2026 validation review).
_minute_buf: dict[str, list[dict]] = {}


def _fetch_since(start: datetime, end: datetime) -> list[dict]:
    from .kraken import gql

    data = gql(_TELEMETRY_QUERY, {
        "d": SMART_DEVICE_ID,
        "s": start.isoformat(),
        "e": end.isoformat(),
    })
    return data.get("smartMeterTelemetry") or []


def _append_log(samples: list[dict]) -> None:
    TELEMETRY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(TELEMETRY_LOG, "a", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s) + "\n")


def _trim_log() -> None:
    """Ring-trim the raw log (called occasionally, not every poll)."""
    if not TELEMETRY_LOG.exists() or TELEMETRY_LOG.stat().st_size < 20_000_000:
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)).isoformat()
    lines = TELEMETRY_LOG.read_text(encoding="utf-8").splitlines()
    kept = [l for l in lines if l[12:37] >= cutoff or json.loads(l).get("readAt", "") >= cutoff]
    TELEMETRY_LOG.write_text("\n".join(kept) + "\n", encoding="utf-8")
    logger.info(f"energy telemetry log trimmed: {len(lines)} -> {len(kept)} lines")


def _upsert_minutes(samples: list[dict]) -> int:
    """Buffer samples per minute; upsert only minutes that are complete.

    A minute is complete when a later minute has samples (or it has aged out
    by 5+ minutes). Each upsert aggregates ALL buffered samples for that
    minute, so rows are written once, whole.
    """
    for s in samples:
        if s.get("readAt") and s.get("demand") is not None:
            _minute_buf.setdefault(s["readAt"][:16] + ":00", []).append(s)
    if not _minute_buf:
        return 0

    newest_minute = max(_minute_buf)
    age_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()[:16] + ":00"
    flushable = [m for m in _minute_buf if m < newest_minute or m < age_cutoff]

    rows = []
    for minute in sorted(flushable):
        group = _minute_buf.pop(minute)
        demands = [float(g["demand"]) for g in group]
        # consumptionDelta is Wh within the sample; sum for the minute
        wh = sum(float(g.get("consumptionDelta") or 0) for g in group)
        rows.append({
            "minute_start": minute,
            "demand_w_avg": round(sum(demands) / len(demands), 1),
            "demand_w_max": max(demands),
            "demand_w_min": min(demands),
            "consumption_wh": round(wh, 2),
            "sample_count": len(group),
        })
    if not rows:
        return 0

    resp = httpx.post(
        f"{SUPABASE_URL}/rest/v1/energy_live",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        params={"on_conflict": "minute_start"},
        json=rows,
        timeout=20,
    )
    if resp.status_code >= 300:
        logger.warning(f"energy_live upsert failed: {resp.status_code} {resp.text[:150]}")
        return 0
    return len(rows)


def _maybe_alert_stall() -> None:
    global _alerted
    if _alerted:
        return
    try:
        httpx.post(
            HADLEY_ALERT_URL,
            headers={"x-api-key": os.environ.get("HADLEY_AUTH_KEY", "")},
            json={
                "message": "Home Mini telemetry stalled — no live energy data for 10+ min "
                           "(Mini offline? wifi? Kraken API?)",
                "source": "energy-telemetry",
            },
            timeout=10,
        )
        _alerted = True
    except Exception as e:
        logger.debug(f"telemetry stall alert failed: {e}")


def poll_once() -> dict:
    """One poll cycle (sync; callers wrap in to_thread)."""
    global _last_read_at, _stall_count, _alerted

    now = datetime.now(timezone.utc)
    start = _last_read_at + timedelta(seconds=1) if _last_read_at else now - timedelta(minutes=5)
    try:
        samples = _fetch_since(start, now)
    except Exception as e:
        _stall_count += 1
        if _stall_count >= STALL_ALERT_POLLS:
            _maybe_alert_stall()
        logger.debug(f"telemetry poll failed ({_stall_count}): {e}")
        return {"ok": False, "error": str(e)[:120]}

    # Kraken returns samples at/before the requested start — filter to
    # strictly newer than the last processed sample, else the raw log gets
    # duplicates and consumptionDelta double-counts within the minute.
    if _last_read_at is not None:
        cutoff_iso = _last_read_at.isoformat()
        samples = [s for s in samples
                   if datetime.fromisoformat(s["readAt"].replace("Z", "+00:00")).isoformat() > cutoff_iso]

    if not samples:
        _stall_count += 1
        if _stall_count >= STALL_ALERT_POLLS:
            _maybe_alert_stall()
        return {"ok": True, "samples": 0}

    _stall_count = 0
    _alerted = False
    _last_read_at = datetime.fromisoformat(samples[-1]["readAt"].replace("Z", "+00:00"))

    latest.update({
        "read_at": samples[-1]["readAt"],
        "demand_w": float(samples[-1]["demand"]) if samples[-1].get("demand") is not None else None,
        "updated_at": now.isoformat(),
    })

    _append_log(samples)
    minutes = _upsert_minutes(samples)
    if minutes and now.minute % 30 == 0:
        _trim_log()
    return {"ok": True, "samples": len(samples), "minutes_upserted": minutes}


def register(scheduler) -> None:
    """Register the poller as a quiet infrastructure job."""

    async def _poll_job():
        await asyncio.to_thread(poll_once)

    scheduler.add_job(
        _poll_job,
        "interval",
        seconds=POLL_SECONDS,
        id="energy_telemetry_poll",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    logger.info(f"Energy telemetry poller registered (every {POLL_SECONDS}s)")
