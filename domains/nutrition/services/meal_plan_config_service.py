"""Meal plan templates, preferences, history, and shopping staples via PostgREST."""

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


# ============================================================
# Templates
# ============================================================

async def list_templates() -> list[dict]:
    """List all meal plan templates."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{_get_rest_url()}/meal_plan_templates",
            headers=_get_headers(),
            params={"select": "id,name,is_default,days,updated_at", "order": "name"},
            timeout=30
        )
        response.raise_for_status()
        return response.json()


async def get_template(name: str) -> dict | None:
    """Get a template by name."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{_get_rest_url()}/meal_plan_templates",
            headers=_get_headers(),
            params={"name": f"eq.{name}", "select": "*"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
    return data[0] if data else None


async def get_default_template() -> dict | None:
    """Get the default template."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{_get_rest_url()}/meal_plan_templates",
            headers=_get_headers(),
            params={"is_default": "eq.true", "select": "*"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
    return data[0] if data else None


async def upsert_template(name: str, days: dict, is_default: bool = False) -> dict:
    """Create or update a template.

    If setting as default, clears default from other templates first.
    """
    if is_default:
        await _clear_default_template()

    payload = {
        "name": name,
        "days": days,
        "is_default": is_default,
        "updated_at": datetime.now().isoformat()
    }

    headers = _get_headers()
    headers["Prefer"] = "return=representation,resolution=merge-duplicates"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_get_rest_url()}/meal_plan_templates",
            headers=headers,
            json=payload,
            params={"on_conflict": "name"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

    template = data[0] if data else None
    logger.info(f"Upserted template '{name}' (default={is_default})")
    return template


async def delete_template(name: str) -> dict:
    """Delete a template by name."""
    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{_get_rest_url()}/meal_plan_templates",
            headers=_get_headers(),
            params={"name": f"eq.{name}"},
            timeout=30
        )
        response.raise_for_status()

    logger.info(f"Deleted template '{name}'")
    return {"success": True, "deleted": name}


async def _clear_default_template():
    """Clear the is_default flag on all templates."""
    async with httpx.AsyncClient() as client:
        await client.patch(
            f"{_get_rest_url()}/meal_plan_templates",
            headers=_get_headers(),
            params={"is_default": "eq.true"},
            json={"is_default": False, "updated_at": datetime.now().isoformat()},
            timeout=30
        )


# ============================================================
# Preferences
# ============================================================

async def get_preferences(profile_name: str = "default") -> dict | None:
    """Get preferences by profile name."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{_get_rest_url()}/meal_plan_preferences",
            headers=_get_headers(),
            params={"profile_name": f"eq.{profile_name}", "select": "*"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
    return data[0] if data else None


async def upsert_preferences(
    profile_name: str = "default",
    dietary: dict = None,
    variety_rules: dict = None,
    cuisine_preferences: list[str] = None,
    disliked_ingredients: list[str] = None,
    gousto_nights_per_week: int = None,
    batch_cook_per_week: int = None,
    budget_per_week_pence: int = None
) -> dict:
    """Create or update preferences. Only provided fields are updated."""
    payload = {
        "profile_name": profile_name,
        "updated_at": datetime.now().isoformat()
    }

    if dietary is not None:
        payload["dietary"] = dietary
    if variety_rules is not None:
        payload["variety_rules"] = variety_rules
    if cuisine_preferences is not None:
        payload["cuisine_preferences"] = cuisine_preferences
    if disliked_ingredients is not None:
        payload["disliked_ingredients"] = disliked_ingredients
    if gousto_nights_per_week is not None:
        payload["gousto_nights_per_week"] = gousto_nights_per_week
    if batch_cook_per_week is not None:
        payload["batch_cook_per_week"] = batch_cook_per_week
    if budget_per_week_pence is not None:
        payload["budget_per_week_pence"] = budget_per_week_pence

    headers = _get_headers()
    headers["Prefer"] = "return=representation,resolution=merge-duplicates"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_get_rest_url()}/meal_plan_preferences",
            headers=headers,
            json=payload,
            params={"on_conflict": "profile_name"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

    prefs = data[0] if data else None
    logger.info(f"Upserted preferences '{profile_name}'")
    return prefs


# ============================================================
# Meal History
# ============================================================

async def log_meal_history(
    date: str,
    meal_name: str,
    recipe_source: str = None,
    recipe_id: str = None,
    protein_type: str = None,
    rating: int = None,
    would_make_again: bool = None,
    notes: str = None
) -> dict:
    """Log a meal to history."""
    payload = {
        "date": date,
        "meal_name": meal_name,
        "recipe_source": recipe_source,
        "recipe_id": recipe_id,
        "protein_type": protein_type,
        "rating": rating,
        "would_make_again": would_make_again,
        "notes": notes
    }
    # Remove None values
    payload = {k: v for k, v in payload.items() if v is not None}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_get_rest_url()}/meal_history",
            headers=_get_headers(),
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

    logger.info(f"Logged meal history: {meal_name} on {date}")
    return data[0] if data else payload


async def get_recent_meal_history(days: int = 14) -> list[dict]:
    """Get meal history for the last N days."""
    from datetime import timedelta
    cutoff = (datetime.now().date() - timedelta(days=days)).isoformat()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{_get_rest_url()}/meal_history",
            headers=_get_headers(),
            params={
                "date": f"gte.{cutoff}",
                "select": "*",
                "order": "date.desc"
            },
            timeout=30
        )
        response.raise_for_status()
        return response.json()


async def update_meal_rating(meal_id: str, rating: int, would_make_again: bool = None, notes: str = None) -> dict:
    """Update rating/feedback for a meal history entry."""
    payload = {"rating": rating}
    if would_make_again is not None:
        payload["would_make_again"] = would_make_again
    if notes is not None:
        payload["notes"] = notes

    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{_get_rest_url()}/meal_history",
            headers=_get_headers(),
            params={"id": f"eq.{meal_id}"},
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

    logger.info(f"Updated meal rating for {meal_id}: {rating}/5")
    return data[0] if data else {"success": True}


# ============================================================
# Shopping Staples
# ============================================================

FREQUENCY_DAYS = {
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
}


async def list_staples(active_only: bool = True) -> list[dict]:
    """List all shopping staples."""
    params = {
        "select": "*",
        "order": "category,name"
    }
    if active_only:
        params["is_active"] = "eq.true"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{_get_rest_url()}/shopping_staples",
            headers=_get_headers(),
            params=params,
            timeout=30
        )
        response.raise_for_status()
        return response.json()


async def get_due_staples() -> list[dict]:
    """Get staples that are due to be added to the shopping list.

    A staple is due if:
    - It has never been added (last_added_date is null), OR
    - Enough time has passed since last_added_date based on frequency
    """
    all_staples = await list_staples(active_only=True)
    today = datetime.now().date()
    due = []

    for staple in all_staples:
        last_added = staple.get("last_added_date")
        freq = staple.get("frequency", "weekly")
        interval = FREQUENCY_DAYS.get(freq, 7)

        if last_added is None:
            due.append(staple)
        else:
            last_date = datetime.fromisoformat(last_added).date()
            if (today - last_date).days >= interval:
                due.append(staple)

    return due


async def upsert_staple(
    name: str,
    category: str,
    quantity: str = None,
    frequency: str = "weekly",
    notes: str = None
) -> dict:
    """Create or update a shopping staple."""
    payload = {
        "name": name,
        "category": category,
        "frequency": frequency,
        "updated_at": datetime.now().isoformat()
    }
    if quantity is not None:
        payload["quantity"] = quantity
    if notes is not None:
        payload["notes"] = notes

    headers = _get_headers()
    headers["Prefer"] = "return=representation,resolution=merge-duplicates"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_get_rest_url()}/shopping_staples",
            headers=headers,
            json=payload,
            params={"on_conflict": "name"},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

    logger.info(f"Upserted staple '{name}' ({frequency})")
    return data[0] if data else payload


async def delete_staple(name: str) -> dict:
    """Delete a shopping staple."""
    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{_get_rest_url()}/shopping_staples",
            headers=_get_headers(),
            params={"name": f"eq.{name}"},
            timeout=30
        )
        response.raise_for_status()

    logger.info(f"Deleted staple '{name}'")
    return {"success": True, "deleted": name}


async def mark_staples_added(staple_names: list[str]) -> dict:
    """Mark staples as added to today's shopping list."""
    today = datetime.now().date().isoformat()

    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{_get_rest_url()}/shopping_staples",
            headers=_get_headers(),
            params={"name": f"in.({','.join(staple_names)})"},
            json={"last_added_date": today, "updated_at": datetime.now().isoformat()},
            timeout=30
        )
        response.raise_for_status()

    logger.info(f"Marked {len(staple_names)} staples as added")
    return {"success": True, "count": len(staple_names), "date": today}
