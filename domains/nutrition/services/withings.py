"""Withings service for weight tracking."""

import os
from datetime import datetime, timedelta

import httpx

from config import (
    WITHINGS_CLIENT_ID,
    WITHINGS_CLIENT_SECRET,
    WITHINGS_ACCESS_TOKEN,
    WITHINGS_REFRESH_TOKEN,
    SUPABASE_URL,
    SUPABASE_KEY
)
from logger import logger

# Token storage (in-memory, refreshed as needed)
_tokens = {
    "access": WITHINGS_ACCESS_TOKEN,
    "refresh": WITHINGS_REFRESH_TOKEN
}


async def _refresh_token() -> bool:
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
                    "refresh_token": _tokens["refresh"]
                }
            )

            data = response.json()
            if data["status"] == 0:
                _tokens["access"] = data["body"]["access_token"]
                _tokens["refresh"] = data["body"]["refresh_token"]

                # Update environment variables for persistence
                os.environ["WITHINGS_ACCESS_TOKEN"] = _tokens["access"]
                os.environ["WITHINGS_REFRESH_TOKEN"] = _tokens["refresh"]

                logger.info("Withings token refreshed successfully")
                return True
            else:
                logger.error(f"Withings token refresh failed: {data}")
                return False
    except Exception as e:
        logger.error(f"Withings token refresh error: {e}")
        return False


async def get_weight(retry: bool = True) -> dict:
    """Get latest weight from Withings."""
    try:
        if not _tokens["access"]:
            return {"error": "Withings not configured", "weight_kg": None, "date": None}

        # Get measurements from last 30 days
        start_date = int((datetime.now() - timedelta(days=30)).timestamp())
        end_date = int(datetime.now().timestamp())

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
                headers={"Authorization": f"Bearer {_tokens['access']}"}
            )

            data = response.json()

            if data["status"] != 0:
                # Token may need refresh
                if retry:
                    logger.warning("Withings token expired, refreshing...")
                    if await _refresh_token():
                        return await get_weight(retry=False)
                return {"error": f"Withings API error: status {data['status']}", "weight_kg": None, "date": None}

            # Get most recent measurement (sort by date descending)
            measures = data["body"]["measuregrps"]
            if not measures:
                return {"weight_kg": None, "date": None}

            # Sort by date to ensure we get the latest
            measures.sort(key=lambda x: x["date"], reverse=True)
            latest = measures[0]
            weight_raw = latest["measures"][0]["value"]
            unit = latest["measures"][0]["unit"]
            weight_kg = weight_raw * (10 ** unit)

            result = {
                "weight_kg": round(weight_kg, 1),
                "date": datetime.fromtimestamp(latest["date"]).isoformat()
            }

            logger.info(f"Retrieved Withings weight: {result['weight_kg']}kg")

            # Store reading in database
            await _store_weight_reading(result["weight_kg"], latest["date"])

            return result
    except Exception as e:
        logger.error(f"Withings API error: {e}")
        return {"error": str(e), "weight_kg": None, "date": None}


async def _store_weight_reading(weight_kg: float, timestamp: int):
    """Store weight reading in database for historical tracking."""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            return

        measured_at = datetime.fromtimestamp(timestamp).isoformat()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SUPABASE_URL}/rest/v1/weight_readings",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=ignore-duplicates"
                },
                json={
                    "user_id": "chris",
                    "weight_kg": weight_kg,
                    "measured_at": measured_at,
                    "source": "withings"
                },
                timeout=10
            )
            if response.status_code in (200, 201):
                logger.info(f"Stored weight reading: {weight_kg}kg")
    except Exception as e:
        logger.warning(f"Failed to store weight reading: {e}")


async def get_weight_history(days: int = 30) -> list:
    """Get weight history for trend analysis."""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            return []

        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/weight_readings",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}"
                },
                params={
                    "user_id": "eq.chris",
                    "measured_at": f"gte.{start_date}",
                    "order": "measured_at.desc",
                    "limit": "100"
                },
                timeout=10
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Failed to get weight history: {e}")
        return []
