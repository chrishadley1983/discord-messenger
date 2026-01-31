"""Backfill historical health data from APIs.

Fetches 10 days of data from:
- Withings: Weight readings
- Garmin: Steps, sleep, heart rate

Run: py scripts/backfill_health_data.py
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
import garth

from config import (
    SUPABASE_URL,
    SUPABASE_KEY,
    WITHINGS_CLIENT_ID,
    WITHINGS_CLIENT_SECRET,
    WITHINGS_ACCESS_TOKEN,
    WITHINGS_REFRESH_TOKEN,
    GARMIN_EMAIL,
    GARMIN_PASSWORD
)
from logger import logger

# Session storage directory
SESSION_DIR = Path(os.getenv("LOCALAPPDATA", ".")) / "discord-assistant" / "garmin_session"

# Token storage for Withings
_withings_tokens = {
    "access": WITHINGS_ACCESS_TOKEN,
    "refresh": WITHINGS_REFRESH_TOKEN
}


def _get_supabase_headers():
    """Get headers for Supabase API calls."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }


async def _upsert_record(http_client: httpx.AsyncClient, table: str, data: dict, key_columns: list[str]) -> bool:
    """Upsert a record - try PATCH first (update), fall back to POST (insert)."""
    # Build filter for the key columns
    filters = "&".join(f"{col}=eq.{data[col]}" for col in key_columns)

    # Try PATCH first (update existing)
    response = await http_client.patch(
        f"{SUPABASE_URL}/rest/v1/{table}?{filters}",
        headers=_get_supabase_headers(),
        json=data,
        timeout=10
    )

    # 200 = success with body, 204 = success no content (both are success for PATCH)
    if response.status_code in (200, 204):
        return True

    # If PATCH failed, try POST (insert)
    response = await http_client.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=_get_supabase_headers(),
        json=data,
        timeout=10
    )

    return response.status_code in (200, 201)


async def refresh_withings_token() -> bool:
    """Refresh Withings OAuth token."""
    logger.info("Refreshing Withings token...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://wbsapi.withings.net/v2/oauth2",
                data={
                    "action": "requesttoken",
                    "grant_type": "refresh_token",
                    "client_id": WITHINGS_CLIENT_ID,
                    "client_secret": WITHINGS_CLIENT_SECRET,
                    "refresh_token": _withings_tokens["refresh"]
                }
            )

            data = response.json()
            if data["status"] == 0:
                _withings_tokens["access"] = data["body"]["access_token"]
                _withings_tokens["refresh"] = data["body"]["refresh_token"]
                logger.info("Withings token refreshed successfully")
                return True
            else:
                logger.error(f"Withings token refresh failed: {data}")
                return False
    except Exception as e:
        logger.error(f"Withings token refresh error: {e}")
        return False


async def backfill_withings_weight(days: int = 10) -> int:
    """Fetch and store weight readings from Withings for the past N days."""
    logger.info(f"Backfilling {days} days of Withings weight data...")

    if not _withings_tokens["access"]:
        logger.error("Withings not configured")
        return 0

    start_date = int((datetime.now() - timedelta(days=days)).timestamp())
    end_date = int(datetime.now().timestamp())

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://wbsapi.withings.net/measure",
                data={
                    "action": "getmeas",
                    "meastype": 1,  # Weight
                    "category": 1,  # Real measurements
                    "startdate": start_date,
                    "enddate": end_date
                },
                headers={"Authorization": f"Bearer {_withings_tokens['access']}"}
            )

            data = response.json()

            if data["status"] != 0:
                # Token may need refresh
                logger.warning("Withings token expired, refreshing...")
                if await refresh_withings_token():
                    return await backfill_withings_weight(days)
                return 0

            measures = data["body"]["measuregrps"]
            if not measures:
                logger.info("No Withings weight data found")
                return 0

            # Store each measurement
            stored_count = 0
            for measure in measures:
                weight_raw = measure["measures"][0]["value"]
                unit = measure["measures"][0]["unit"]
                weight_kg = round(weight_raw * (10 ** unit), 1)
                measured_at = datetime.fromtimestamp(measure["date"]).isoformat()

                # Insert into Supabase
                insert_response = await client.post(
                    f"{SUPABASE_URL}/rest/v1/weight_readings",
                    headers=_get_supabase_headers(),
                    json={
                        "user_id": "chris",
                        "weight_kg": weight_kg,
                        "measured_at": measured_at,
                        "source": "withings"
                    },
                    timeout=10
                )

                if insert_response.status_code in (200, 201):
                    stored_count += 1
                    logger.info(f"  Stored weight: {weight_kg}kg at {measured_at}")
                elif insert_response.status_code == 409:
                    logger.debug(f"  Duplicate: {weight_kg}kg at {measured_at}")
                else:
                    logger.warning(f"  Failed to store: {insert_response.text}")

            logger.info(f"Stored {stored_count} weight readings from Withings")
            return stored_count

    except Exception as e:
        logger.error(f"Withings backfill error: {e}")
        return 0


def get_garmin_client():
    """Get authenticated Garmin client."""
    if not GARMIN_EMAIL or not GARMIN_PASSWORD:
        raise ValueError("Garmin credentials not configured")

    # Try to load existing session
    if SESSION_DIR.exists():
        try:
            logger.info("Loading existing Garmin session...")
            garth.resume(str(SESSION_DIR))
            logger.info("Garmin session loaded successfully")
            return garth.client
        except Exception as e:
            logger.warning(f"Failed to load Garmin session: {e}")

    # Fresh login required (will prompt for MFA)
    logger.info("Authenticating with Garmin Connect (may require MFA)...")
    garth.login(GARMIN_EMAIL, GARMIN_PASSWORD)

    # Save session for future use
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        garth.save(str(SESSION_DIR))
        logger.info(f"Garmin session saved to {SESSION_DIR}")
    except Exception as e:
        logger.warning(f"Failed to save Garmin session: {e}")

    logger.info("Garmin authentication successful")
    return garth.client


async def backfill_garmin_data(days: int = 10) -> dict:
    """Fetch historical Garmin data for the past N days."""
    logger.info(f"Backfilling {days} days of Garmin data...")

    try:
        get_garmin_client()  # Ensure authenticated
    except ValueError as e:
        logger.error(str(e))
        return {"steps": 0, "sleep": 0, "hr": 0}

    results = {"steps": 0, "sleep": 0}

    async with httpx.AsyncClient() as http_client:
        # Fetch steps data using garth's stats API
        logger.info("Fetching steps data...")
        try:
            steps_data = garth.DailySteps.list(end=date.today(), period=days)
            for step in steps_data:
                daily_data = {
                    "user_id": "chris",
                    "date": step.calendar_date.isoformat(),
                    "steps": step.total_steps,
                    "steps_goal": step.step_goal,
                    "source": "garmin"
                }

                # Use upsert to allow updating today's steps as they increment
                success = await _upsert_record(
                    http_client,
                    "garmin_daily_summary",
                    daily_data,
                    ["user_id", "date"]
                )

                if success:
                    results["steps"] += 1
                    logger.info(f"  {step.calendar_date}: {step.total_steps} steps")
        except Exception as e:
            logger.error(f"Steps backfill error: {e}")

        # Fetch sleep data
        logger.info("Fetching sleep data...")
        try:
            for day_offset in range(days):
                target_date = (date.today() - timedelta(days=day_offset)).isoformat()
                try:
                    sleep = garth.DailySleepData.get(target_date)
                    if sleep and sleep.daily_sleep_dto:
                        dto = sleep.daily_sleep_dto
                        sleep_seconds = dto.sleep_time_seconds or 0
                        sleep_hours = round(sleep_seconds / 3600, 1)

                        # Get sleep score
                        quality_score = None
                        if dto.sleep_scores and dto.sleep_scores.overall:
                            quality_score = dto.sleep_scores.overall.value

                        sleep_record = {
                            "user_id": "chris",
                            "date": target_date,
                            "total_hours": sleep_hours,
                            "quality_score": quality_score,
                            "deep_hours": round((dto.deep_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'deep_sleep_seconds') and dto.deep_sleep_seconds else None,
                            "light_hours": round((dto.light_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'light_sleep_seconds') and dto.light_sleep_seconds else None,
                            "rem_hours": round((dto.rem_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'rem_sleep_seconds') and dto.rem_sleep_seconds else None,
                            "awake_hours": round((dto.awake_sleep_seconds or 0) / 3600, 1) if hasattr(dto, 'awake_sleep_seconds') and dto.awake_sleep_seconds else None,
                            "source": "garmin"
                        }

                        # Use upsert to allow updating sleep data
                        success = await _upsert_record(
                            http_client,
                            "garmin_sleep",
                            sleep_record,
                            ["user_id", "date"]
                        )

                        if success:
                            results["sleep"] += 1
                            logger.info(f"  {target_date}: {sleep_hours}h sleep, score: {quality_score}")
                except Exception as e:
                    logger.debug(f"  No sleep data for {target_date}: {e}")
        except Exception as e:
            logger.error(f"Sleep backfill error: {e}")

    logger.info(f"Garmin backfill complete: {results}")
    return results


async def main():
    """Run the backfill."""
    print("=" * 60)
    print("Health Data Backfill Script")
    print("=" * 60)
    print()

    # Check configuration
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: Supabase not configured")
        return

    print()

    # Backfill Withings weight
    print("-" * 40)
    print("WITHINGS WEIGHT DATA")
    print("-" * 40)
    weight_count = await backfill_withings_weight(days=10)
    print(f"Result: {weight_count} weight readings stored")
    print()

    # Backfill Garmin data
    print("-" * 40)
    print("GARMIN HEALTH DATA")
    print("-" * 40)
    garmin_results = await backfill_garmin_data(days=10)
    print(f"Result: {garmin_results['steps']} daily summaries, {garmin_results['sleep']} sleep records")
    print()

    print("=" * 60)
    print("Backfill complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
