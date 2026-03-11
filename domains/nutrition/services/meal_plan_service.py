"""Meal plan service for weekly meal planning via PostgREST."""

from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")

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


def _monday_of(date_str: str) -> str:
    """Get the Monday of the week containing the given date."""
    d = datetime.fromisoformat(date_str).date()
    monday = d - timedelta(days=d.weekday())
    return monday.isoformat()


async def upsert_meal_plan(week_start: str, source: str = None,
                           sheet_id: str = None, notes: str = None) -> dict:
    """Create or update a meal plan for a given week.

    Args:
        week_start: Monday date (YYYY-MM-DD) for the plan week
        source: 'sheets', 'csv', 'manual'
        sheet_id: Google Sheet ID if imported from sheets
        notes: Optional notes

    Returns:
        The upserted meal plan record
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase credentials not configured")

    payload = {
        "week_start": week_start,
        "source": source,
        "sheet_id": sheet_id,
        "notes": notes
    }

    headers = _get_headers()
    headers["Prefer"] = "return=representation,resolution=merge-duplicates"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_get_rest_url()}/meal_plans",
            headers=headers,
            json=payload,
            params={"on_conflict": "week_start"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

    plan = data[0] if data else None
    logger.info(f"Upserted meal plan for week {week_start}")
    return plan


async def get_meal_plan(week_start: str) -> dict | None:
    """Get a meal plan by week_start date.

    Returns:
        Plan dict with items and ingredients, or None if not found
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase credentials not configured")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{_get_rest_url()}/meal_plans",
            headers=_get_headers(),
            params={
                "week_start": f"eq.{week_start}",
                "select": "*"
            },
            timeout=30
        )
        response.raise_for_status()
        plans = response.json()

    if not plans:
        return None

    plan = plans[0]

    # Fetch items and ingredients in parallel
    async with httpx.AsyncClient() as client:
        items_resp, ingredients_resp = await _parallel_get(client, plan["id"])

    plan["items"] = items_resp
    plan["ingredients"] = ingredients_resp
    return plan


async def get_current_meal_plan() -> dict | None:
    """Get the meal plan containing today's date.

    First tries exact week_start match for this Monday.
    Falls back to finding any plan with items for today
    (handles plans that span week boundaries).
    """
    today = datetime.now(UK_TZ).date()
    monday = today - timedelta(days=today.weekday())

    # Try exact week_start match first
    plan = await get_meal_plan(monday.isoformat())
    if plan:
        return plan

    # Fallback: find any plan that has items for today
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_get_rest_url()}/meal_plan_items",
            headers=_get_headers(),
            params={
                "date": f"eq.{today.isoformat()}",
                "select": "plan_id",
                "limit": "1"
            },
            timeout=30
        )
        resp.raise_for_status()
        items = resp.json()

    if not items:
        return None

    return await get_meal_plan_by_id(items[0]["plan_id"])


async def get_meal_plan_by_id(plan_id: str) -> dict | None:
    """Get a meal plan by its UUID."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase credentials not configured")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{_get_rest_url()}/meal_plans",
            headers=_get_headers(),
            params={"id": f"eq.{plan_id}", "select": "*"},
            timeout=30
        )
        response.raise_for_status()
        plans = response.json()

    if not plans:
        return None

    plan = plans[0]
    async with httpx.AsyncClient() as client:
        items_resp, ingredients_resp = await _parallel_get(client, plan["id"])

    plan["items"] = items_resp
    plan["ingredients"] = ingredients_resp
    return plan


async def _parallel_get(client: httpx.AsyncClient, plan_id: str) -> tuple:
    """Fetch items and ingredients for a plan in parallel."""
    import asyncio

    async def get_items():
        resp = await client.get(
            f"{_get_rest_url()}/meal_plan_items",
            headers=_get_headers(),
            params={
                "plan_id": f"eq.{plan_id}",
                "select": "*",
                "order": "date,meal_slot"
            },
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    async def get_ingredients():
        resp = await client.get(
            f"{_get_rest_url()}/meal_plan_ingredients",
            headers=_get_headers(),
            params={
                "plan_id": f"eq.{plan_id}",
                "select": "*",
                "order": "category,item"
            },
            timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    items, ingredients = await asyncio.gather(get_items(), get_ingredients())
    return items, ingredients


async def delete_meal_plan(plan_id: str) -> dict:
    """Delete a meal plan and all its items/ingredients (cascade)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase credentials not configured")

    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{_get_rest_url()}/meal_plans?id=eq.{plan_id}",
            headers=_get_headers(),
            timeout=30
        )
        response.raise_for_status()

    logger.info(f"Deleted meal plan {plan_id}")
    return {"success": True, "deleted_id": plan_id}


async def upsert_meal_plan_items(plan_id: str, items: list[dict]) -> list:
    """Upsert meal plan items for a plan.

    Each item should have: date, meal_slot, adults_meal, kids_meal, source_tag, recipe_url

    Args:
        plan_id: UUID of the meal plan
        items: List of item dicts

    Returns:
        List of upserted items
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase credentials not configured")

    # Add plan_id to each item
    for item in items:
        item["plan_id"] = plan_id

    headers = _get_headers()
    headers["Prefer"] = "return=representation,resolution=merge-duplicates"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_get_rest_url()}/meal_plan_items",
            headers=headers,
            json=items,
            params={"on_conflict": "plan_id,date,meal_slot"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

    logger.info(f"Upserted {len(data)} meal plan items for plan {plan_id}")
    return data


async def set_meal_plan_ingredients(plan_id: str, ingredients: list[dict]) -> list:
    """Replace all ingredients for a plan (delete existing, insert new).

    Each ingredient should have: category, item, quantity, for_recipe

    Args:
        plan_id: UUID of the meal plan
        ingredients: List of ingredient dicts

    Returns:
        List of inserted ingredients
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase credentials not configured")

    async with httpx.AsyncClient() as client:
        # Delete existing ingredients
        await client.delete(
            f"{_get_rest_url()}/meal_plan_ingredients?plan_id=eq.{plan_id}",
            headers=_get_headers(),
            timeout=30
        )

        if not ingredients:
            return []

        # Add plan_id to each ingredient
        for ing in ingredients:
            ing["plan_id"] = plan_id

        # Insert new ingredients
        response = await client.post(
            f"{_get_rest_url()}/meal_plan_ingredients",
            headers=_get_headers(),
            json=ingredients,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

    logger.info(f"Set {len(data)} ingredients for plan {plan_id}")
    return data


async def get_shopping_list_categories(plan_id: str) -> dict[str, list[str]]:
    """Get ingredients grouped by category for shopping list generation.

    Returns:
        Dict of category -> list of item strings (e.g. "Chicken breast (500g)")
        Compatible with POST /shopping-list/generate {categories: {...}}
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase credentials not configured")

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{_get_rest_url()}/meal_plan_ingredients",
            headers=_get_headers(),
            params={
                "plan_id": f"eq.{plan_id}",
                "select": "category,item,quantity",
                "order": "category,item"
            },
            timeout=30
        )
        response.raise_for_status()
        ingredients = response.json()

    categories: dict[str, list[str]] = {}
    for ing in ingredients:
        cat = ing["category"]
        item_str = ing["item"]
        if ing.get("quantity"):
            item_str = f"{item_str} ({ing['quantity']})"
        categories.setdefault(cat, []).append(item_str)

    return categories
