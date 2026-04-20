"""Backfill 90 days of Garmin HRV + stress + sleep + RHR into garmin_daily_summary.

Steps are already populated by the existing sync. This fills the gaps:
- hrv_weekly_avg / hrv_last_night / hrv_status (never populated — column added today)
- avg_stress (never populated despite column existing)
- sleep_score / resting_hr / sleep_hours (only ~70% populated)

Safe to re-run — uses upsert on (user_id, date).
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta

import httpx
import garth

# Make project imports work when running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from domains.nutrition.services.garmin import _get_client  # noqa: E402

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
USER_ID = "chris"
DAYS = int(os.environ.get("BACKFILL_DAYS", "90"))


def _sleep_values(day_iso: str) -> dict:
    try:
        sleep = garth.DailySleepData.get(day_iso)
    except Exception:
        return {}
    if not sleep or not getattr(sleep, "daily_sleep_dto", None):
        return {}
    dto = sleep.daily_sleep_dto
    out: dict = {}
    secs = dto.sleep_time_seconds or 0
    if secs:
        out["sleep_hours"] = round(secs / 3600, 1)
    if dto.sleep_scores and dto.sleep_scores.overall:
        out["sleep_score"] = dto.sleep_scores.overall.value
    rhr = getattr(sleep, "resting_heart_rate", None)
    if rhr is not None:
        out["resting_hr"] = int(rhr)
    return out


def _hrv_map(end_date: date, days: int) -> dict[str, dict]:
    """Bulk-fetch HRV for a date range, returning {iso_date: {...fields}}."""
    try:
        rows = garth.DailyHRV.list(end=end_date, period=days)
    except Exception as e:
        print(f"  HRV list failed: {e}")
        return {}
    out: dict[str, dict] = {}
    for h in rows or []:
        iso = h.calendar_date.isoformat()
        entry: dict = {}
        if getattr(h, "weekly_avg", None) is not None:
            entry["hrv_weekly_avg"] = int(h.weekly_avg)
        if getattr(h, "last_night_avg", None) is not None:
            entry["hrv_last_night"] = int(h.last_night_avg)
        if getattr(h, "status", None):
            entry["hrv_status"] = str(h.status)
        if entry:
            out[iso] = entry
    return out


def _stress_map(end_date: date, days: int) -> dict[str, dict]:
    """Bulk-fetch stress for a date range."""
    try:
        rows = garth.DailyStress.list(end=end_date, period=days)
    except Exception as e:
        print(f"  Stress list failed: {e}")
        return {}
    out: dict[str, dict] = {}
    for s in rows or []:
        overall = getattr(s, "overall_stress_level", None)
        if overall is not None and overall >= 0:
            out[s.calendar_date.isoformat()] = {"avg_stress": int(overall)}
    return out


async def _upsert(client: httpx.AsyncClient, record: dict) -> bool:
    r = await client.post(
        f"{SUPABASE_URL}/rest/v1/garmin_daily_summary",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        params={"on_conflict": "user_id,date"},
        json=record,
    )
    if r.status_code not in (200, 201, 204):
        print(f"    upsert failed {r.status_code}: {r.text[:200]}")
        return False
    return True


async def main() -> None:
    _get_client()  # auth once
    end = date.today()
    start = end - timedelta(days=DAYS)
    print(f"Backfilling {start} -> {end} ({DAYS} days) into garmin_daily_summary")

    # Bulk-fetch HRV and stress once — much faster than per-day calls.
    print("Fetching HRV (bulk)...")
    hrv_map = await asyncio.to_thread(_hrv_map, end, DAYS + 1)
    print(f"  got HRV for {len(hrv_map)} days")
    print("Fetching stress (bulk)...")
    stress_map = await asyncio.to_thread(_stress_map, end, DAYS + 1)
    print(f"  got stress for {len(stress_map)} days")

    filled = {"sleep": 0, "hrv": 0, "stress": 0, "rows": 0}
    async with httpx.AsyncClient(timeout=20) as client:
        for offset in range(DAYS + 1):
            day = end - timedelta(days=offset)
            day_iso = day.isoformat()
            record = {"user_id": USER_ID, "date": day_iso, "source": "garmin"}

            sleep = await asyncio.to_thread(_sleep_values, day_iso)
            hrv = hrv_map.get(day_iso, {})
            stress = stress_map.get(day_iso, {})

            record.update(sleep)
            record.update(hrv)
            record.update(stress)

            if not (sleep or hrv or stress):
                print(f"  {day_iso}: no data")
                continue

            ok = await _upsert(client, record)
            if ok:
                filled["rows"] += 1
                if sleep:
                    filled["sleep"] += 1
                if hrv:
                    filled["hrv"] += 1
                if stress:
                    filled["stress"] += 1
                parts = []
                if sleep:
                    parts.append(
                        f"sleep={sleep.get('sleep_score')}/{sleep.get('sleep_hours')}h rhr={sleep.get('resting_hr')}"
                    )
                if hrv:
                    parts.append(
                        f"hrv={hrv.get('hrv_last_night')} wkly={hrv.get('hrv_weekly_avg')}"
                    )
                if stress:
                    parts.append(f"stress={stress.get('avg_stress')}")
                print(f"  {day_iso}: {' '.join(parts)}")
            # Only sleep is per-day; light pacing just for that.
            await asyncio.sleep(0.15)

    print()
    print(f"DONE: {filled['rows']} rows upserted "
          f"(sleep={filled['sleep']}, hrv={filled['hrv']}, stress={filled['stress']})")


if __name__ == "__main__":
    asyncio.run(main())
