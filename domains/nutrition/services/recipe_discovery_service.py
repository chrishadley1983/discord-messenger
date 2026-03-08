"""Recipe discovery service.

Analyses Chris's top-rated recipes to find patterns, then searches
for new recipes that match those patterns but haven't been tried yet.
"""

import asyncio
from datetime import datetime, timedelta

from logger import logger


async def get_discovery_context() -> dict:
    """Build context for recipe discovery by analysing existing recipes and preferences.

    Returns dict with:
    - top_recipes: List of highest-rated recipes with key attributes
    - preferred_cuisines: Most common cuisines in top-rated recipes
    - preferred_proteins: Most common protein types
    - avg_prep_time: Average prep time of liked recipes
    - recent_recipes: Names of recipes made in last 30 days (to exclude)
    - preferences: Dietary preferences
    """
    import httpx

    HADLEY_API = "http://localhost:8100"

    async with httpx.AsyncClient(timeout=15) as client:
        # Fetch in parallel
        results = await asyncio.gather(
            client.get(f"{HADLEY_API}/recipes/search", params={"limit": "50"}),
            client.get(f"{HADLEY_API}/meal-plan/history", params={"days": "30"}),
            client.get(f"{HADLEY_API}/meal-plan/preferences"),
            return_exceptions=True,
        )

    # Parse recipes
    all_recipes = []
    if not isinstance(results[0], Exception):
        all_recipes = results[0].json().get("recipes", [])

    # Top rated (rating >= 4 on 1-10 scale, i.e. >= 7)
    top_recipes = [r for r in all_recipes if (r.get("familyRating") or 0) >= 7]
    top_recipes.sort(key=lambda r: r.get("familyRating", 0), reverse=True)

    # Analyse patterns from top recipes
    cuisine_counts = {}
    for r in top_recipes:
        cuisine = r.get("cuisineType", "Other")
        if cuisine:
            cuisine_counts[cuisine] = cuisine_counts.get(cuisine, 0) + 1
    preferred_cuisines = sorted(cuisine_counts, key=cuisine_counts.get, reverse=True)[:5]

    # Average prep time
    prep_times = [r.get("prepTimeMinutes", 0) for r in top_recipes if r.get("prepTimeMinutes")]
    avg_prep = sum(prep_times) / len(prep_times) if prep_times else 30

    # Recent recipes (to exclude)
    recent_names = set()
    if not isinstance(results[1], Exception):
        history = results[1].json().get("history", [])
        recent_names = {h.get("meal_name", "").lower() for h in history}

    # All existing recipe names (to avoid suggesting what's already saved)
    existing_names = {r.get("recipeName", "").lower() for r in all_recipes}

    # Preferences
    preferences = {}
    if not isinstance(results[2], Exception):
        preferences = results[2].json().get("preferences", {})

    return {
        "top_recipes": top_recipes[:10],
        "preferred_cuisines": preferred_cuisines,
        "avg_prep_time": round(avg_prep),
        "recent_recipes": list(recent_names),
        "existing_recipes": list(existing_names),
        "preferences": preferences,
        "total_recipes": len(all_recipes),
        "top_rated_count": len(top_recipes),
    }
