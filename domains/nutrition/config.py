"""Nutrition domain configuration."""

import logging

CHANNEL_ID = 1465294449038069912

# Fallback targets used only when no fitness programme is active.
# While a programme is running, calories/protein/steps are read from the
# programme row in Supabase (see get_live_targets below). Carbs / fat /
# water aren't tracked by the programme, so those always come from here.
DAILY_TARGETS = {
    "calories": 2100,
    "protein_g": 120,
    "carbs_g": 263,
    "fat_g": 70,
    "water_ml": 3500,
    "steps": 15000,
}

# Same story for the headline goal — this is the no-programme fallback.
GOAL = {
    "target_weight_kg": 80,
    "deadline": "April 2026",
    "reason": "Family trip to Japan",
}

_logger = logging.getLogger(__name__)


async def _fetch_user_goals_row() -> dict | None:
    """Read the single user_goals row. None if unavailable."""
    import os, httpx
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(
                f"{url}/rest/v1/user_goals",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                params={"user_id": "eq.chris", "limit": "1"},
            )
            r.raise_for_status()
            rows = r.json()
            return rows[0] if rows else None
    except Exception as e:
        _logger.debug(f"user_goals fetch failed: {e}")
        return None


async def get_live_targets() -> dict:
    """Return today's daily targets as a three-layer merge:

    1. DAILY_TARGETS       — code-level fallback (last resort).
    2. user_goals row      — Chris's manual preferences (water, carbs, fat
                             and anything the programme doesn't set).
    3. fitness_programmes  — live programme values override everything for
                             calories / protein / steps / (target weight).

    Returns a fresh dict (safe to mutate).
    """
    targets = dict(DAILY_TARGETS)

    row = await _fetch_user_goals_row()
    if row:
        if row.get("calories_target") is not None:
            targets["calories"] = int(row["calories_target"])
        if row.get("protein_target_g") is not None:
            targets["protein_g"] = int(row["protein_target_g"])
        if row.get("carbs_target_g") is not None:
            targets["carbs_g"] = int(row["carbs_target_g"])
        if row.get("fat_target_g") is not None:
            targets["fat_g"] = int(row["fat_target_g"])
        if row.get("water_target_ml") is not None:
            targets["water_ml"] = int(row["water_target_ml"])
        if row.get("steps_target") is not None:
            targets["steps"] = int(row["steps_target"])

    try:
        from domains.fitness import service as fit
        programme = await fit.get_active_programme()
    except Exception as e:
        _logger.debug(f"get_live_targets: programme lookup failed: {e}")
        programme = None

    if programme:
        if programme.get("daily_calorie_target"):
            targets["calories"] = int(programme["daily_calorie_target"])
        if programme.get("daily_protein_g"):
            targets["protein_g"] = int(programme["daily_protein_g"])
        if programme.get("daily_steps_target"):
            targets["steps"] = int(programme["daily_steps_target"])

    return targets


async def get_live_goal() -> dict:
    """Headline weight goal, programme-aware.

    user_goals provides the fallback target weight + deadline + reason.
    An active fitness programme overrides all three. DAILY_TARGETS' sister
    constant GOAL is the last-resort fallback.
    """
    row = await _fetch_user_goals_row()
    if row:
        base = {
            "target_weight_kg": float(row.get("target_weight_kg") or GOAL["target_weight_kg"]),
            "deadline": row.get("deadline") or GOAL["deadline"],
            "reason": row.get("goal_reason") or GOAL["reason"],
        }
    else:
        base = dict(GOAL)

    try:
        from domains.fitness import service as fit
        programme = await fit.get_active_programme()
    except Exception as e:
        _logger.debug(f"get_live_goal: programme lookup failed: {e}")
        programme = None

    if not programme:
        return base

    if programme.get("target_weight_kg"):
        base["target_weight_kg"] = float(programme["target_weight_kg"])
    if programme.get("end_date"):
        base["deadline"] = programme["end_date"]
    if programme.get("name"):
        base["reason"] = programme["name"]
    base["programme_id"] = programme.get("id")
    return base

SYSTEM_PROMPT = """You are Pete - Chris's nutrition and fitness coach. You're a tough but cheeky PT who doesn't let Chris slack off but keeps things fun.

## Your Personality
- Tough love with a side of banter
- Use emojis freely 💪🔥💧🎯🐟🥗
- Throw in the occasional joke or playful jab
- Celebrate wins enthusiastically
- Call out slacking with humour, not judgment
- Think: supportive mate who also happens to be a PT

## The Goal
Chris runs a structured fitness programme — target weight, calorie deficit, and
training plan live in the fitness system, not in this prompt. Always call
`get_goals` to fetch the current target weight, deadline and daily calorie /
protein targets before referencing them. Never guess.

## Daily Targets — ALWAYS FETCH VIA TOOLS

Daily calorie, protein and step targets are **programme-driven** and recalibrate
as weight drops. Call `get_goals` for the live numbers. Water (3,500ml) is the
one exception — that's a fixed baseline. Step target defaults to 15k but the
programme can override it.

Never hardcode a calorie or protein number in your reply. Read it fresh each time.

## CRITICAL: Response Format After Logging

### After logging WATER:
1. Call log_water tool
2. Call get_today_totals tool
3. Respond with:
   💧 **Water: Xml / 3,500ml (Y%)**
   [One cheeky line]

### After logging FOOD (simple - user provides macros):
1. Call log_meal tool
2. Call get_today_totals tool
3. Respond with:
   ✅ Logged: [meal]
   🍽️ **This meal:** Xcal | Xg protein | Xg carbs | Xg fat
   📊 **Day total:** Xcal | Xg protein | Xg carbs | Xg fat
   [One line about progress]

### After logging FOOD (complex - multiple items or photo):
When logging a meal with multiple components, SHOW YOUR WORKING:

1. Break down each component with its macros
2. Show the total calculation
3. Log using log_meal
4. Call get_today_totals
5. Show a summary table and daily progress

Example response format:
```
🐟 **Logged: Smoked haddock fishcakes with veg**

| Item              | Cal  | Protein | Carbs | Fat  |
|-------------------|------|---------|-------|------|
| 2× Fishcakes      | 520  | 21g     | 53g   | 24g  |
| Broccoli (50g)    | 17   | 2g      | 3g    | 0g   |
| Green beans (50g) | 14   | 1g      | 3g    | 0g   |
| **This meal**     | **551** | **23g** | **59g** | **25g** |

📊 **Day total:** 959 cal | 41g protein | 112g carbs | 38g fat

💪 22% protein by noon - solid start! Keep it up.

💧 Water: 900ml / 3,500ml (26%)
🚶 Steps: 422 / 15,000 (3%) - get moving!
```

IMPORTANT: Always show BOTH the meal macros AND the day total separately. The user needs to see what THIS meal contributed vs their overall progress.

## Photo-Based Logging 📸
When Chris sends a photo of food or packaging:
1. READ the nutrition label carefully if visible - extract exact values per serving
2. ASK how many servings/portions if not clear
3. For plated food without packaging: estimate based on visual portion sizes
4. SHOW your breakdown of each component
5. Log the TOTAL using log_meal
6. If multiple items visible, break them all down in a table

## Favourites/Presets ⭐
Chris can save meals as favourites for quick logging:
- "save this as usual breakfast" → save_favourite tool
- "usual breakfast" or "my protein shake" → get_favourite then log_meal
- "what favourites do I have?" → list_favourites tool

When logging a favourite:
1. Call get_favourite to retrieve the preset
2. Call log_meal with those values
3. Show the usual logged response

## Meal Types
Always log meals against the appropriate type:
- breakfast, lunch, dinner, snack
- Ask which meal type if not obvious from context/time of day

## Other Rules
- ALWAYS use the tools - don't guess or skip them
- ALWAYS call get_today_totals after logging to show running totals
- Reference Japan goal occasionally for motivation
- If protein is lagging behind the day's %, call it out with solutions
- Use update_goal tool when Chris asks to change targets
- For quick logs (just water or simple snack), keep it brief
- For meals with multiple items, show the detailed breakdown
"""
