"""Cooking reminder service.

Analyses tomorrow's and today's recipes for prep actions that need
advance notice (marinating, defrosting, soaking, etc.).
"""

import asyncio
import re
from datetime import datetime, timedelta

import httpx

from logger import logger

HADLEY_API = "http://localhost:8100"

# Patterns that indicate advance prep is needed
PREP_PATTERNS = {
    "night_before": [
        (r"marinate\s+(?:overnight|for\s+\d+\s*(?:hours?|hrs?))", "Marinate"),
        (r"(?:soak|soaking)\s+overnight", "Soak"),
        (r"(?:chill|refrigerate)\s+(?:overnight|for\s+\d+\s*(?:hours?|hrs?))", "Chill"),
        (r"(?:rest|resting)\s+(?:overnight|in\s+the\s+fridge)", "Rest in fridge"),
        (r"(?:brine|brining)\s+(?:overnight|for\s+\d+\s*(?:hours?|hrs?))", "Brine"),
        (r"(?:press|pressing)\s+(?:the\s+)?tofu", "Press tofu"),
    ],
    "morning": [
        (r"(?:defrost|thaw|de-frost)", "Take out of freezer to defrost"),
        (r"(?:frozen|from\s+frozen)", "Take out of freezer"),
        (r"(?:room\s+temperature|bring\s+to\s+room\s+temp)", "Take out of fridge to reach room temperature"),
        (r"(?:slow\s+cook|slow-cook|crockpot|crock\s+pot)", "Start the slow cooker"),
    ],
}


def extract_prep_notes(instructions: list[dict], recipe_name: str) -> list[dict]:
    """Extract prep reminders from recipe instructions.

    Args:
        instructions: List of {stepNumber, instruction, timerMinutes?}
        recipe_name: Name of the recipe for the reminder message

    Returns:
        List of {timing: "night_before"|"morning", action: str, recipe: str, step: int}
    """
    reminders = []

    for step in instructions:
        text = step.get("instruction", "").lower()
        step_num = step.get("stepNumber", 0)

        for timing, patterns in PREP_PATTERNS.items():
            for pattern, action_prefix in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    # Build a human-readable action
                    action = f"{action_prefix} for the {recipe_name}"
                    reminders.append({
                        "timing": timing,
                        "action": action,
                        "recipe": recipe_name,
                        "step": step_num,
                        "matched_text": text[:100],
                    })

    return reminders


async def get_reminders_for_date(target_date: str) -> list[dict]:
    """Get cooking reminders for a specific date.

    Checks the meal plan for the target date and analyses recipes
    for prep actions needed.

    Args:
        target_date: ISO date string (YYYY-MM-DD)

    Returns:
        List of reminders with timing, action, and recipe info
    """
    async with httpx.AsyncClient(timeout=15) as client:
        # Get current meal plan
        resp = await client.get(f"{HADLEY_API}/meal-plan/current")
        if resp.status_code != 200:
            return []

        plan = resp.json().get("plan")
        if not plan:
            return []

        # Find meals for the target date (skip leftovers but keep everything else)
        target_meals = [
            item for item in plan.get("items", [])
            if item.get("date") == target_date
            and item.get("source_tag") != "leftovers"  # Leftovers don't need prep
        ]

        if not target_meals:
            return []

        reminders = []

        for meal in target_meals:
            meal_name = meal.get("adults_meal", "")
            if not meal_name:
                continue

            is_gousto = meal.get("source_tag") == "gousto"

            # Check meal plan item notes for explicit prep instructions
            item_notes = meal.get("notes", "") or ""
            if item_notes:
                # Item notes are explicit prep instructions from plan generation
                for timing, patterns in PREP_PATTERNS.items():
                    for pattern, action_prefix in patterns:
                        if re.search(pattern, item_notes, re.IGNORECASE):
                            reminders.append({
                                "timing": timing,
                                "action": item_notes,
                                "recipe": meal_name,
                                "step": 0,
                                "matched_text": item_notes[:100],
                            })
                            break
                    else:
                        continue
                    break
                else:
                    # Notes exist but don't match patterns — still include
                    # as a morning reminder (e.g. "Put pork in slow cooker before 8am")
                    reminders.append({
                        "timing": "morning",
                        "action": item_notes,
                        "recipe": meal_name,
                        "step": 0,
                        "matched_text": item_notes[:100],
                    })

            # Skip recipe instruction analysis for Gousto (ingredients come prepped)
            if is_gousto:
                continue

            # Try to find the recipe in Family Fuel
            try:
                search_resp = await client.get(
                    f"{HADLEY_API}/recipes/search",
                    params={"q": meal_name, "limit": "1"}
                )
                recipes = search_resp.json().get("recipes", [])

                if recipes:
                    recipe_id = recipes[0].get("id")
                    # Get full recipe with instructions
                    recipe_resp = await client.get(f"{HADLEY_API}/recipes/{recipe_id}")
                    recipe_data = recipe_resp.json()

                    instructions = recipe_data.get("instructions", [])
                    if instructions:
                        meal_reminders = extract_prep_notes(instructions, meal_name)
                        reminders.extend(meal_reminders)

            except Exception as e:
                logger.warning(f"Failed to check recipe '{meal_name}' for prep notes: {e}")

        logger.info(f"Found {len(reminders)} cooking reminders for {target_date}")
        return reminders


async def get_evening_reminders() -> list[dict]:
    """Get reminders for tomorrow's meal (things to prep tonight)."""
    tomorrow = (datetime.now() + timedelta(days=1)).date().isoformat()
    all_reminders = await get_reminders_for_date(tomorrow)
    return [r for r in all_reminders if r["timing"] == "night_before"]


async def get_morning_reminders() -> list[dict]:
    """Get reminders for today's meal (things to do this morning)."""
    today = datetime.now().date().isoformat()
    all_reminders = await get_reminders_for_date(today)
    return [r for r in all_reminders if r["timing"] == "morning"]
