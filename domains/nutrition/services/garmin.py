"""Garmin Connect service for fitness tracking.

Date-handling note: overnight metrics (sleep, resting HR, HRV) for the
*current* calendar day are typically NOT yet synced from the watch when the
morning digest runs (~07:55). They only become available under a completed
calendar date once the watch syncs. Steps and stress have same-day intraday
values so they're reliable immediately. To avoid silently dropping nights,
the sleep/HR/HRV fetchers scan back for the most recent *populated* record
rather than blindly querying today.
"""

import asyncio
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import garth

from config import GARMIN_EMAIL, GARMIN_PASSWORD
from logger import logger

_client = None
_last_api_success = 0.0  # timestamp of last successful API call

# Session storage directory
SESSION_DIR = Path(os.getenv("LOCALAPPDATA", ".")) / "discord-assistant" / "garmin_session"

# Re-authenticate if no successful API call in this many seconds
_SESSION_MAX_AGE = 3600  # 1 hour


def _save_session():
    """Save current garth session to disk."""
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        garth.save(str(SESSION_DIR))
        logger.debug("Garmin session saved")
    except Exception as e:
        logger.warning(f"Failed to save Garmin session: {e}")


def _invalidate_client():
    """Clear cached client so next call re-authenticates."""
    global _client, _last_api_success
    _client = None
    _last_api_success = 0.0


def _get_client() -> garth.Client:
    """Get or create authenticated Garmin client.

    Invalidates the cached client if no successful API call within _SESSION_MAX_AGE,
    forcing a session reload which triggers garth's automatic token refresh.
    """
    global _client, _last_api_success

    # Invalidate stale client (forces session reload + token refresh)
    if _client is not None and (time.time() - _last_api_success) > _SESSION_MAX_AGE:
        logger.info("Garmin client stale (no recent success), reloading session...")
        _client = None

    if _client is not None:
        return _client

    if not GARMIN_EMAIL or not GARMIN_PASSWORD:
        raise ValueError("Garmin credentials not configured")

    # Try to load existing session
    if SESSION_DIR.exists():
        try:
            logger.info("Loading existing Garmin session...")
            garth.resume(str(SESSION_DIR))
            _client = garth.client
            logger.info("Garmin session loaded successfully")
            return _client
        except Exception as e:
            logger.warning(f"Failed to load Garmin session: {e}")

    # Fresh login required
    logger.info("Authenticating with Garmin Connect (may require MFA)...")
    garth.login(GARMIN_EMAIL, GARMIN_PASSWORD)
    _client = garth.client
    _save_session()

    logger.info("Garmin authentication successful")
    return _client


async def get_steps(date_str: str | None = None) -> dict:
    """Get step count from Garmin for a given date (default: today).

    Args:
        date_str: Date in YYYY-MM-DD format, or None for today.
    """
    try:
        _get_client()  # Ensure authenticated
        target_date = date.fromisoformat(date_str) if date_str else date.today()

        # Use garth stats API
        steps_data = garth.DailySteps.list(end=target_date, period=1)

        # Mark successful API call and save refreshed session
        global _last_api_success
        _last_api_success = time.time()
        _save_session()

        if steps_data:
            step = steps_data[0]
            steps = step.total_steps if step.total_steps is not None else 0
            goal = step.step_goal or 15000

            result = {
                "steps": steps,
                "goal": goal,
                "percentage": round((steps / goal) * 100) if goal else 0,
                "date": target_date.isoformat()
            }

            logger.info(f"Retrieved Garmin steps for {target_date}: {steps}/{goal}")
            return result

        return {"steps": 0, "goal": 15000, "percentage": 0, "date": target_date.isoformat()}
    except Exception as e:
        logger.error(f"Garmin API error: {e}")
        _invalidate_client()  # Force re-auth on next call
        return {"error": str(e), "steps": None, "goal": None, "percentage": None}


def _latest_sleep(max_lookback: int = 4):
    """Most recent DailySleepData with an actual sleep session.

    Garmin keys a night's sleep under the calendar date it *ends* on. The
    current day's record is usually empty at digest time (watch not synced),
    so scan back up to `max_lookback` days and return the first populated
    record along with the date it belongs to.

    Returns (sleep_obj, date) or (None, None) if nothing is available.
    """
    today = date.today()
    for i in range(max_lookback + 1):
        d = today - timedelta(days=i)
        try:
            sleep = garth.DailySleepData.get(d.isoformat())
        except Exception:
            sleep = None
        dto = getattr(sleep, "daily_sleep_dto", None) if sleep else None
        if dto and (dto.sleep_time_seconds or 0) > 0:
            return sleep, d
    return None, None


async def get_sleep(date_str: str | None = None) -> dict:
    """Get sleep data from Garmin.

    Args:
        date_str: Specific date (YYYY-MM-DD) to fetch. When omitted, returns
            the most recent night that actually has data (handles the common
            case where last night hasn't synced yet).
    """
    try:
        _get_client()  # Ensure authenticated

        if date_str:
            sleep = garth.DailySleepData.get(date_str)
            sleep_date = date.fromisoformat(date_str)
            if not sleep or not getattr(sleep, "daily_sleep_dto", None):
                return {"error": "No sleep data", "total_hours": None, "date": date_str}
        else:
            sleep, sleep_date = _latest_sleep()
            if not sleep or not sleep.daily_sleep_dto:
                return {"error": "No sleep data", "total_hours": None, "date": None}

        dto = sleep.daily_sleep_dto
        sleep_seconds = dto.sleep_time_seconds or 0
        sleep_hours = round(sleep_seconds / 3600, 1)

        # Sleep quality score
        quality_score = None
        if dto.sleep_scores and dto.sleep_scores.overall:
            quality_score = dto.sleep_scores.overall.value

        result = {
            "total_hours": sleep_hours,
            "quality_score": quality_score,
            "resting_hr": getattr(sleep, "resting_heart_rate", None),
            "date": sleep_date.isoformat() if sleep_date else None,
            "deep_hours": round((dto.deep_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'deep_sleep_seconds') and dto.deep_sleep_seconds else 0,
            "light_hours": round((dto.light_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'light_sleep_seconds') and dto.light_sleep_seconds else 0,
            "rem_hours": round((dto.rem_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'rem_sleep_seconds') and dto.rem_sleep_seconds else 0,
            "awake_hours": round((dto.awake_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'awake_sleep_seconds') and dto.awake_sleep_seconds else 0
        }

        logger.info(f"Retrieved Garmin sleep ({result['date']}): {sleep_hours}h, score: {quality_score}")
        return result
    except Exception as e:
        logger.error(f"Garmin sleep API error: {e}")
        return {"error": str(e), "total_hours": None}


async def get_heart_rate() -> dict:
    """Get resting heart rate from Garmin (most recent populated night)."""
    try:
        _get_client()  # Ensure authenticated

        # Resting HR comes from the sleep record. Use the most recent night
        # that actually has data rather than today's (usually-empty) record.
        sleep, sleep_date = _latest_sleep()
        resting_hr = getattr(sleep, "resting_heart_rate", None) if sleep else None

        result = {
            "resting": resting_hr,
            "date": sleep_date.isoformat() if sleep_date else None,
            "min": None,
            "max": None,
            "average": None
        }

        logger.info(f"Retrieved Garmin HR: resting={resting_hr} ({result['date']})")
        return result
    except Exception as e:
        logger.error(f"Garmin HR API error: {e}")
        return {"error": str(e), "resting": None}


async def get_daily_summary() -> dict:
    """Get comprehensive daily health summary from Garmin."""
    global _last_api_success
    try:
        _get_client()  # Ensure authenticated
        today = date.today()

        result = {
            "steps": {"count": 0, "goal": 15000},
            "heart_rate": {"resting": None, "min": None, "max": None, "average": None},
            "stress": {"average": None, "max": None},
            "calories": {"total": None, "active": None, "bmr": None},
            "sleep": {}
        }

        # Get steps
        try:
            steps_data = garth.DailySteps.list(end=today, period=1)
            if steps_data:
                step = steps_data[0]
                result["steps"] = {
                    "count": step.total_steps if step.total_steps is not None else 0,
                    "goal": step.step_goal or 15000
                }
            _last_api_success = time.time()
            _save_session()
        except Exception as e:
            logger.warning(f"Failed to get steps: {e}")

        # Get sleep data
        try:
            sleep = garth.DailySleepData.get(today.isoformat())
            if sleep and sleep.daily_sleep_dto:
                dto = sleep.daily_sleep_dto
                sleep_seconds = dto.sleep_time_seconds or 0
                quality_score = None
                if dto.sleep_scores and dto.sleep_scores.overall:
                    quality_score = dto.sleep_scores.overall.value

                result["sleep"] = {
                    "total_hours": round(sleep_seconds / 3600, 1),
                    "quality_score": quality_score,
                    "deep_hours": round((dto.deep_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'deep_sleep_seconds') and dto.deep_sleep_seconds else 0,
                    "rem_hours": round((dto.rem_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'rem_sleep_seconds') and dto.rem_sleep_seconds else 0
                }

                # Get resting HR from sleep
                if sleep.resting_heart_rate:
                    result["heart_rate"]["resting"] = sleep.resting_heart_rate
        except Exception as e:
            logger.warning(f"Failed to get sleep: {e}")

        # Get HRV
        try:
            hrv = _latest_hrv()
            if hrv and getattr(hrv, "weekly_avg", None):
                result["hrv"] = {
                    "weekly_avg": hrv.weekly_avg,
                    "last_night": getattr(hrv, "last_night_avg", None),
                    "status": getattr(hrv, "status", None),
                }
        except Exception as e:
            logger.warning(f"Failed to get HRV: {e}")

        # Get stress
        try:
            stress = _latest_stress()
            overall = getattr(stress, "overall_stress_level", None) if stress else None
            if overall is not None and overall >= 0:
                result["stress"] = {"average": overall, "max": None}
        except Exception as e:
            logger.warning(f"Failed to get stress: {e}")

        logger.info(f"Retrieved Garmin daily summary")
        return result
    except Exception as e:
        logger.error(f"Garmin summary API error: {e}")
        return {"error": str(e)}


def _latest_hrv():
    """Most recent populated DailyHRV row.

    garth exposes .list() not .get() — the single-item variant silently 404s
    on this garth version. Critically, `period=1, end=today` returns ONLY
    today's row, which doesn't exist until tonight's sleep is processed — so
    it almost always came back empty. Pull a 7-day window and return the most
    recent row that has data (rows come back oldest→newest)."""
    rows = garth.DailyHRV.list(end=date.today(), period=7) or []
    for row in reversed(rows):
        if getattr(row, "weekly_avg", None) is not None or getattr(row, "last_night_avg", None) is not None:
            return row
    return None


def _latest_stress():
    """Most recent DailyStress row."""
    rows = garth.DailyStress.list(end=date.today(), period=1)
    return rows[0] if rows else None


async def get_hrv() -> dict:
    """Get HRV data from Garmin (weekly avg + last night + status)."""
    try:
        _get_client()
        hrv = _latest_hrv()
        if hrv and getattr(hrv, "weekly_avg", None):
            hrv_date = getattr(hrv, "calendar_date", None)
            result = {
                "weekly_avg": hrv.weekly_avg,
                "last_night": getattr(hrv, "last_night_avg", None),
                "status": getattr(hrv, "status", None),
                "date": hrv_date.isoformat() if hrv_date else None,
            }
            logger.info(f"Retrieved Garmin HRV ({result['date']}): weekly_avg={result['weekly_avg']}ms")
            return result
        return {"weekly_avg": None, "last_night": None, "status": None}
    except Exception as e:
        logger.error(f"Garmin HRV API error: {e}")
        return {"error": str(e), "weekly_avg": None}


async def get_stress() -> dict:
    """Get today's average stress level (0-100)."""
    try:
        _get_client()
        stress = _latest_stress()
        overall = getattr(stress, "overall_stress_level", None) if stress else None
        if overall is not None and overall >= 0:
            logger.info(f"Retrieved Garmin stress: avg={overall}")
            return {"average": overall}
        return {"average": None}
    except Exception as e:
        logger.error(f"Garmin stress API error: {e}")
        return {"error": str(e), "average": None}


# ══════════════════════════════════════════════════════════════════════
# DAILY SUMMARY SYNC (self-healing multi-day upsert)
# ══════════════════════════════════════════════════════════════════════


def _sleep_metrics(day_iso: str) -> dict:
    """Sleep/RHR fields for one calendar date, keyed for garmin_daily_summary."""
    try:
        sleep = garth.DailySleepData.get(day_iso)
    except Exception:
        return {}
    dto = getattr(sleep, "daily_sleep_dto", None) if sleep else None
    if not dto:
        return {}
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
    """Bulk HRV for a date range → {iso_date: {hrv fields}}."""
    try:
        rows = garth.DailyHRV.list(end=end_date, period=days)
    except Exception as e:
        logger.warning(f"HRV bulk fetch failed: {e}")
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
    """Bulk stress for a date range → {iso_date: {avg_stress}}."""
    try:
        rows = garth.DailyStress.list(end=end_date, period=days)
    except Exception as e:
        logger.warning(f"Stress bulk fetch failed: {e}")
        return {}
    out: dict[str, dict] = {}
    for s in rows or []:
        overall = getattr(s, "overall_stress_level", None)
        if overall is not None and overall >= 0:
            out[s.calendar_date.isoformat()] = {"avg_stress": int(overall)}
    return out


def _steps_map(end_date: date, days: int) -> dict[str, dict]:
    """Bulk steps for a date range → {iso_date: {steps, steps_goal}}."""
    try:
        rows = garth.DailySteps.list(end=end_date, period=days)
    except Exception as e:
        logger.warning(f"Steps bulk fetch failed: {e}")
        return {}
    out: dict[str, dict] = {}
    for s in rows or []:
        cd = getattr(s, "calendar_date", None)
        if cd is None or s.total_steps is None:
            continue
        out[cd.isoformat()] = {"steps": s.total_steps, "steps_goal": s.step_goal or 15000}
    return out


async def daily_summary_records(days: int = 3, end_date: date | None = None) -> list[dict]:
    """Build garmin_daily_summary rows for the last `days` completed days.

    Overnight metrics for a given night arrive late, so each morning we
    re-pull a short trailing window and upsert (on user_id,date). A night
    that hadn't synced yesterday gets filled in today — nothing is lost.

    Today's (partial) date is skipped for steps but still checked for
    sleep/HRV/stress in case they've already landed.
    """
    _get_client()
    end = end_date or date.today()

    # Bulk-fetch the windowed metrics off-thread (garth is blocking).
    hrv_map = await asyncio.to_thread(_hrv_map, end, days + 1)
    stress_map = await asyncio.to_thread(_stress_map, end, days + 1)
    steps_map = await asyncio.to_thread(_steps_map, end, days + 1)

    records: list[dict] = []
    for offset in range(days + 1):
        day = end - timedelta(days=offset)
        iso = day.isoformat()
        rec: dict = {"user_id": "chris", "date": iso, "source": "garmin"}

        rec.update(await asyncio.to_thread(_sleep_metrics, iso))
        rec.update(hrv_map.get(iso, {}))
        rec.update(stress_map.get(iso, {}))
        if offset > 0:  # skip today's still-accumulating step count
            rec.update(steps_map.get(iso, {}))

        # Only keep rows that carry real metrics (more than the 3 key fields).
        if len(rec) > 3:
            records.append(rec)

    return records
