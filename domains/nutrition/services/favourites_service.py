"""Meal favourites/presets service."""

from datetime import datetime

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


async def save_favourite(
    name: str,
    description: str,
    calories: float,
    protein_g: float,
    carbs_g: float,
    fat_g: float,
    meal_type: str | None = None
) -> dict:
    """Save a meal as a favourite/preset."""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")

        # Normalize name for lookup
        name_lower = name.lower().strip()

        async with httpx.AsyncClient() as client:
            # Upsert (insert or update)
            response = await client.post(
                f"{_get_rest_url()}/meal_favourites",
                headers={**_get_headers(), "Prefer": "return=representation,resolution=merge-duplicates"},
                json={
                    "user_id": "chris",
                    "name": name_lower,
                    "description": description,
                    "calories": calories,
                    "protein_g": protein_g,
                    "carbs_g": carbs_g,
                    "fat_g": fat_g,
                    "meal_type": meal_type
                },
                timeout=30
            )
            response.raise_for_status()

        logger.info(f"Saved favourite: {name}")
        return {"success": True, "name": name_lower}

    except Exception as e:
        logger.error(f"Failed to save favourite: {e}")
        return {"error": str(e)}


async def get_favourite(name: str) -> dict | None:
    """Get a favourite by name."""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")

        name_lower = name.lower().strip()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_get_rest_url()}/meal_favourites",
                headers=_get_headers(),
                params={
                    "user_id": "eq.chris",
                    "name": f"eq.{name_lower}",
                    "limit": "1"
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

        if data:
            fav = data[0]
            # Update use count
            await _increment_use_count(fav["id"])
            return {
                "name": fav["name"],
                "description": fav["description"],
                "meal_type": fav["meal_type"],
                "calories": float(fav["calories"]),
                "protein_g": float(fav["protein_g"]),
                "carbs_g": float(fav["carbs_g"]),
                "fat_g": float(fav["fat_g"])
            }
        return None

    except Exception as e:
        logger.error(f"Failed to get favourite: {e}")
        return None


async def _increment_use_count(favourite_id: str):
    """Increment the use count for a favourite."""
    try:
        async with httpx.AsyncClient() as client:
            # Get current count
            response = await client.get(
                f"{_get_rest_url()}/meal_favourites",
                headers=_get_headers(),
                params={"id": f"eq.{favourite_id}", "select": "use_count"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            current_count = data[0]["use_count"] if data else 0

            # Update
            await client.patch(
                f"{_get_rest_url()}/meal_favourites",
                headers=_get_headers(),
                params={"id": f"eq.{favourite_id}"},
                json={
                    "use_count": (current_count or 0) + 1,
                    "last_used_at": datetime.now().isoformat()
                },
                timeout=30
            )
    except Exception as e:
        logger.warning(f"Failed to increment use count: {e}")


async def list_favourites() -> list:
    """List all favourites."""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_get_rest_url()}/meal_favourites",
                headers=_get_headers(),
                params={
                    "user_id": "eq.chris",
                    "order": "use_count.desc",
                    "limit": "20"
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

        return [
            {
                "name": f["name"],
                "description": f["description"],
                "calories": float(f["calories"]),
                "protein_g": float(f["protein_g"]),
                "use_count": f["use_count"] or 0
            }
            for f in data
        ]

    except Exception as e:
        logger.error(f"Failed to list favourites: {e}")
        return []


async def delete_favourite(name: str) -> dict:
    """Delete a favourite."""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")

        name_lower = name.lower().strip()

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{_get_rest_url()}/meal_favourites",
                headers=_get_headers(),
                params={
                    "user_id": "eq.chris",
                    "name": f"eq.{name_lower}"
                },
                timeout=30
            )
            response.raise_for_status()

        logger.info(f"Deleted favourite: {name}")
        return {"success": True}

    except Exception as e:
        logger.error(f"Failed to delete favourite: {e}")
        return {"error": str(e)}
