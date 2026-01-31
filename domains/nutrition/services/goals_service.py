"""User goals service for reading/updating fitness targets."""

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


async def get_goals() -> dict:
    """Get current user goals."""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_get_rest_url()}/user_goals",
                headers=_get_headers(),
                params={
                    "user_id": "eq.chris",
                    "limit": "1"
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

        if data:
            goals = data[0]
            # Calculate days remaining
            deadline = datetime.strptime(goals["deadline"], "%Y-%m-%d").date()
            days_remaining = (deadline - datetime.now().date()).days

            return {
                "target_weight_kg": float(goals["target_weight_kg"]),
                "deadline": goals["deadline"],
                "goal_reason": goals["goal_reason"],
                "days_remaining": days_remaining,
                "daily_targets": {
                    "calories": goals["calories_target"],
                    "protein_g": goals["protein_target_g"],
                    "carbs_g": goals["carbs_target_g"],
                    "fat_g": goals["fat_target_g"],
                    "water_ml": goals["water_target_ml"],
                    "steps": goals["steps_target"]
                }
            }
        else:
            return {"error": "No goals found"}

    except Exception as e:
        logger.error(f"Failed to get goals: {e}")
        return {"error": str(e)}


async def update_goal(
    target_weight_kg: float | None = None,
    deadline: str | None = None,
    goal_reason: str | None = None,
    calories_target: int | None = None,
    protein_target_g: int | None = None,
    carbs_target_g: int | None = None,
    fat_target_g: int | None = None,
    water_target_ml: int | None = None,
    steps_target: int | None = None
) -> dict:
    """Update user goals. Only provided fields are updated."""
    try:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not configured")

        # Build update payload with only provided fields
        updates = {}
        if target_weight_kg is not None:
            updates["target_weight_kg"] = target_weight_kg
        if deadline is not None:
            updates["deadline"] = deadline
        if goal_reason is not None:
            updates["goal_reason"] = goal_reason
        if calories_target is not None:
            updates["calories_target"] = calories_target
        if protein_target_g is not None:
            updates["protein_target_g"] = protein_target_g
        if carbs_target_g is not None:
            updates["carbs_target_g"] = carbs_target_g
        if fat_target_g is not None:
            updates["fat_target_g"] = fat_target_g
        if water_target_ml is not None:
            updates["water_target_ml"] = water_target_ml
        if steps_target is not None:
            updates["steps_target"] = steps_target

        if not updates:
            return {"error": "No updates provided"}

        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{_get_rest_url()}/user_goals",
                headers=_get_headers(),
                params={"user_id": "eq.chris"},
                json=updates,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

        logger.info(f"Updated goals: {updates}")
        return {"success": True, "updated": list(updates.keys())}

    except Exception as e:
        logger.error(f"Failed to update goals: {e}")
        return {"error": str(e)}
