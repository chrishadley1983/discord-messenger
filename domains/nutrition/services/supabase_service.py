"""Supabase service for nutrition data operations using PostgREST directly."""

from datetime import datetime, timedelta

import httpx

from config import SUPABASE_URL, SUPABASE_KEY
from logger import logger


def _get_headers():
    """Get headers for Supabase API calls."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def _get_rest_url():
    """Get the REST API URL."""
    return f"{SUPABASE_URL}/rest/v1"


async def insert_meal(
    meal_type: str,
    description: str,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float
) -> dict:
    """Insert a meal record."""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_get_rest_url()}/nutrition_logs",
                headers=_get_headers(),
                json={
                    "meal_type": meal_type,
                    "description": description,
                    "calories": calories,
                    "protein_g": protein_g,
                    "carbs_g": carbs_g,
                    "fat_g": fat_g,
                    "water_ml": 0
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

        logger.info(f"Logged meal: {meal_type} - {description}")
        return {"success": True, "id": data[0]["id"] if data else None}
    except Exception as e:
        logger.error(f"Failed to insert meal: {e}")
        raise


async def insert_water(ml: float) -> dict:
    """Insert a water record."""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")

        payload = {
            "meal_type": "water",
            "description": f"{ml}ml water",
            "water_ml": ml,
            "calories": 0,
            "protein_g": 0,
            "carbs_g": 0,
            "fat_g": 0
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_get_rest_url()}/nutrition_logs",
                headers=_get_headers(),
                json=payload,
                timeout=30
            )
            if response.status_code >= 400:
                logger.error(f"Insert water failed - Status: {response.status_code}, Body: {response.text}, Payload: {payload}")
            response.raise_for_status()
            data = response.json()

        logger.info(f"Logged water: {ml}ml")
        return {"success": True, "id": data[0]["id"] if data else None}
    except Exception as e:
        logger.error(f"Failed to insert water: {e}")
        raise


async def get_today_totals() -> dict:
    """Get today's nutrition totals."""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")

        today = datetime.now().date().isoformat()
        tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()

        # PostgREST: use 'and' filter for multiple conditions on same column
        # Format: and=(logged_at.gte.X,logged_at.lt.Y)
        filter_str = f"and=(logged_at.gte.{today}T00:00:00,logged_at.lt.{tomorrow}T00:00:00)"
        url = f"{_get_rest_url()}/nutrition_logs?select=calories,protein_g,carbs_g,fat_g,water_ml,logged_at&{filter_str}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=_get_headers(),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

        logger.info(f"Retrieved {len(data)} nutrition records for today")

        totals = {
            "calories": sum(r["calories"] or 0 for r in data),
            "protein_g": sum(r["protein_g"] or 0 for r in data),
            "carbs_g": sum(r["carbs_g"] or 0 for r in data),
            "fat_g": sum(r["fat_g"] or 0 for r in data),
            "water_ml": sum(r["water_ml"] or 0 for r in data),
        }

        logger.info(f"Retrieved today's totals: {totals['calories']} cal")
        return totals
    except Exception as e:
        logger.error(f"Failed to get today's totals: {e}")
        raise


async def get_today_meals() -> list:
    """Get today's meals (excluding water)."""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")

        today = datetime.now().date().isoformat()
        tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()

        # PostgREST: use 'and' filter for multiple conditions
        filter_str = f"and=(logged_at.gte.{today}T00:00:00,logged_at.lt.{tomorrow}T00:00:00)"
        url = f"{_get_rest_url()}/nutrition_logs?select=*&{filter_str}&meal_type=neq.water&order=logged_at"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=_get_headers(),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

        logger.info(f"Retrieved {len(data)} meals for today")
        return data
    except Exception as e:
        logger.error(f"Failed to get today's meals: {e}")
        raise


async def get_week_summary() -> list:
    """Get last 7 days of totals."""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=7)

        # Call RPC function
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_get_rest_url()}/rpc/get_daily_totals",
                headers=_get_headers(),
                json={
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

        logger.info(f"Retrieved week summary: {len(data)} days")
        return data
    except Exception as e:
        logger.error(f"Failed to get week summary: {e}")
        raise
