"""Garmin Connect service for fitness tracking."""

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


async def get_sleep() -> dict:
    """Get last night's sleep data from Garmin."""
    try:
        _get_client()  # Ensure authenticated
        today = date.today().isoformat()

        # Get sleep data using garth
        sleep = garth.DailySleepData.get(today)

        if not sleep or not sleep.daily_sleep_dto:
            return {"error": "No sleep data", "total_hours": None}

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
            "deep_hours": round((dto.deep_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'deep_sleep_seconds') and dto.deep_sleep_seconds else 0,
            "light_hours": round((dto.light_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'light_sleep_seconds') and dto.light_sleep_seconds else 0,
            "rem_hours": round((dto.rem_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'rem_sleep_seconds') and dto.rem_sleep_seconds else 0,
            "awake_hours": round((dto.awake_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'awake_sleep_seconds') and dto.awake_sleep_seconds else 0
        }

        logger.info(f"Retrieved Garmin sleep: {sleep_hours}h, score: {quality_score}")
        return result
    except Exception as e:
        logger.error(f"Garmin sleep API error: {e}")
        return {"error": str(e), "total_hours": None}


async def get_heart_rate() -> dict:
    """Get today's heart rate data from Garmin."""
    try:
        _get_client()  # Ensure authenticated

        # Get resting HR from sleep data (most reliable source)
        today = date.today().isoformat()
        sleep = garth.DailySleepData.get(today)

        resting_hr = None
        if sleep:
            resting_hr = sleep.resting_heart_rate

        result = {
            "resting": resting_hr,
            "min": None,
            "max": None,
            "average": None
        }

        logger.info(f"Retrieved Garmin HR: resting={resting_hr}")
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
    """Most recent DailyHRV row. garth exposes .list() not .get() — the
    single-item variant silently 404s on this garth version."""
    rows = garth.DailyHRV.list(end=date.today(), period=1)
    return rows[0] if rows else None


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
            result = {
                "weekly_avg": hrv.weekly_avg,
                "last_night": getattr(hrv, "last_night_avg", None),
                "status": getattr(hrv, "status", None),
            }
            logger.info(f"Retrieved Garmin HRV: weekly_avg={result['weekly_avg']}ms")
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
