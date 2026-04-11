"""One-shot programme initializer.

Called when Chris says "start the fitness programme" or via
POST /fitness/programme/start. Does:

1. Archive existing active fitness programmes.
2. Archive existing legacy "Hit 80kg" accountability goal.
3. Compute TDEE from current weight, height, age, step average.
4. Create new fitness_programme row.
5. Create 6 accountability_goals (weight, calories, protein, steps, strength, mobility).
6. Return the resulting programme + goals summary.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import httpx

from domains.fitness.service import (
    abandon_active_programmes,
    create_programme,
    fetch_steps_history,
)
from domains.fitness.tdee import compute_tdee

logger = logging.getLogger(__name__)

# Chris's constants (pulled from second brain / profile)
HEIGHT_CM = 183
AGE_YEARS = 42
SEX = "male"


async def _archive_old_weight_goals(api_base: str, api_key: str) -> list[str]:
    """Mark any 'Hit 80kg' or 'Lose weight' accountability goals as abandoned."""
    archived: list[str] = []
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.get(
            f"{api_base}/accountability/goals",
            headers={"x-api-key": api_key},
            params={"status": "active"},
        )
        if resp.status_code != 200:
            return archived
        data = resp.json().get("goals", [])
        for g in data:
            title = (g.get("title") or "").lower()
            if any(k in title for k in ["80kg", "lose weight", "weight loss", "hit weight"]):
                await c.patch(
                    f"{api_base}/accountability/goals/{g['id']}",
                    headers={"x-api-key": api_key, "Content-Type": "application/json"},
                    json={"status": "abandoned"},
                )
                archived.append(g["title"])
    return archived


async def _create_goal(
    api_base: str,
    api_key: str,
    *,
    title: str,
    goal_type: str,
    metric: str,
    target_value: float,
    category: str = "fitness",
    description: str | None = None,
    start_value: float = 0,
    direction: str = "up",
    frequency: str | None = None,
    deadline: str | None = None,
    auto_source: str | None = None,
) -> dict | None:
    body = {
        "title": title,
        "goal_type": goal_type,
        "metric": metric,
        "target_value": target_value,
        "category": category,
        "description": description,
        "start_value": start_value,
        "direction": direction,
        "frequency": frequency,
        "deadline": deadline,
        "auto_source": auto_source,
    }
    async with httpx.AsyncClient(timeout=10) as c:
        resp = await c.post(
            f"{api_base}/accountability/goals",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json=body,
        )
        if resp.status_code in (200, 201):
            return resp.json().get("goal")
        logger.warning(f"Create goal failed: {resp.status_code} {resp.text}")
        return None


async def start_programme(
    *,
    start_date: str,
    current_weight_kg: float,
    target_loss_kg: float = 10.0,
    duration_weeks: int = 13,
    api_base: str,
    api_key: str,
    archive_old_goals: bool = True,
) -> dict:
    """Initialize the full fitness programme.

    Args:
        start_date: ISO date the programme begins.
        current_weight_kg: Chris's weight on the start date.
        target_loss_kg: How much to lose (default 10).
        duration_weeks: Programme length (default 13).
        api_base: Hadley API base URL (for accountability calls).
        api_key: Hadley API key.
        archive_old_goals: If true, abandon old 'Hit 80kg' goals first.

    Returns:
        Dict with programme + list of created goals + archived goals.
    """
    # 1. Archive old programmes
    await abandon_active_programmes()

    # 2. Archive legacy weight goals
    archived = []
    if archive_old_goals:
        archived = await _archive_old_weight_goals(api_base, api_key)

    # 3. TDEE
    steps_history = await fetch_steps_history(days=7)
    avg_steps = (
        sum(p["value"] for p in steps_history) / len(steps_history)
        if steps_history else 8000
    )
    tdee = compute_tdee(
        weight_kg=current_weight_kg,
        height_cm=HEIGHT_CM,
        age_years=AGE_YEARS,
        avg_steps=avg_steps,
        sex=SEX,
        deficit_kcal=550,
    )

    target_weight = round(current_weight_kg - target_loss_kg, 1)

    # 4. Create programme
    programme = await create_programme(
        name=f"Post-Japan 13-week cut",
        start_date=start_date,
        start_weight_kg=current_weight_kg,
        target_weight_kg=target_weight,
        tdee_kcal=tdee.tdee,
        daily_calorie_target=tdee.target_calories,
        daily_protein_g=tdee.target_protein_g,
        duration_weeks=duration_weeks,
        split="5x_short",
        daily_steps_target=12000,
        weekly_strength_sessions=5,
        notes=f"BMR {tdee.bmr} × {tdee.activity_factor} = {tdee.tdee}. "
              f"Deficit {tdee.deficit_kcal}. 5x/week 20-min sessions. "
              f"Archived goals: {', '.join(archived) or 'none'}",
    )

    # 5. Create accountability goals
    deadline = (date.fromisoformat(start_date) + timedelta(weeks=duration_weeks)).isoformat()
    goals_created = []

    # Weight target
    g = await _create_goal(
        api_base, api_key,
        title=f"Lose {target_loss_kg:g}kg (post-Japan cut)",
        goal_type="target",
        metric="kg",
        target_value=target_weight,
        start_value=current_weight_kg,
        direction="down",
        deadline=deadline,
        description="Weighted 7-day trend from Withings",
        auto_source="weight",
    )
    goals_created.append(g)

    # Daily calories
    g = await _create_goal(
        api_base, api_key,
        title=f"Daily calories ≤ {tdee.target_calories}",
        goal_type="habit",
        metric="kcal",
        target_value=tdee.target_calories,
        direction="down",
        frequency="daily",
        description="Stay within daily calorie budget",
        auto_source="nutrition_calories",
    )
    goals_created.append(g)

    # Daily protein
    g = await _create_goal(
        api_base, api_key,
        title=f"Protein ≥ {tdee.target_protein_g}g daily",
        goal_type="habit",
        metric="g",
        target_value=tdee.target_protein_g,
        direction="up",
        frequency="daily",
        description="Preserve muscle in the cut",
        auto_source="nutrition_protein",
    )
    goals_created.append(g)

    # Daily steps
    g = await _create_goal(
        api_base, api_key,
        title="12k steps daily",
        goal_type="habit",
        metric="steps",
        target_value=12000,
        direction="up",
        frequency="daily",
        description="NEAT is the biggest fat-loss lever",
        auto_source="garmin_steps",
    )
    goals_created.append(g)

    # Weekly strength
    g = await _create_goal(
        api_base, api_key,
        title="5 strength sessions per week",
        goal_type="habit",
        metric="sessions",
        target_value=5,
        direction="up",
        frequency="weekly",
        description="Mon-Fri 20-min bodyweight sessions",
        auto_source="fitness_strength_week",
    )
    goals_created.append(g)

    # Daily mobility
    g = await _create_goal(
        api_base, api_key,
        title="Daily mobility routine",
        goal_type="habit",
        metric="boolean",
        target_value=1,
        direction="up",
        frequency="daily",
        description="10-min morning or evening mobility",
        auto_source="fitness_mobility_today",
    )
    goals_created.append(g)

    return {
        "programme": programme,
        "tdee": {
            "bmr": tdee.bmr,
            "activity_factor": tdee.activity_factor,
            "tdee": tdee.tdee,
            "deficit": tdee.deficit_kcal,
            "target_calories": tdee.target_calories,
            "target_protein_g": tdee.target_protein_g,
        },
        "goals_created": [g for g in goals_created if g],
        "archived_goals": archived,
        "start_date": start_date,
        "end_date": (date.fromisoformat(start_date) + timedelta(weeks=duration_weeks)).isoformat(),
    }
