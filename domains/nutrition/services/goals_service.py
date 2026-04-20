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
    """Get current user goals.

    Programme-aware: when an active fitness_programmes row exists, its
    target weight, deadline, calorie target, protein target and step target
    override the static user_goals row. Carbs / fat / water always come
    from user_goals (the programme doesn't track them).
    """
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

        if not data:
            return {"error": "No goals found"}

        goals = data[0]

        # Overlay the active fitness programme if there is one — that's
        # the live source of truth for calories / protein / steps / weight target.
        programme = None
        try:
            from domains.fitness import service as fit
            programme = await fit.get_active_programme()
        except Exception as e:
            logger.debug(f"programme lookup in get_goals failed: {e}")

        target_weight = float(goals["target_weight_kg"])
        deadline = goals["deadline"]
        goal_reason = goals["goal_reason"]
        calories = goals["calories_target"]
        protein = goals["protein_target_g"]
        steps = goals["steps_target"]

        if programme:
            if programme.get("target_weight_kg"):
                target_weight = float(programme["target_weight_kg"])
            if programme.get("end_date"):
                deadline = programme["end_date"]
            if programme.get("name"):
                goal_reason = programme["name"]
            if programme.get("daily_calorie_target"):
                calories = int(programme["daily_calorie_target"])
            if programme.get("daily_protein_g"):
                protein = int(programme["daily_protein_g"])
            if programme.get("daily_steps_target"):
                steps = int(programme["daily_steps_target"])

        deadline_date = datetime.strptime(deadline, "%Y-%m-%d").date()
        days_remaining = (deadline_date - datetime.now().date()).days

        result = {
            "target_weight_kg": target_weight,
            "deadline": deadline,
            "goal_reason": goal_reason,
            "days_remaining": days_remaining,
            "daily_targets": {
                "calories": calories,
                "protein_g": protein,
                "carbs_g": goals["carbs_target_g"],
                "fat_g": goals["fat_target_g"],
                "water_ml": goals["water_target_ml"],
                "steps": steps,
            },
        }
        if programme:
            result["source"] = "fitness_programme"
            result["programme_id"] = programme.get("id")
        else:
            result["source"] = "user_goals"
        return result

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
