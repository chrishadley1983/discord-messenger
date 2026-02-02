"""Data fetchers for scheduled jobs.

Pre-fetches data in parallel for skills that need it.
Skills without a fetcher use web search during execution.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from logger import logger

UK_TZ = ZoneInfo("Europe/London")


async def get_nutrition_data() -> dict[str, Any]:
    """Fetch nutrition data for nutrition-summary skill.

    Returns:
        Dict with today's nutrition totals, targets, and steps
    """
    from domains.nutrition.services import get_today_totals, get_steps
    from domains.nutrition.config import DAILY_TARGETS

    try:
        totals, steps_data = await asyncio.gather(
            get_today_totals(),
            get_steps(),
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(totals, Exception):
            logger.warning(f"Failed to get nutrition totals: {totals}")
            totals = {}
        if isinstance(steps_data, Exception):
            logger.warning(f"Failed to get steps: {steps_data}")
            steps_data = {}

        return {
            "nutrition": totals,
            "steps": steps_data.get("steps", 0) if steps_data else 0,
            "targets": DAILY_TARGETS,
            "date": datetime.now(UK_TZ).strftime("%Y-%m-%d")
        }

    except Exception as e:
        logger.error(f"Nutrition data fetch error: {e}")
        return {"error": str(e)}


async def get_hydration_data() -> dict[str, Any]:
    """Fetch hydration and steps data for hydration skill.

    Returns:
        Dict with water intake, steps, targets, and time info
    """
    from domains.nutrition.services import get_today_totals, get_steps
    from domains.nutrition.config import DAILY_TARGETS

    try:
        totals, steps_data = await asyncio.gather(
            get_today_totals(),
            get_steps(),
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(totals, Exception):
            logger.warning(f"Failed to get totals: {totals}")
            totals = {}
        if isinstance(steps_data, Exception):
            logger.warning(f"Failed to get steps: {steps_data}")
            steps_data = {}

        now = datetime.now(UK_TZ)
        water_ml = totals.get("water_ml", 0)
        water_target = DAILY_TARGETS["water_ml"]
        steps = steps_data.get("steps", 0) if steps_data else 0
        steps_target = DAILY_TARGETS["steps"]

        return {
            "water_ml": water_ml,
            "water_target": water_target,
            "water_pct": (water_ml / water_target * 100) if water_target else 0,
            "steps": steps,
            "steps_target": steps_target,
            "steps_pct": (steps / steps_target * 100) if steps_target else 0,
            "hour": now.hour,
            "time_of_day": "morning" if now.hour < 12 else "afternoon" if now.hour < 17 else "evening",
            "hours_until_9pm": max(0, 21 - now.hour)
        }

    except Exception as e:
        logger.error(f"Hydration data fetch error: {e}")
        return {"error": str(e)}


async def get_health_digest_data() -> dict[str, Any]:
    """Fetch health data for morning health-digest skill.

    Returns:
        Dict with sleep, steps, heart rate, weight, and yesterday's nutrition
    """
    from domains.nutrition.services import (
        get_sleep, get_steps, get_heart_rate, get_weight,
        get_today_totals
    )
    from domains.nutrition.config import DAILY_TARGETS, GOAL

    try:
        # Parallel fetch all health data
        results = await asyncio.gather(
            get_sleep(),
            get_steps(),
            get_heart_rate(),
            get_weight(),
            get_today_totals(),  # This gets yesterday's final totals if called early
            return_exceptions=True
        )

        sleep_data, steps_data, hr_data, weight_data, nutrition_data = results

        # Handle exceptions
        data = {
            "sleep": sleep_data if not isinstance(sleep_data, Exception) else None,
            "steps": steps_data if not isinstance(steps_data, Exception) else None,
            "heart_rate": hr_data if not isinstance(hr_data, Exception) else None,
            "weight": weight_data if not isinstance(weight_data, Exception) else None,
            "nutrition": nutrition_data if not isinstance(nutrition_data, Exception) else None,
            "targets": DAILY_TARGETS,
            "goal": GOAL,
            "date": datetime.now(UK_TZ).strftime("%Y-%m-%d")
        }

        return data

    except Exception as e:
        logger.error(f"Health digest data fetch error: {e}")
        return {"error": str(e)}


async def get_weekly_health_data() -> dict[str, Any]:
    """Fetch weekly health summary data.

    Uses the legacy job's fetch functions for comprehensive data.

    Returns:
        Dict with structured weekly health data
    """
    from jobs.weekly_health import (
        _get_weight_week,
        _get_nutrition_week,
        _get_steps_week,
        _get_sleep_week,
        _get_heart_rate_week,
        _get_goals
    )
    from domains.nutrition.config import DAILY_TARGETS

    try:
        # Parallel fetch all data using legacy functions
        results = await asyncio.gather(
            _get_weight_week(),
            _get_nutrition_week(),
            _get_steps_week(),
            _get_sleep_week(),
            _get_heart_rate_week(),
            _get_goals(),
            return_exceptions=True
        )

        weight, nutrition, steps, sleep, hr, goals = results

        # Handle exceptions
        if isinstance(weight, Exception):
            logger.warning(f"Failed to get weight: {weight}")
            weight = {}
        if isinstance(nutrition, Exception):
            logger.warning(f"Failed to get nutrition: {nutrition}")
            nutrition = {}
        if isinstance(steps, Exception):
            logger.warning(f"Failed to get steps: {steps}")
            steps = {}
        if isinstance(sleep, Exception):
            logger.warning(f"Failed to get sleep: {sleep}")
            sleep = {}
        if isinstance(hr, Exception):
            logger.warning(f"Failed to get HR: {hr}")
            hr = {}
        if isinstance(goals, Exception):
            logger.warning(f"Failed to get goals: {goals}")
            goals = {}

        return {
            "weight": weight,
            "nutrition": nutrition,
            "steps": steps,
            "sleep": sleep,
            "heart_rate": hr,
            "goals": goals,
            "targets": DAILY_TARGETS,
            "week_ending": datetime.now(UK_TZ).strftime("%Y-%m-%d")
        }

    except Exception as e:
        logger.error(f"Weekly health data fetch error: {e}")
        return {"error": str(e)}


async def get_monthly_health_data() -> dict[str, Any]:
    """Fetch monthly health summary data.

    Uses the legacy job's fetch functions for comprehensive data.

    Returns:
        Dict with structured monthly health data
    """
    from jobs.monthly_health import (
        _get_weight_month,
        _get_nutrition_month,
        _get_steps_month,
        _get_sleep_month,
        _get_goals,
        _get_previous_month
    )
    from domains.nutrition.config import DAILY_TARGETS

    try:
        # Parallel fetch all data using legacy functions
        results = await asyncio.gather(
            _get_weight_month(),
            _get_nutrition_month(),
            _get_steps_month(),
            _get_sleep_month(),
            _get_goals(),
            _get_previous_month(),
            return_exceptions=True
        )

        weight, nutrition, steps, sleep, goals, prev_month = results

        # Handle exceptions
        if isinstance(weight, Exception):
            logger.warning(f"Failed to get weight: {weight}")
            weight = {}
        if isinstance(nutrition, Exception):
            logger.warning(f"Failed to get nutrition: {nutrition}")
            nutrition = {}
        if isinstance(steps, Exception):
            logger.warning(f"Failed to get steps: {steps}")
            steps = {}
        if isinstance(sleep, Exception):
            logger.warning(f"Failed to get sleep: {sleep}")
            sleep = {}
        if isinstance(goals, Exception):
            logger.warning(f"Failed to get goals: {goals}")
            goals = {}
        if isinstance(prev_month, Exception):
            logger.warning(f"Failed to get previous month: {prev_month}")
            prev_month = {}

        return {
            "weight": weight,
            "nutrition": nutrition,
            "steps": steps,
            "sleep": sleep,
            "goals": goals,
            "previous_month": prev_month,
            "targets": DAILY_TARGETS,
            "month_ending": datetime.now(UK_TZ).strftime("%Y-%m-%d")
        }

    except Exception as e:
        logger.error(f"Monthly health data fetch error: {e}")
        return {"error": str(e)}


async def get_balance_data() -> dict[str, Any]:
    """Fetch API balance data for balance-monitor skill.

    Returns:
        Dict with Claude, Moonshot, and Grok balances
    """
    from jobs.balance_monitor import _get_claude_balance, _get_moonshot_balance, _get_grok_balance

    try:
        claude_data, moonshot_data, grok_data = await asyncio.gather(
            _get_claude_balance(),
            _get_moonshot_balance(),
            _get_grok_balance(),
            return_exceptions=True
        )

        return {
            "claude": claude_data if not isinstance(claude_data, Exception) else {"error": str(claude_data)},
            "moonshot": moonshot_data if not isinstance(moonshot_data, Exception) else {"error": str(moonshot_data)},
            "grok": grok_data if not isinstance(grok_data, Exception) else {"error": str(grok_data)},
            "threshold": 5.00,
            "timestamp": datetime.now(UK_TZ).strftime("%Y-%m-%d %H:%M")
        }

    except Exception as e:
        logger.error(f"Balance data fetch error: {e}")
        return {"error": str(e)}


async def get_youtube_data() -> dict[str, Any]:
    """Fetch YouTube feed data for youtube-digest skill.

    Searches all categories via Grok web_search and filters out
    previously shown videos from Supabase.

    Returns:
        Dict with videos by category and shown_ids for deduplication
    """
    try:
        from jobs.youtube_feed import (
            _search_youtube_grok,
            get_shown_video_ids,
            YOUTUBE_CATEGORIES
        )

        # Get previously shown videos
        shown_ids = await get_shown_video_ids()

        # Search all categories in parallel
        search_tasks = []
        for category_key, config in YOUTUBE_CATEGORIES.items():
            search_tasks.append(
                (category_key, _search_youtube_grok(category_key, config["search_query"]))
            )

        # Run searches
        search_results = await asyncio.gather(
            *[task[1] for task in search_tasks],
            return_exceptions=True
        )

        # Process results by category
        videos_by_category = {}
        for i, (category_key, _) in enumerate(search_tasks):
            result = search_results[i]
            if isinstance(result, Exception):
                logger.warning(f"YouTube search failed for {category_key}: {result}")
                videos_by_category[category_key] = []
                continue

            # Filter out already shown videos, take top 3
            new_videos = [v for v in result if v["video_id"] not in shown_ids][:3]
            videos_by_category[category_key] = new_videos

            # Add to shown_ids to prevent cross-category duplicates
            for v in new_videos:
                shown_ids.add(v["video_id"])

        # Build category info for the skill
        categories_info = {
            key: {"name": cfg["name"], "emoji": cfg["emoji"]}
            for key, cfg in YOUTUBE_CATEGORIES.items()
        }

        return {
            "videos_by_category": videos_by_category,
            "categories": categories_info,
            "fetch_time": datetime.now(UK_TZ).strftime("%Y-%m-%d %H:%M")
        }

    except Exception as e:
        logger.error(f"YouTube data fetch error: {e}")
        return {"error": str(e)}


async def get_school_run_data() -> dict[str, Any]:
    """Fetch data for school-run skill (morning).

    Returns:
        Dict with traffic, weather, uniform, and timing info
    """
    from jobs.school_run import (
        _get_traffic, _get_weather, _get_uniform,
        _calculate_leave_time, _get_morning_activities,
        DAY_NAMES
    )

    try:
        now = datetime.now(UK_TZ)
        weekday = now.weekday()

        # Parallel fetch traffic, weather, and clubs
        traffic_data, weather_data, morning_activities = await asyncio.gather(
            _get_traffic(),
            _get_weather(),
            _get_morning_activities(weekday),
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(traffic_data, Exception):
            logger.warning(f"Failed to get traffic: {traffic_data}")
            traffic_data = {"error": str(traffic_data)}
        if isinstance(weather_data, Exception):
            logger.warning(f"Failed to get weather: {weather_data}")
            weather_data = {"error": str(weather_data)}
        if isinstance(morning_activities, Exception):
            logger.warning(f"Failed to get activities: {morning_activities}")
            morning_activities = []

        # Get uniform requirements
        uniform = _get_uniform(weekday)

        # Calculate leave time
        duration = traffic_data.get("duration_in_minutes", 20)
        leave_time, arrival_time = _calculate_leave_time(duration, weekday)

        return {
            "traffic": traffic_data,
            "weather": {
                "temp_c": weather_data.get("high_temp"),
                "condition": weather_data.get("condition", "Unknown"),
                "rain_probability": weather_data.get("precipitation_probability", 0)
            },
            "uniform": {
                "max": uniform["max"],
                "emmie": uniform["emmie"]
            },
            "activities": morning_activities,
            "suggested_leave": leave_time,
            "target_arrival": arrival_time,
            "day_of_week": DAY_NAMES[weekday] if weekday < 5 else "Weekend",
            "date": now.strftime("%Y-%m-%d")
        }

    except Exception as e:
        logger.error(f"School run data fetch error: {e}")
        return {"error": str(e)}


async def get_school_pickup_data() -> dict[str, Any]:
    """Fetch data for school-pickup skill (afternoon).

    Returns:
        Dict with traffic, weather, clubs, and timing info
    """
    from jobs.school_run import (
        _get_traffic_return, _get_weather, _get_evening_clubs,
        _get_target_pickup, DAY_NAMES
    )

    try:
        now = datetime.now(UK_TZ)
        weekday = now.weekday()

        # Parallel fetch traffic, weather, and clubs
        traffic_data, weather_data, evening_clubs = await asyncio.gather(
            _get_traffic_return(),
            _get_weather(),
            _get_evening_clubs(weekday),
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(traffic_data, Exception):
            logger.warning(f"Failed to get traffic: {traffic_data}")
            traffic_data = {"error": str(traffic_data)}
        if isinstance(weather_data, Exception):
            logger.warning(f"Failed to get weather: {weather_data}")
            weather_data = {"error": str(weather_data)}
        if isinstance(evening_clubs, Exception):
            logger.warning(f"Failed to get clubs: {evening_clubs}")
            evening_clubs = []

        # Get target pickup time
        pickup_hour, pickup_minute = _get_target_pickup(weekday)
        pickup_time = f"{pickup_hour:02d}:{pickup_minute:02d}"

        # Calculate leave time (pickup time - traffic duration - 5 min buffer)
        duration = traffic_data.get("duration_in_minutes", 20)
        total_minutes = pickup_hour * 60 + pickup_minute - duration - 5
        leave_hour = total_minutes // 60
        leave_minute = total_minutes % 60
        leave_time = f"{leave_hour:02d}:{leave_minute:02d}"

        # Format clubs data
        clubs = {}
        for club in evening_clubs:
            child = club.get("child_name", "").lower()
            clubs[child] = {
                "club": club.get("club_name"),
                "end_time": club.get("pickup_time"),
                "pickup_location": club.get("pickup_location", "Main gate")
            }

        return {
            "traffic": traffic_data,
            "weather": {
                "temp_c": weather_data.get("high_temp"),
                "condition": weather_data.get("condition", "Unknown"),
                "rain_probability": weather_data.get("precipitation_probability", 0)
            },
            "clubs": clubs,
            "suggested_leave": leave_time,
            "target_pickup": pickup_time,
            "day_of_week": DAY_NAMES[weekday] if weekday < 5 else "Weekend",
            "date": now.strftime("%Y-%m-%d")
        }

    except Exception as e:
        logger.error(f"School pickup data fetch error: {e}")
        return {"error": str(e)}


async def get_morning_briefing_data() -> dict[str, Any]:
    """Fetch AI news data for morning-briefing skill using Grok.

    Uses Grok's x_search and web_search tools to get:
    - X/Twitter posts about Claude/AI
    - Reddit discussions
    - Web articles

    Returns:
        Dict with raw data from Grok searches
    """
    from datetime import timedelta

    try:
        from jobs.morning_briefing import (
            _search_x,
            _search_reddit,
            _search_web
        )

        # Date range for X search (last 2 days)
        now = datetime.now(UK_TZ)
        to_date = now.strftime("%Y-%m-%d")
        from_date = (now - timedelta(days=2)).strftime("%Y-%m-%d")

        # Search topics in parallel
        x_results, reddit_results, web_results = await asyncio.gather(
            _search_x("Claude AI OR Anthropic OR Claude Code", from_date, to_date),
            _search_reddit("Claude AI OR Anthropic"),
            _search_web("Claude Anthropic AI news"),
            return_exceptions=True
        )

        # Handle exceptions
        x_items = x_results if not isinstance(x_results, Exception) else []
        reddit_items = reddit_results if not isinstance(reddit_results, Exception) else []
        web_items = web_results if not isinstance(web_results, Exception) else []

        logger.info(f"Morning briefing fetch: {len(x_items)} X, {len(reddit_items)} Reddit, {len(web_items)} web")

        # Limit to top items and truncate context to keep payload small
        def trim_items(items, limit=8):
            trimmed = []
            for item in items[:limit]:
                trimmed.append({
                    "url": item.get("url", ""),
                    "title": (item.get("text") or item.get("title", ""))[:100],
                    "context": (item.get("context") or "")[:150],
                })
            return trimmed

        return {
            "x_posts": trim_items(x_items, 8),
            "reddit_posts": trim_items(reddit_items, 6),
            "web_articles": trim_items(web_items, 6),
            "fetch_time": now.strftime("%Y-%m-%d %H:%M"),
            "has_x_data": len(x_items) > 0,
            "has_reddit_data": len(reddit_items) > 0,
            "has_web_data": len(web_items) > 0,
        }

    except Exception as e:
        logger.error(f"Morning briefing data fetch error: {e}")
        return {"error": str(e)}


async def get_whatsapp_keepalive_data() -> dict[str, Any]:
    """Send WhatsApp keepalive ping to maintain sandbox session.

    Sends directly - no Claude Code output needed.
    Runs twice daily (06:00 and 22:00) to keep sandbox active.
    """
    try:
        from twilio.rest import Client
        from config import (
            TWILIO_ACCOUNT_SID,
            TWILIO_AUTH_TOKEN,
            TWILIO_WHATSAPP_FROM
        )

        if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM]):
            return {"sent": False, "error": "Twilio not configured"}

        # Only send to Chris
        recipient = "+447855620978"
        now = datetime.now(UK_TZ)
        time_str = "morning" if now.hour < 12 else "evening"
        message = f"📍 {time_str.title()} keepalive - WhatsApp sandbox active"

        def send_message():
            """Sync function to send WhatsApp via Twilio."""
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            return client.messages.create(
                body=message,
                from_=f"whatsapp:{TWILIO_WHATSAPP_FROM}",
                to=f"whatsapp:{recipient}"
            )

        # Run sync Twilio client in thread to avoid blocking event loop
        msg = await asyncio.to_thread(send_message)

        logger.info(f"WhatsApp keepalive sent: {msg.sid}")
        return {"sent": True, "recipient": recipient, "sid": msg.sid}

    except Exception as e:
        logger.error(f"WhatsApp keepalive error: {e}")
        return {"sent": False, "error": str(e)}


async def get_football_scores_data() -> dict[str, Any]:
    """Fetch today's Premier League matches from Football-Data.org.

    Returns:
        Dict with matches array sorted by status (live first)
    """
    import httpx
    from config import FOOTBALL_DATA_API_KEY

    today = datetime.now(UK_TZ).date().isoformat()

    try:
        if not FOOTBALL_DATA_API_KEY:
            return {"error": "Football Data API key not configured", "matches": []}

        url = f"https://api.football-data.org/v4/competitions/PL/matches"
        params = {"dateFrom": today, "dateTo": today}
        headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

        matches = data.get("matches", [])
        formatted = []

        for m in matches:
            formatted.append({
                "home": m["homeTeam"]["shortName"],
                "away": m["awayTeam"]["shortName"],
                "home_score": m["score"]["fullTime"]["home"],
                "away_score": m["score"]["fullTime"]["away"],
                "status": m["status"],
                "minute": m.get("minute"),
                "kickoff": m["utcDate"],
            })

        # Sort: LIVE/IN_PLAY first, then FINISHED, then SCHEDULED
        status_order = {"LIVE": 0, "IN_PLAY": 0, "PAUSED": 1, "FINISHED": 2, "SCHEDULED": 3, "TIMED": 3}
        formatted.sort(key=lambda x: status_order.get(x["status"], 4))

        logger.info(f"Football scores fetch: {len(formatted)} matches")
        return {"matches": formatted, "date": today}

    except Exception as e:
        logger.error(f"Football scores fetch error: {e}")
        return {"error": str(e), "matches": []}


# ============================================================
# PHASE 8a: Gmail / Calendar / Notion Data Fetchers
# Uses Hadley API (localhost:8100) for all requests
# ============================================================

HADLEY_API_URL = "http://localhost:8100"


async def _hadley_request(endpoint: str) -> dict[str, Any]:
    """Make a request to Hadley API."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{HADLEY_API_URL}{endpoint}", timeout=15)
            return response.json()
    except Exception as e:
        logger.error(f"Hadley API request failed for {endpoint}: {e}")
        return {"error": str(e)}


async def get_email_summary_data() -> dict[str, Any]:
    """Fetch unread email summary via Hadley API."""
    result = await _hadley_request("/gmail/unread")
    if "error" not in result:
        logger.info(f"Email summary fetch: {result.get('unread_count', 0)} unread")
    return result


async def get_schedule_today_data() -> dict[str, Any]:
    """Fetch today's calendar events via Hadley API."""
    result = await _hadley_request("/calendar/today")
    if "error" not in result:
        logger.info(f"Schedule today fetch: {result.get('event_count', 0)} events")
    return result


async def get_schedule_week_data() -> dict[str, Any]:
    """Fetch this week's calendar events via Hadley API."""
    result = await _hadley_request("/calendar/week")
    if "error" not in result:
        logger.info(f"Schedule week fetch: {result.get('total_events', 0)} events")
    return result


async def get_notion_todos_data() -> dict[str, Any]:
    """Fetch todos from Notion via Hadley API."""
    result = await _hadley_request("/notion/todos")
    if "error" not in result:
        logger.info(f"Notion todos fetch: {result.get('count', 0)} items")
    return result


async def get_notion_ideas_data() -> dict[str, Any]:
    """Fetch ideas from Notion via Hadley API."""
    result = await _hadley_request("/notion/ideas")
    if "error" not in result:
        logger.info(f"Notion ideas fetch: {result.get('count', 0)} items")
    return result


async def get_knowledge_digest_data() -> dict[str, Any]:
    """Fetch Second Brain weekly digest data.

    Returns:
        Dict with digest data including new items, connections, fading items
    """
    try:
        from domains.second_brain.digest import get_digest_for_skill
        result = await get_digest_for_skill()
        logger.info(f"Knowledge digest: {result.get('new_items_count', 0)} new items, {result.get('new_connections_count', 0)} connections")
        return result
    except Exception as e:
        logger.error(f"Knowledge digest fetch error: {e}")
        return {"error": str(e), "formatted_message": f"❌ Failed to generate digest: {e}"}


# Map skill names to their data fetchers
# Skills not in this dict use web search (news, etc.)
SKILL_DATA_FETCHERS = {
    "nutrition-summary": get_nutrition_data,
    "hydration": get_hydration_data,
    "health-digest": get_health_digest_data,
    "weekly-health": get_weekly_health_data,
    "monthly-health": get_monthly_health_data,
    "balance-monitor": get_balance_data,
    "youtube-digest": get_youtube_data,
    "school-run": get_school_run_data,
    "school-pickup": get_school_pickup_data,
    "morning-briefing": get_morning_briefing_data,
    "whatsapp-keepalive": get_whatsapp_keepalive_data,
    "football-scores": get_football_scores_data,
    # Phase 8a
    "email-summary": get_email_summary_data,
    "schedule-today": get_schedule_today_data,
    "schedule-week": get_schedule_week_data,
    "notion-todos": get_notion_todos_data,
    "notion-ideas": get_notion_ideas_data,
    # Second Brain
    "knowledge-digest": get_knowledge_digest_data,
}
