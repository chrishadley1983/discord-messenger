"""Garmin Connect service for fitness tracking."""

import os
from datetime import date, datetime, timedelta
from pathlib import Path

import garth

from config import GARMIN_EMAIL, GARMIN_PASSWORD
from logger import logger

_client = None

# Session storage directory
SESSION_DIR = Path(os.getenv("LOCALAPPDATA", ".")) / "discord-assistant" / "garmin_session"


def _get_client() -> garth.Client:
    """Get or create authenticated Garmin client."""
    global _client
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

    # Save session for future use
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        garth.save(str(SESSION_DIR))
        logger.info(f"Garmin session saved to {SESSION_DIR}")
    except Exception as e:
        logger.warning(f"Failed to save Garmin session: {e}")

    logger.info("Garmin authentication successful")
    return _client


async def get_steps() -> dict:
    """Get today's step count from Garmin."""
    try:
        _get_client()  # Ensure authenticated
        today = date.today()

        # Use garth stats API
        steps_data = garth.DailySteps.list(end=today, period=1)
        if steps_data:
            step = steps_data[0]
            steps = step.total_steps
            goal = step.step_goal

            result = {
                "steps": steps,
                "goal": goal,
                "percentage": round((steps / goal) * 100) if goal else 0
            }

            logger.info(f"Retrieved Garmin steps: {steps}/{goal}")
            return result

        return {"steps": 0, "goal": 15000, "percentage": 0}
    except Exception as e:
        logger.error(f"Garmin API error: {e}")
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
                    "count": step.total_steps,
                    "goal": step.step_goal
                }
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

        logger.info(f"Retrieved Garmin daily summary")
        return result
    except Exception as e:
        logger.error(f"Garmin summary API error: {e}")
        return {"error": str(e)}
