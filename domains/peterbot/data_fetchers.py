"""Data fetchers for scheduled jobs.

Pre-fetches data in parallel for skills that need it.
Skills without a fetcher use web search during execution.
"""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
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
        get_nutrition_totals
    )
    from domains.nutrition.config import DAILY_TARGETS, GOAL

    # Calculate yesterday's date for steps and nutrition
    yesterday = (datetime.now(UK_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        # Parallel fetch all health data
        # Sleep and HR are for last night (ending this morning) - use today's date
        # Steps and nutrition are for YESTERDAY's complete day
        results = await asyncio.gather(
            get_sleep(),
            get_steps(date_str=yesterday),  # Yesterday's steps
            get_heart_rate(),
            get_weight(),
            get_nutrition_totals(date=yesterday),  # Yesterday's nutrition
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
            "date": datetime.now(UK_TZ).strftime("%Y-%m-%d"),
            "yesterday": yesterday
        }

        # Sync yesterday's Garmin data to garmin_daily_summary table
        # (fire-and-forget — don't let sync failures break the digest)
        asyncio.create_task(_sync_garmin_to_supabase(yesterday, data))

        return data

    except Exception as e:
        logger.error(f"Health digest data fetch error: {e}")
        return {"error": str(e)}


async def _sync_garmin_to_supabase(date_str: str, data: dict) -> None:
    """Sync fetched Garmin data to garmin_daily_summary table.

    Called after the morning health digest fetches live data.
    Upserts yesterday's steps, sleep, and HR into Supabase so the
    weekly/monthly summaries have data to read.
    """
    import httpx
    from config import SUPABASE_URL, SUPABASE_KEY

    try:
        steps = data.get("steps") or {}
        sleep = data.get("sleep") or {}
        hr = data.get("heart_rate") or {}

        # Only sync if we have at least some data
        step_count = steps.get("steps")
        sleep_hours = sleep.get("total_hours")
        resting_hr = hr.get("resting")

        if step_count is None and sleep_hours is None and resting_hr is None:
            logger.info(f"Garmin sync: no data to sync for {date_str}")
            return

        record = {
            "user_id": "chris",
            "date": date_str,
            "source": "garmin",
        }
        if step_count is not None:
            record["steps"] = step_count
            record["steps_goal"] = steps.get("goal", 15000)
        if sleep_hours is not None:
            record["sleep_hours"] = sleep_hours
        if sleep.get("quality_score") is not None:
            record["sleep_score"] = sleep["quality_score"]
        if resting_hr is not None:
            record["resting_hr"] = resting_hr

        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/garmin_daily_summary?on_conflict=user_id,date",
                headers=headers,
                json=record,
                timeout=15
            )

        if resp.status_code in (200, 201):
            logger.info(f"Garmin sync: upserted {date_str} — steps={step_count}, sleep={sleep_hours}h, rhr={resting_hr}")
        else:
            logger.warning(f"Garmin sync: upsert returned {resp.status_code}: {resp.text}")

    except Exception as e:
        logger.error(f"Garmin sync failed for {date_str}: {e}")


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
            mark_video_shown,
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

        # Mark all selected videos as shown in Supabase so they won't repeat
        for category_key, videos in videos_by_category.items():
            for video in videos:
                await mark_video_shown(video, category_key, video.get("context", ""))

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


def _trim_x_items(items: list, limit: int = 15) -> list:
    """Trim X/Twitter posts with markdown formatting and @handle extraction."""
    import re
    trimmed = []
    for item in items[:limit]:
        url = item.get("url", "")
        title = (item.get("text") or item.get("title", ""))[:100]
        context = (item.get("context") or "")[:200]

        # Extract @handle from X URL (e.g., https://x.com/username/status/123)
        handle_match = re.search(r'x\.com/([^/]+)/', url)
        handle = f"@{handle_match.group(1)}" if handle_match else ""

        # Pre-format markdown link
        markdown_link = f"[{title}]({url})" if url and title else ""

        trimmed.append({
            "url": url,
            "title": title,
            "context": context,
            "handle": handle,
            "markdown_link": markdown_link,
        })
    return trimmed


def _trim_reddit_items(items: list, limit: int = 12) -> list:
    """Trim Reddit posts with markdown formatting and subreddit extraction."""
    import re
    trimmed = []
    for item in items[:limit]:
        url = item.get("url", "")
        title = (item.get("text") or item.get("title", ""))[:100]
        context = (item.get("context") or "")[:200]
        subreddit = item.get("subreddit", "")

        # Extract subreddit if not provided
        if not subreddit and url:
            sub_match = re.search(r'/r/(\w+)/', url)
            subreddit = f"r/{sub_match.group(1)}" if sub_match else ""

        # Pre-format markdown link
        markdown_link = f"[{title}]({url})" if url and title else ""

        trimmed.append({
            "url": url,
            "title": title,
            "context": context,
            "subreddit": subreddit,
            "markdown_link": markdown_link,
        })
    return trimmed


def _trim_web_items(items: list, limit: int = 12) -> list:
    """Trim web articles with markdown formatting."""
    trimmed = []
    for item in items[:limit]:
        url = item.get("url", "")
        title = (item.get("text") or item.get("title", ""))[:100]
        context = (item.get("context") or "")[:200]

        # Pre-format markdown link
        markdown_link = f"[{title}]({url})" if url and title else ""

        trimmed.append({
            "url": url,
            "title": title,
            "context": context,
            "markdown_link": markdown_link,
        })
    return trimmed


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

        # Date range for X search (last 7 days for richer content)
        now = datetime.now(UK_TZ)
        to_date = now.strftime("%Y-%m-%d")
        from_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")

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

        return {
            "x_posts": _trim_x_items(x_items, 15),
            "reddit_posts": _trim_reddit_items(reddit_items, 12),
            "web_articles": _trim_web_items(web_items, 12),
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


async def get_meal_plan_data() -> dict[str, Any]:
    """Fetch current week's meal plan via Hadley API.

    Returns:
        Dict with meal plan data including items and ingredients
    """
    result = await _hadley_request("/meal-plan/current")
    if "error" not in result:
        plan = result.get("plan")
        if plan:
            items_count = len(plan.get("items", []))
            logger.info(f"Meal plan fetch: {items_count} items for week {plan.get('week_start')}")
        else:
            logger.info("Meal plan fetch: no plan for this week")
    return result


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


async def get_morning_quality_data() -> dict[str, Any]:
    """Fetch morning quality report data for self-improving parser.

    Returns:
        Dict with parser health, improvement cycle results, scheduled output health,
        feedback summary, 7-day trends, and action items.
    """
    try:
        from domains.peterbot.morning_quality_report import fetch_morning_quality_data
        result = await fetch_morning_quality_data()
        logger.info(f"Morning quality report: {result.get('fixture_stats', {}).get('total', 0)} fixtures")
        return result
    except Exception as e:
        logger.error(f"Morning quality data fetch error: {e}")
        return {"error": str(e)}


async def run_parser_improvement_cycle() -> dict[str, Any]:
    """Run the parser improvement cycle (Phase 3).

    This is the nightly self-improvement job that:
    1. Reviews captures, fixtures, and feedback
    2. Plans targeted changes
    3. Validates via regression
    4. Commits or rolls back

    Returns:
        Dict with cycle results and report text
    """
    try:
        from domains.peterbot.parser_improver import get_parser_improver
        improver = get_parser_improver()

        # Run the cycle
        result = improver.run_cycle()
        review = improver.review()
        report_text = improver.format_report(result, review)

        logger.info(f"Parser improvement cycle: {result.target_stage or 'no target'}, "
                   f"committed={result.committed}")

        return {
            'report_text': report_text,
            'cycle_id': result.cycle_id,
            'target_stage': result.target_stage,
            'committed': result.committed,
            'review_required': result.review_required,
            'score_before': result.score_before,
            'score_after': result.score_after,
        }
    except Exception as e:
        logger.error(f"Parser improvement cycle error: {e}")
        return {"error": str(e), "report_text": f"❌ Improvement cycle failed: {e}"}


# ============================================================
# Hadley Bricks Inventory Management Integration
# Uses authenticated API calls to localhost:3000
# ============================================================

import os
import httpx

HADLEY_BRICKS_URL = os.getenv("HADLEY_BRICKS_URL", "http://localhost:3000")
HADLEY_BRICKS_API_KEY = os.getenv("HADLEY_BRICKS_API_KEY")


async def _hb_request(
    endpoint: str,
    method: str = "GET",
    json_body: dict = None,
    params: dict = None,
    timeout: int = 30
) -> dict[str, Any]:
    """Make authenticated request to Hadley Bricks API.

    Args:
        endpoint: API endpoint path (e.g., /api/reports/profit-loss)
        method: HTTP method (GET, POST, PATCH)
        json_body: Request body for POST/PATCH
        params: Query parameters for GET
        timeout: Request timeout in seconds (default 30)

    Returns:
        Dict with API response or error
    """
    if not HADLEY_BRICKS_API_KEY:
        return {"error": "HADLEY_BRICKS_API_KEY not configured"}

    headers = {"x-api-key": HADLEY_BRICKS_API_KEY}
    url = f"{HADLEY_BRICKS_URL}{endpoint}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method == "POST":
                response = await client.post(url, headers=headers, json=json_body)
            elif method == "PATCH":
                response = await client.patch(url, headers=headers, json=json_body)
            else:
                return {"error": f"Unsupported method: {method}"}

            if response.status_code == 401:
                return {"error": "Unauthorized - check HADLEY_BRICKS_API_KEY"}
            if response.status_code == 404:
                return {"error": f"Endpoint not found: {endpoint}"}
            if response.status_code >= 400:
                return {"error": f"API error {response.status_code}: {response.text[:200]}"}

            return response.json()

    except httpx.ConnectError:
        return {"error": "Hadley Bricks unavailable - is the app running?"}
    except httpx.TimeoutException:
        return {"error": f"Hadley Bricks request timed out after {timeout}s"}
    except Exception as e:
        logger.error(f"Hadley Bricks request failed for {endpoint}: {e}")
        return {"error": str(e)}


# --- Tier 1: Daily Operations ---

async def get_hb_dashboard_data() -> dict[str, Any]:
    """Fetch dashboard metrics for business summary.

    Combines P&L, inventory valuation, and daily activity.
    """
    try:
        results = await asyncio.gather(
            _hb_request("/api/reports/profit-loss", params={"preset": "this_month"}),
            _hb_request("/api/reports/inventory-valuation"),
            _hb_request("/api/reports/daily-activity", params={"preset": "today"}),
            _hb_request("/api/orders", params={"status": "Paid,Pending"}),
            return_exceptions=True
        )

        pnl, inventory, daily, orders = results

        data = {
            "pnl": pnl if not isinstance(pnl, Exception) else {"error": str(pnl)},
            "inventory": inventory if not isinstance(inventory, Exception) else {"error": str(inventory)},
            "daily": daily if not isinstance(daily, Exception) else {"error": str(daily)},
            "orders": orders if not isinstance(orders, Exception) else {"error": str(orders)},
            "fetch_time": datetime.now(UK_TZ).strftime("%Y-%m-%d %H:%M")
        }

        logger.info(f"HB dashboard fetch: pnl={'error' not in data['pnl']}, inv={'error' not in data['inventory']}")
        return data

    except Exception as e:
        logger.error(f"HB dashboard fetch error: {e}")
        return {"error": str(e)}


async def get_hb_pick_list_data() -> dict[str, Any]:
    """Fetch Amazon and eBay picking lists."""
    try:
        results = await asyncio.gather(
            _hb_request("/api/picking-list/amazon", params={"format": "json"}),
            _hb_request("/api/picking-list/ebay", params={"format": "json"}),
            return_exceptions=True
        )

        amazon, ebay = results

        data = {
            "amazon": amazon if not isinstance(amazon, Exception) else {"error": str(amazon)},
            "ebay": ebay if not isinstance(ebay, Exception) else {"error": str(ebay)},
            "fetch_time": datetime.now(UK_TZ).strftime("%Y-%m-%d %H:%M")
        }

        # Count items
        amazon_count = len(amazon.get("items", [])) if isinstance(amazon, dict) and "items" in amazon else 0
        ebay_count = len(ebay.get("items", [])) if isinstance(ebay, dict) and "items" in ebay else 0
        logger.info(f"HB pick list fetch: {amazon_count} Amazon, {ebay_count} eBay items")

        return data

    except Exception as e:
        logger.error(f"HB pick list fetch error: {e}")
        return {"error": str(e)}


async def get_hb_orders_data() -> dict[str, Any]:
    """Fetch unfulfilled orders."""
    result = await _hb_request("/api/orders", params={"status": "Paid,Pending"})
    if "error" not in result:
        count = len(result.get("orders", []))
        logger.info(f"HB orders fetch: {count} unfulfilled orders")
    return result


async def get_hb_daily_activity_data() -> dict[str, Any]:
    """Fetch today's listings and sales activity."""
    result = await _hb_request("/api/reports/daily-activity", params={"preset": "today"})
    if "error" not in result:
        logger.info(f"HB daily activity fetch: success")
    return result


async def get_hb_arbitrage_data() -> dict[str, Any]:
    """Fetch arbitrage opportunities above profit threshold."""
    try:
        results = await asyncio.gather(
            _hb_request("/api/arbitrage", params={"opportunities": "true", "limit": "20"}),
            _hb_request("/api/arbitrage/summary"),
            return_exceptions=True
        )

        opportunities, summary = results

        data = {
            "opportunities": opportunities if not isinstance(opportunities, Exception) else {"error": str(opportunities)},
            "summary": summary if not isinstance(summary, Exception) else {"error": str(summary)},
            "fetch_time": datetime.now(UK_TZ).strftime("%Y-%m-%d %H:%M")
        }

        opp_count = len(opportunities.get("opportunities", [])) if isinstance(opportunities, dict) else 0
        logger.info(f"HB arbitrage fetch: {opp_count} opportunities")

        return data

    except Exception as e:
        logger.error(f"HB arbitrage fetch error: {e}")
        return {"error": str(e)}


# --- Tier 2: Reports ---

async def get_hb_pnl_data(preset: str = "this_month") -> dict[str, Any]:
    """Fetch P&L summary by period."""
    result = await _hb_request("/api/reports/profit-loss", params={"preset": preset})
    if "error" not in result:
        logger.info(f"HB P&L fetch ({preset}): success")
    return result


async def get_hb_inventory_status_data() -> dict[str, Any]:
    """Fetch inventory valuation and breakdown."""
    result = await _hb_request("/api/reports/inventory-valuation")
    if "error" not in result:
        logger.info(f"HB inventory status fetch: success")
    return result


async def get_hb_inventory_aging_data() -> dict[str, Any]:
    """Fetch slow-moving stock alerts."""
    result = await _hb_request("/api/reports/inventory-aging")
    if "error" not in result:
        logger.info(f"HB inventory aging fetch: success")
    return result


async def get_hb_platform_performance_data(preset: str = "this_month") -> dict[str, Any]:
    """Fetch platform comparison metrics."""
    result = await _hb_request("/api/reports/platform-performance", params={"preset": preset})
    if "error" not in result:
        logger.info(f"HB platform performance fetch ({preset}): success")
    return result


async def get_hb_purchase_analysis_data() -> dict[str, Any]:
    """Fetch ROI analysis by purchase source."""
    result = await _hb_request("/api/reports/purchase-analysis", params={"preset": "this_year"})
    if "error" not in result:
        logger.info(f"HB purchase analysis fetch: success")
    return result


# --- Tier 3: Lookups ---

async def get_hb_set_lookup_data(set_number: str = None) -> dict[str, Any]:
    """Look up LEGO set information and pricing.

    Note: set_number should be passed from conversational context.
    """
    if not set_number:
        return {"error": "No set number provided", "hint": "Pass set number from conversation"}

    try:
        results = await asyncio.gather(
            _hb_request("/api/brickset/lookup", params={"setNumber": set_number}),
            _hb_request("/api/brickset/pricing", params={"setNumber": set_number}),
            _hb_request("/api/brickset/inventory-stock", params={"setNumber": set_number}),
            return_exceptions=True
        )

        lookup, pricing, stock = results

        data = {
            "set_info": lookup if not isinstance(lookup, Exception) else {"error": str(lookup)},
            "pricing": pricing if not isinstance(pricing, Exception) else {"error": str(pricing)},
            "current_stock": stock if not isinstance(stock, Exception) else {"error": str(stock)},
            "set_number": set_number,
            "fetch_time": datetime.now(UK_TZ).strftime("%Y-%m-%d %H:%M")
        }

        logger.info(f"HB set lookup fetch: {set_number}")
        return data

    except Exception as e:
        logger.error(f"HB set lookup fetch error: {e}")
        return {"error": str(e)}


async def get_hb_stock_check_data(set_number: str = None) -> dict[str, Any]:
    """Check current stock for a specific set."""
    if not set_number:
        return {"error": "No set number provided", "hint": "Pass set number from conversation"}

    result = await _hb_request("/api/brickset/inventory-stock", params={"setNumber": set_number})
    if "error" not in result:
        logger.info(f"HB stock check fetch: {set_number}")
    return result


# --- Tier 4: Workflow ---

async def get_hb_tasks_data() -> dict[str, Any]:
    """Fetch today's workflow tasks."""
    result = await _hb_request("/api/workflow/tasks/today")
    if "error" not in result:
        count = len(result.get("tasks", []))
        logger.info(f"HB tasks fetch: {count} tasks")
    return result


async def get_hb_pickups_data() -> dict[str, Any]:
    """Fetch upcoming scheduled pickups."""
    result = await _hb_request("/api/pickups/upcoming")
    if "error" not in result:
        count = len(result.get("pickups", []))
        logger.info(f"HB pickups fetch: {count} upcoming")
    return result


# ============================================================
# HB Full Sync + Pick List Print
# Combined workflow: sync all platforms, download PDFs, print
# ============================================================

async def get_hb_full_sync_and_print_data() -> dict[str, Any]:
    """Execute full HB workflow: sync, get pick lists, download PDFs, print.

    This is the morning workflow that:
    1. Triggers full inventory sync across all platforms
    2. Gets pick list data (JSON for counts)
    3. Downloads PDFs if items exist
    4. Prints PDFs to configured printer
    5. Returns structured data for Discord message + file attachments

    Returns:
        Dict with sync results, pick list data, PDF paths, and print status
    """
    import tempfile
    from pathlib import Path

    result = {
        "sync": {"status": "pending", "data": {}},
        "pick_lists": {
            "amazon": {"status": "pending", "items": 0, "orders": 0, "pdf_path": None},
            "ebay": {"status": "pending", "items": 0, "orders": 0, "pdf_path": None}
        },
        "print_status": {"amazon": None, "ebay": None},
        "files_to_attach": [],  # List of (filepath, filename) tuples for Discord
        "errors": [],
        "fetch_time": datetime.now(UK_TZ).strftime("%Y-%m-%d %H:%M")
    }

    # Step 1: Full sync (long timeout - can take minutes)
    logger.info("HB Full Sync: Starting inventory sync...")
    try:
        sync_result = await _hb_request("/api/workflow/sync-all", method="POST", timeout=300)
        if "error" in sync_result:
            result["sync"]["status"] = "error"
            result["sync"]["data"] = sync_result
            result["errors"].append(f"Sync failed: {sync_result.get('error')}")
            logger.warning(f"HB Full Sync: Sync failed - {sync_result.get('error')}")
        else:
            result["sync"]["status"] = "success"
            result["sync"]["data"] = sync_result
            logger.info(f"HB Full Sync: Sync complete - {sync_result}")
    except Exception as e:
        result["sync"]["status"] = "error"
        result["errors"].append(f"Sync exception: {e}")
        logger.error(f"HB Full Sync: Sync exception - {e}")

    # Step 2: Get pick list data (JSON for counts)
    logger.info("HB Full Sync: Fetching pick list data...")
    amazon_data, ebay_data = await asyncio.gather(
        _hb_request("/api/picking-list/amazon", params={"format": "json"}),
        _hb_request("/api/picking-list/ebay", params={"format": "json"}),
        return_exceptions=True
    )

    # Process Amazon pick list
    if isinstance(amazon_data, Exception):
        result["pick_lists"]["amazon"]["status"] = "error"
        result["errors"].append(f"Amazon pick list error: {amazon_data}")
    elif "error" in amazon_data:
        result["pick_lists"]["amazon"]["status"] = "error"
        result["errors"].append(f"Amazon API error: {amazon_data.get('error')}")
    else:
        items = amazon_data.get("data", {}).get("items", [])
        result["pick_lists"]["amazon"]["status"] = "success"
        result["pick_lists"]["amazon"]["items"] = len(items)
        result["pick_lists"]["amazon"]["orders"] = len(set(i.get("order_id") for i in items if i.get("order_id")))
        result["pick_lists"]["amazon"]["data"] = amazon_data.get("data", {})

    # Process eBay pick list
    if isinstance(ebay_data, Exception):
        result["pick_lists"]["ebay"]["status"] = "error"
        result["errors"].append(f"eBay pick list error: {ebay_data}")
    elif "error" in ebay_data:
        result["pick_lists"]["ebay"]["status"] = "error"
        result["errors"].append(f"eBay API error: {ebay_data.get('error')}")
    else:
        items = ebay_data.get("data", {}).get("items", [])
        result["pick_lists"]["ebay"]["status"] = "success"
        result["pick_lists"]["ebay"]["items"] = len(items)
        result["pick_lists"]["ebay"]["orders"] = len(set(i.get("order_id") for i in items if i.get("order_id")))
        result["pick_lists"]["ebay"]["data"] = ebay_data.get("data", {})

    # Step 3: Download PDFs if items exist
    temp_dir = Path(tempfile.gettempdir()) / "peterbot_picklists"
    temp_dir.mkdir(exist_ok=True)

    # Download Amazon PDF
    if result["pick_lists"]["amazon"]["items"] > 0:
        amazon_pdf = await _download_pick_list_pdf("amazon", temp_dir)
        if amazon_pdf:
            result["pick_lists"]["amazon"]["pdf_path"] = str(amazon_pdf)
            result["files_to_attach"].append((str(amazon_pdf), f"amazon_picklist_{datetime.now(UK_TZ).strftime('%Y%m%d')}.pdf"))
            logger.info(f"HB Full Sync: Amazon PDF downloaded to {amazon_pdf}")

    # Download eBay PDF
    if result["pick_lists"]["ebay"]["items"] > 0:
        ebay_pdf = await _download_pick_list_pdf("ebay", temp_dir)
        if ebay_pdf:
            result["pick_lists"]["ebay"]["pdf_path"] = str(ebay_pdf)
            result["files_to_attach"].append((str(ebay_pdf), f"ebay_picklist_{datetime.now(UK_TZ).strftime('%Y%m%d')}.pdf"))
            logger.info(f"HB Full Sync: eBay PDF downloaded to {ebay_pdf}")

    # Step 4: Add interactive pick list URLs (printing disabled)
    app_url = os.getenv("HADLEY_BRICKS_URL", "https://hadley-bricks-inventory-management.vercel.app")
    if result["pick_lists"]["amazon"]["items"] > 0:
        result["pick_lists"]["amazon"]["pick_url"] = f"{app_url}/pick/amazon"
    if result["pick_lists"]["ebay"]["items"] > 0:
        result["pick_lists"]["ebay"]["pick_url"] = f"{app_url}/pick/ebay"
    result["print_status"]["skipped"] = "Printing disabled — use interactive pick lists"

    logger.info(f"HB Full Sync complete: {result['pick_lists']['amazon']['items']} Amazon, {result['pick_lists']['ebay']['items']} eBay items")
    return result


async def _download_pick_list_pdf(platform: str, dest_dir: Path) -> Optional[Path]:
    """Download pick list PDF from Hadley Bricks API.

    Args:
        platform: 'amazon' or 'ebay'
        dest_dir: Directory to save PDF

    Returns:
        Path to downloaded PDF, or None on failure
    """
    from pathlib import Path

    if not HADLEY_BRICKS_API_KEY:
        logger.warning("Cannot download PDF: HADLEY_BRICKS_API_KEY not configured")
        return None

    url = f"{HADLEY_BRICKS_URL}/api/picking-list/{platform}"
    headers = {"x-api-key": HADLEY_BRICKS_API_KEY}
    params = {"format": "pdf"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers, params=params)

            if response.status_code != 200:
                logger.warning(f"PDF download failed for {platform}: HTTP {response.status_code}")
                return None

            # Check content type
            content_type = response.headers.get("content-type", "")
            if "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
                logger.warning(f"Unexpected content type for {platform} PDF: {content_type}")
                # Try anyway - might still be PDF

            # Save to file
            today = datetime.now(UK_TZ).strftime("%Y%m%d")
            pdf_path = dest_dir / f"{platform}_picklist_{today}.pdf"
            pdf_path.write_bytes(response.content)

            logger.info(f"Downloaded {platform} pick list PDF: {pdf_path} ({len(response.content)} bytes)")
            return pdf_path

    except Exception as e:
        logger.error(f"PDF download error for {platform}: {e}")
        return None


async def get_self_reflect_data() -> dict[str, Any]:
    """Fetch context for self-reflection: recent memories, second brain saves, and job history.

    Gives Peter visibility into what's been happening so he can identify
    proactive tasks to add to HEARTBEAT.md.
    """
    import httpx
    import sqlite3
    from pathlib import Path

    data = {}

    # 1. Recent peterbot-mem observations (what Peter learned from conversations)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "http://localhost:37777/api/context/inject",
                params={"project": "peterbot", "query": "recent"},
                timeout=10,
            )
            if resp.status_code == 200:
                data["recent_memories"] = resp.text[:4000]  # Cap size
            else:
                data["recent_memories"] = "(unavailable)"
    except Exception as e:
        logger.warning(f"Self-reflect: peterbot-mem fetch failed: {e}")
        data["recent_memories"] = "(unavailable)"

    # 2. Recent Second Brain saves
    brain_stats = await _hadley_request("/brain/stats")
    if "error" not in brain_stats:
        recent = brain_stats.get("recent", [])[:10]
        data["recent_brain_saves"] = [
            {"title": r.get("title", "")[:100], "date": r.get("created_at", "")[:10]}
            for r in recent
        ]
    else:
        data["recent_brain_saves"] = []

    # 3. Job execution history (last 24h)
    try:
        db_path = Path(__file__).parent.parent.parent / "peter_dashboard" / "job_history.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            c = conn.cursor()
            c.execute("""
                SELECT job_id,
                       COUNT(*) as total,
                       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as ok,
                       SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) as fail
                FROM job_executions
                WHERE started_at > datetime('now', '-24 hours')
                GROUP BY job_id ORDER BY total DESC
            """)
            data["job_stats_24h"] = [
                {"job": r[0], "total": r[1], "ok": r[2], "fail": r[3]}
                for r in c.fetchall()
            ]
            # Recent failures with details
            c.execute("""
                SELECT job_id, started_at, error_message
                FROM job_executions
                WHERE status != 'success' AND started_at > datetime('now', '-24 hours')
                ORDER BY started_at DESC LIMIT 5
            """)
            data["recent_failures"] = [
                {"job": r[0], "time": r[1], "error": r[2]}
                for r in c.fetchall()
            ]
            conn.close()
        else:
            data["job_stats_24h"] = []
            data["recent_failures"] = []
    except Exception as e:
        logger.warning(f"Self-reflect: job history fetch failed: {e}")
        data["job_stats_24h"] = []
        data["recent_failures"] = []

    # 4. Current HEARTBEAT.md state (so Peter knows what's already tracked)
    heartbeat_path = Path(__file__).parent / "wsl_config" / "HEARTBEAT.md"
    try:
        data["current_heartbeat"] = heartbeat_path.read_text(encoding="utf-8")[:2000]
    except Exception:
        data["current_heartbeat"] = "(could not read)"

    logger.info(f"Self-reflect data: {len(data.get('recent_memories', ''))} chars memories, "
                f"{len(data.get('recent_brain_saves', []))} brain saves, "
                f"{len(data.get('job_stats_24h', []))} job types")
    return data


async def get_heartbeat_data() -> dict[str, Any]:
    """Fetch queued Peter Queue tasks for heartbeat processing.

    Fetches both 'queued' and 'heartbeat_scheduled' tasks, sorts by priority,
    and returns them for the heartbeat skill to pick up.
    """
    PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "someday": 4}

    queued = await _hadley_request("/ptasks?list_type=peter_queue&status=queued&limit=10")
    scheduled = await _hadley_request("/ptasks?list_type=peter_queue&status=heartbeat_scheduled&limit=10")

    # Merge results
    tasks = []
    for result in [queued, scheduled]:
        if "error" not in result:
            tasks.extend(result.get("tasks", []))

    if not tasks:
        logger.info("Heartbeat: no queued ptasks found")
        return {"ptasks": [], "count": 0}

    # Sort by priority
    tasks.sort(key=lambda t: PRIORITY_ORDER.get(t.get("priority", "medium"), 2))

    logger.info(f"Heartbeat: {len(tasks)} ptask(s) ready for processing")
    return {"ptasks": tasks, "count": len(tasks)}


async def get_instagram_prep_data() -> dict[str, Any]:
    """Pre-fetch images for daily-instagram-prep skill.

    Searches Unsplash + Pixabay APIs for 3 LEGO content concepts,
    downloads source images to a shared Windows path accessible from WSL.
    Returns image paths and metadata for Peter to run the optimizer.
    """
    import httpx
    import json
    import tempfile
    from pathlib import Path
    from concurrent.futures import ThreadPoolExecutor

    # Shared dir: Windows-accessible, WSL can reach via /mnt/c/...
    prep_dir = Path(__file__).parent.parent / "data" / "instagram_prep"
    prep_dir.mkdir(parents=True, exist_ok=True)

    # Clean up previous run
    for old in prep_dir.iterdir():
        if old.is_dir():
            import shutil
            shutil.rmtree(old, ignore_errors=True)
        elif old.is_file():
            old.unlink(missing_ok=True)

    # Load API keys
    config_path = Path.home() / ".claude" / "skills" / "unsplash" / "unsplash_config.json"
    if not config_path.exists():
        logger.error("Instagram prep: unsplash_config.json not found")
        return {"error": "Config not found", "images": []}

    config = json.loads(config_path.read_text())
    unsplash_key = config.get("unsplash", {}).get("access_key", "")
    pixabay_key = config.get("pixabay", {}).get("api_key", "")

    if not unsplash_key and not pixabay_key:
        return {"error": "No API keys configured", "images": []}

    # Content pillars for variety
    PILLARS = [
        {"pillar": "LEGO Nostalgia", "queries": ["vintage LEGO classic bricks colorful", "retro LEGO minifigures collection"]},
        {"pillar": "Product Showcase", "queries": ["LEGO Star Wars set display", "LEGO Technic detailed build"]},
        {"pillar": "Behind the Scenes", "queries": ["LEGO sorting bricks organizing", "LEGO collection shelf display"]},
        {"pillar": "Community / Culture", "queries": ["LEGO fan creation MOC", "LEGO convention display"]},
        {"pillar": "Educational", "queries": ["LEGO architecture detailed", "LEGO engineering mechanism"]},
        {"pillar": "Lifestyle", "queries": ["LEGO decoration room shelf", "LEGO desk setup creative"]},
        {"pillar": "Collection Highlight", "queries": ["LEGO impressive collection display", "LEGO minifigure collection rare"]},
    ]

    import random
    random.shuffle(PILLARS)
    selected_pillars = PILLARS[:3]

    async def search_unsplash(client: httpx.AsyncClient, query: str) -> list[dict]:
        if not unsplash_key:
            return []
        try:
            resp = await client.get(
                "https://api.unsplash.com/search/photos",
                headers={"Authorization": f"Client-ID {unsplash_key}"},
                params={"query": query, "per_page": 6},
                timeout=10,
            )
            resp.raise_for_status()
            return [
                {
                    "source": "Unsplash",
                    "photographer": p["user"]["name"],
                    "desc": p.get("alt_description", "")[:100],
                    "w": p["width"], "h": p["height"],
                    "url": p["urls"]["regular"],
                    "trigger": p["links"]["download_location"],
                    "page": p["links"]["html"],
                }
                for p in resp.json().get("results", [])
            ]
        except Exception as e:
            logger.warning(f"Unsplash search failed for '{query}': {e}")
            return []

    async def search_pixabay(client: httpx.AsyncClient, query: str) -> list[dict]:
        if not pixabay_key:
            return []
        try:
            resp = await client.get(
                "https://pixabay.com/api/",
                params={"key": pixabay_key, "q": query, "per_page": 6,
                        "image_type": "photo", "safesearch": "true"},
                timeout=10,
            )
            resp.raise_for_status()
            return [
                {
                    "source": "Pixabay",
                    "photographer": p.get("user", "Unknown"),
                    "desc": p.get("tags", "")[:100],
                    "w": p["imageWidth"], "h": p["imageHeight"],
                    "url": p["largeImageURL"],
                    "trigger": None,
                    "page": p["pageURL"],
                }
                for p in resp.json().get("hits", [])
            ]
        except Exception as e:
            logger.warning(f"Pixabay search failed for '{query}': {e}")
            return []

    images = []
    async with httpx.AsyncClient() as client:
        for i, pillar in enumerate(selected_pillars, 1):
            concept_name = f"concept_{i}"
            concept_dir = prep_dir / concept_name
            concept_dir.mkdir(exist_ok=True)

            # Try each query until we get results
            best = None
            for query in pillar["queries"]:
                results_u, results_p = await asyncio.gather(
                    search_unsplash(client, query),
                    search_pixabay(client, query),
                )
                all_results = results_u + results_p
                # Filter: prefer high-res, avoid very wide panoramas
                all_results = [r for r in all_results if r["w"] > 800 and r["h"] > 600]
                all_results.sort(key=lambda r: r["w"] * r["h"], reverse=True)
                if all_results:
                    best = all_results[0]
                    best["query"] = query
                    break

            if not best:
                logger.warning(f"Instagram prep: no images found for pillar '{pillar['pillar']}'")
                continue

            # Download image
            try:
                img_resp = await client.get(best["url"], timeout=30)
                img_resp.raise_for_status()
                img_path = concept_dir / "source.jpg"
                img_path.write_bytes(img_resp.content)
                logger.info(f"Instagram prep: downloaded {best['source']} image for {pillar['pillar']} ({best['w']}x{best['h']})")

                # Trigger Unsplash download event
                if best.get("trigger"):
                    try:
                        await client.get(best["trigger"],
                            headers={"Authorization": f"Client-ID {unsplash_key}"}, timeout=5)
                    except Exception:
                        pass

                # Upload source image to Google Drive
                drive_link = None
                try:
                    upload_resp = await client.post(
                        f"{HADLEY_API_URL}/drive/upload",
                        params={
                            "file_path": str(img_path),
                            "title": f"instagram_prep_{concept_name}_source.jpg",
                        },
                        timeout=30,
                    )
                    if upload_resp.status_code == 200:
                        drive_data = upload_resp.json()
                        drive_link = drive_data.get("link")
                        logger.info(f"Instagram prep: uploaded {concept_name} to Drive")
                except Exception as e:
                    logger.warning(f"Instagram prep: Drive upload failed for {concept_name}: {e}")

                images.append({
                    "concept_name": concept_name,
                    "pillar": pillar["pillar"],
                    "query": best["query"],
                    "source_path": str(img_path),                    # Windows path
                    "source_path_wsl": f"/mnt/c/{str(img_path).replace(chr(92), '/').split('C:/')[1]}",  # WSL path
                    "drive_link": drive_link,
                    "photographer": best["photographer"],
                    "photo_source": best["source"],
                    "photo_page": best["page"],
                    "width": best["w"],
                    "height": best["h"],
                    "description": best["desc"],
                })
            except Exception as e:
                logger.warning(f"Instagram prep: download failed for {pillar['pillar']}: {e}")

    logger.info(f"Instagram prep: sourced {len(images)} of 3 images")
    return {
        "images": images,
        "prep_dir": str(prep_dir),
        "prep_dir_wsl": f"/mnt/c/{str(prep_dir).replace(chr(92), '/').split('C:/')[1]}",
        "count": len(images),
    }


async def get_vinted_collections_data() -> dict[str, Any]:
    """Fetch Vinted collections ready to collect via Hadley API."""
    result = await _hadley_request("/vinted/collections")
    if "error" not in result:
        logger.info(f"Vinted collections fetch: {result.get('new_count', 0)} new, {result.get('total_count', 0)} total")
    return result


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
    # Meal plan
    "meal-plan": get_meal_plan_data,
    # Phase 8a
    "email-summary": get_email_summary_data,
    "schedule-today": get_schedule_today_data,
    "schedule-week": get_schedule_week_data,
    "notion-todos": get_notion_todos_data,
    "notion-ideas": get_notion_ideas_data,
    # Second Brain
    "knowledge-digest": get_knowledge_digest_data,
    # Self-Improving Parser
    "morning-quality-report": get_morning_quality_data,
    "parser-improve": run_parser_improvement_cycle,
    # Vinted
    "vinted-collections": get_vinted_collections_data,
    # Hadley Bricks - Tier 1 (Daily Operations)
    "hb-dashboard": get_hb_dashboard_data,
    "hb-pick-list": get_hb_pick_list_data,
    "hb-orders": get_hb_orders_data,
    "hb-daily-activity": get_hb_daily_activity_data,
    "hb-arbitrage": get_hb_arbitrage_data,
    # Hadley Bricks - Tier 2 (Reports)
    "hb-pnl": get_hb_pnl_data,
    "hb-inventory-status": get_hb_inventory_status_data,
    "hb-inventory-aging": get_hb_inventory_aging_data,
    "hb-platform-performance": get_hb_platform_performance_data,
    "hb-purchase-analysis": get_hb_purchase_analysis_data,
    # Hadley Bricks - Tier 3 (Lookups) - require args from conversation
    "hb-set-lookup": get_hb_set_lookup_data,
    "hb-stock-check": get_hb_stock_check_data,
    # Hadley Bricks - Tier 4 (Workflow)
    "hb-tasks": get_hb_tasks_data,
    "hb-upcoming-pickups": get_hb_pickups_data,
    # Hadley Bricks - Full Sync + Print
    "hb-full-sync-print": get_hb_full_sync_and_print_data,
    # Heartbeat - Peter Queue pickup
    "heartbeat": get_heartbeat_data,
    # Self-Reflect - memories, brain saves, job history
    "self-reflect": get_self_reflect_data,
    # Instagram - pre-source images via APIs
    "daily-instagram-prep": get_instagram_prep_data,
}
