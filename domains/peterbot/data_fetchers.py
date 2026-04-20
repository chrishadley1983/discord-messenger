"""Data fetchers for scheduled jobs.

Pre-fetches data in parallel for skills that need it.
Skills without a fetcher use web search during execution.
"""

import asyncio
import json
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
    from domains.nutrition.config import get_live_targets

    try:
        totals, steps_data, targets = await asyncio.gather(
            get_today_totals(),
            get_steps(),
            get_live_targets(),
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(totals, Exception):
            logger.warning(f"Failed to get nutrition totals: {totals}")
            totals = {}
        if isinstance(steps_data, Exception):
            logger.warning(f"Failed to get steps: {steps_data}")
            steps_data = {}
        if isinstance(targets, Exception):
            logger.warning(f"Failed to resolve live targets, using defaults: {targets}")
            from domains.nutrition.config import DAILY_TARGETS
            targets = dict(DAILY_TARGETS)

        return {
            "nutrition": totals,
            "steps": steps_data.get("steps", 0) if steps_data else 0,
            "targets": targets,
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
    from domains.nutrition.config import get_live_targets

    try:
        totals, steps_data, targets = await asyncio.gather(
            get_today_totals(),
            get_steps(),
            get_live_targets(),
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(totals, Exception):
            logger.warning(f"Failed to get totals: {totals}")
            totals = {}
        if isinstance(steps_data, Exception):
            logger.warning(f"Failed to get steps: {steps_data}")
            steps_data = {}
        if isinstance(targets, Exception):
            logger.warning(f"Failed to resolve live targets, using defaults: {targets}")
            from domains.nutrition.config import DAILY_TARGETS
            targets = dict(DAILY_TARGETS)

        now = datetime.now(UK_TZ)
        water_ml = totals.get("water_ml", 0)
        water_target = targets["water_ml"]
        steps = steps_data.get("steps", 0) if steps_data else 0
        steps_target = targets["steps"]

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
        get_nutrition_totals, get_hrv, get_stress,
    )
    from domains.nutrition.config import DAILY_TARGETS, GOAL, get_live_targets, get_live_goal

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
            get_hrv(),
            get_stress(),
            return_exceptions=True
        )

        sleep_data, steps_data, hr_data, weight_data, nutrition_data, hrv_data, stress_data = results

        # Resolve live programme-aware targets + goal (with fallback to statics)
        try:
            targets = await get_live_targets()
        except Exception as e:
            logger.warning(f"Live targets failed, using defaults: {e}")
            targets = dict(DAILY_TARGETS)
        try:
            goal = await get_live_goal()
        except Exception as e:
            logger.warning(f"Live goal failed, using defaults: {e}")
            goal = dict(GOAL)

        # Handle exceptions
        data = {
            "sleep": sleep_data if not isinstance(sleep_data, Exception) else None,
            "steps": steps_data if not isinstance(steps_data, Exception) else None,
            "heart_rate": hr_data if not isinstance(hr_data, Exception) else None,
            "weight": weight_data if not isinstance(weight_data, Exception) else None,
            "nutrition": nutrition_data if not isinstance(nutrition_data, Exception) else None,
            "hrv": hrv_data if not isinstance(hrv_data, Exception) else None,
            "stress": stress_data if not isinstance(stress_data, Exception) else None,
            "targets": targets,
            "goal": goal,
            "date": datetime.now(UK_TZ).strftime("%Y-%m-%d"),
            "yesterday": yesterday
        }

        # Sync yesterday's Garmin data to garmin_daily_summary table
        # (fire-and-forget — don't let sync failures break the digest)
        asyncio.create_task(_sync_garmin_to_supabase(yesterday, data))

        # Advisor warnings for the morning message
        try:
            from domains.fitness.advisor import get_advice
            advisor = await get_advice()
            data["advisor"] = advisor
        except Exception as e:
            logger.warning(f"Advisor fetch for health digest failed: {e}")
            data["advisor"] = None

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
        hrv = data.get("hrv") or {}
        stress = data.get("stress") or {}

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
        if hrv.get("weekly_avg") is not None:
            record["hrv_weekly_avg"] = hrv["weekly_avg"]
        if hrv.get("last_night") is not None:
            record["hrv_last_night"] = hrv["last_night"]
        if hrv.get("status") is not None:
            record["hrv_status"] = hrv["status"]
        if stress.get("average") is not None:
            record["avg_stress"] = stress["average"]

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
    from domains.nutrition.config import DAILY_TARGETS, get_live_targets

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

        try:
            targets = await get_live_targets()
        except Exception as e:
            logger.warning(f"Live targets failed, using defaults: {e}")
            targets = dict(DAILY_TARGETS)

        return {
            "weight": weight,
            "nutrition": nutrition,
            "steps": steps,
            "sleep": sleep,
            "heart_rate": hr,
            "goals": goals,
            "targets": targets,
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
    from domains.nutrition.config import DAILY_TARGETS, get_live_targets

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

        try:
            targets = await get_live_targets()
        except Exception as e:
            logger.warning(f"Live targets failed, using defaults: {e}")
            targets = dict(DAILY_TARGETS)

        return {
            "weight": weight,
            "nutrition": nutrition,
            "steps": steps,
            "sleep": sleep,
            "goals": goals,
            "previous_month": prev_month,
            "targets": targets,
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
    from jobs.balance_monitor import _get_claude_data, _get_moonshot_data, _get_grok_data, _get_max_usage
    from domains.api_usage.services.gcp_monitoring import get_gcp_cost_summary

    try:
        claude_data, moonshot_data, grok_data, max_data, gcp_data = await asyncio.gather(
            _get_claude_data(),
            _get_moonshot_data(),
            _get_grok_data(),
            _get_max_usage(),
            get_gcp_cost_summary(),
            return_exceptions=True
        )

        return {
            "claude": claude_data if not isinstance(claude_data, Exception) else {"error": str(claude_data)},
            "moonshot": moonshot_data if not isinstance(moonshot_data, Exception) else {"error": str(moonshot_data)},
            "grok": grok_data if not isinstance(grok_data, Exception) else {"error": str(grok_data)},
            "max": max_data if not isinstance(max_data, Exception) else {"error": str(max_data)},
            "gcp": gcp_data if not isinstance(gcp_data, Exception) else {"error": str(gcp_data)},
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

        # Parallel fetch traffic, weather, clubs, and school events
        traffic_data, weather_data, morning_activities, school_data = await asyncio.gather(
            _get_traffic(),
            _get_weather(),
            _get_morning_activities(weekday),
            get_school_data(),
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
        if isinstance(school_data, Exception):
            logger.warning(f"Failed to get school data: {school_data}")
            school_data = {}

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
            "school_events_today": school_data.get("today_events", []) if isinstance(school_data, dict) else [],
            "is_inset_day": school_data.get("is_inset_day", False) if isinstance(school_data, dict) else False,
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


async def get_whatsapp_health_data() -> dict[str, Any]:
    """Check Evolution API WhatsApp connection health.

    Replaces Twilio keepalive — Evolution API maintains its own session,
    so this just checks the connection is alive.
    """
    try:
        from integrations.whatsapp import check_connection

        result = await check_connection()
        state = result.get("instance", {}).get("state", "unknown")
        return {"connected": state == "open", "state": state}

    except Exception as e:
        logger.error(f"WhatsApp health check error: {e}")
        return {"connected": False, "error": str(e)}


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


async def get_pl_results_data() -> dict[str, Any]:
    """Fetch yesterday's finished PL and Champions League matches for morning roundup.

    Returns NO_REPLY trigger if no finished matches yesterday across any competition.
    Also signals the skill to web search for Dover Athletic results.
    """
    import httpx
    from config import FOOTBALL_DATA_API_KEY

    yesterday = (datetime.now(UK_TZ) - timedelta(days=1)).date().isoformat()

    try:
        if not FOOTBALL_DATA_API_KEY:
            return {"error": "Football Data API key not configured", "pl_matches": [], "cl_matches": []}

        headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
        params = {"dateFrom": yesterday, "dateTo": yesterday, "status": "FINISHED"}

        async with httpx.AsyncClient() as client:
            # Fetch PL and CL in parallel
            pl_url = "https://api.football-data.org/v4/competitions/PL/matches"
            cl_url = "https://api.football-data.org/v4/competitions/CL/matches"

            pl_resp, cl_resp = await asyncio.gather(
                client.get(pl_url, headers=headers, params=params, timeout=10),
                client.get(cl_url, headers=headers, params=params, timeout=10),
                return_exceptions=True,
            )

        def parse_matches(resp):
            if isinstance(resp, Exception):
                logger.warning(f"Match fetch failed: {resp}")
                return []
            resp.raise_for_status()
            data = resp.json()
            matches = data.get("matches", [])
            formatted = []
            for m in matches:
                scorers = []
                for g in m.get("goals", []):
                    scorers.append({
                        "player": g.get("scorer", {}).get("name", "Unknown"),
                        "minute": g.get("minute"),
                        "team": g.get("team", {}).get("shortName", ""),
                        "type": g.get("type", "REGULAR"),
                    })
                formatted.append({
                    "home": m["homeTeam"]["shortName"],
                    "away": m["awayTeam"]["shortName"],
                    "home_score": m["score"]["fullTime"]["home"],
                    "away_score": m["score"]["fullTime"]["away"],
                    "ht_home": m["score"].get("halfTime", {}).get("home"),
                    "ht_away": m["score"].get("halfTime", {}).get("away"),
                    "status": "FINISHED",
                    "kickoff": m["utcDate"],
                    "scorers": scorers,
                    "venue": m.get("venue", ""),
                    "referee": m.get("referees", [{}])[0].get("name", "") if m.get("referees") else "",
                    "home_id": m["homeTeam"]["id"],
                    "away_id": m["awayTeam"]["id"],
                })
            formatted.sort(key=lambda x: x["kickoff"])
            return formatted

        pl_matches = parse_matches(pl_resp)
        cl_matches = parse_matches(cl_resp)

        if not pl_matches and not cl_matches:
            return {"no_matches": True}

        # Find Spurs match in either competition
        spurs_match = None
        for m in pl_matches + cl_matches:
            if m.get("home_id") == 73 or m.get("away_id") == 73:
                spurs_match = m
                break

        logger.info(f"Football results fetch: {len(pl_matches)} PL, {len(cl_matches)} CL")
        return {
            "pl_matches": pl_matches,
            "cl_matches": cl_matches,
            "spurs_match": spurs_match,
            "date": yesterday,
        }

    except Exception as e:
        logger.error(f"Football results fetch error: {e}")
        return {"error": str(e), "pl_matches": [], "cl_matches": []}


async def _get_next_spurs_fixture() -> dict[str, Any] | None:
    """Look up the next scheduled Spurs fixture (up to 14 days ahead)."""
    import httpx
    from config import FOOTBALL_DATA_API_KEY

    if not FOOTBALL_DATA_API_KEY:
        return None

    now = datetime.now(UK_TZ)
    date_from = now.date().isoformat()
    date_to = (now.date() + timedelta(days=14)).isoformat()

    try:
        headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.football-data.org/v4/teams/73/matches",
                headers=headers,
                params={"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED,TIMED"},
                timeout=10,
            )
            resp.raise_for_status()
            matches = resp.json().get("matches", [])

        if not matches:
            return None

        m = matches[0]
        kickoff = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")).astimezone(UK_TZ)
        return {
            "kickoff": kickoff,
            "home": m["homeTeam"]["shortName"],
            "away": m["awayTeam"]["shortName"],
            "competition": m["competition"]["name"],
        }
    except Exception as e:
        logger.warning(f"Failed to fetch next Spurs fixture: {e}")
        return None


async def get_spurs_live_data() -> dict[str, Any]:
    """Fetch live Spurs match data with smart scheduling.

    Match window: 1 hour before kickoff to 1 hour after expected FT.
    Outside the window, returns __skip__ with the next wake time so the
    scheduler can avoid invoking Claude (saving ~£9/day).
    """
    import httpx
    from config import FOOTBALL_DATA_API_KEY

    today = datetime.now(UK_TZ).date().isoformat()
    now = datetime.now(UK_TZ)
    state_file = Path(__file__).parent.parent.parent / "data" / "spurs_live_state.json"

    # --- Check if we're in a sleep window ---
    try:
        if state_file.exists():
            state = json.loads(state_file.read_text(encoding="utf-8"))
            wake_at_str = state.get("wake_at")
            if wake_at_str:
                wake_at = datetime.fromisoformat(wake_at_str)
                if now < wake_at:
                    # Still sleeping — skip without any API call
                    next_fixture = state.get("next_fixture", "")
                    logger.debug(f"Spurs-live sleeping until {wake_at.strftime('%a %d %b %H:%M')} ({next_fixture})")
                    return {"__skip__": True, "reason": f"Sleeping until {wake_at.strftime('%a %d %b %H:%M')} — {next_fixture}"}
            elif state.get("date") != today:
                # Stale state with no wake_at (e.g. FT written but no next fixture found at the time)
                # Look up next fixture now and sleep until then, avoiding repeated API calls
                next_fix = await _get_next_spurs_fixture()
                if next_fix:
                    wake_at = next_fix["kickoff"] - timedelta(hours=1)
                    desc = f"{next_fix['home']} vs {next_fix['away']} ({next_fix['competition']})"
                    try:
                        state_file.write_text(json.dumps({
                            "wake_at": wake_at.isoformat(),
                            "next_fixture": desc,
                            "next_kickoff": next_fix["kickoff"].isoformat(),
                        }), encoding="utf-8")
                    except Exception:
                        pass
                    if now < wake_at:
                        logger.info(f"Spurs-live: stale state, sleeping until {wake_at.strftime('%a %d %b %H:%M')} ({desc})")
                        return {"__skip__": True, "reason": f"No match today. Next: {desc} — waking {wake_at.strftime('%a %d %b %H:%M')}"}
    except Exception:
        pass

    try:
        if not FOOTBALL_DATA_API_KEY:
            return {"spurs_playing": False, "error": "No API key"}

        headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
        params = {"dateFrom": today, "dateTo": today}

        async with httpx.AsyncClient() as client:
            pl_url = "https://api.football-data.org/v4/competitions/PL/matches"
            cl_url = "https://api.football-data.org/v4/competitions/CL/matches"

            pl_resp, cl_resp = await asyncio.gather(
                client.get(pl_url, headers=headers, params=params, timeout=10),
                client.get(cl_url, headers=headers, params=params, timeout=10),
                return_exceptions=True,
            )

        all_matches = []
        for resp in [pl_resp, cl_resp]:
            if isinstance(resp, Exception):
                continue
            resp.raise_for_status()
            all_matches.extend(resp.json().get("matches", []))

        spurs_match = None
        for m in all_matches:
            if m["homeTeam"]["id"] == 73 or m["awayTeam"]["id"] == 73:
                spurs_match = m
                break

        if not spurs_match:
            # No match today — find the next fixture and sleep until 1hr before kickoff
            next_fix = await _get_next_spurs_fixture()
            if next_fix:
                wake_at = next_fix["kickoff"] - timedelta(hours=1)
                desc = f"{next_fix['home']} vs {next_fix['away']} ({next_fix['competition']})"
                try:
                    state_file.parent.mkdir(parents=True, exist_ok=True)
                    state_file.write_text(json.dumps({
                        "wake_at": wake_at.isoformat(),
                        "next_fixture": desc,
                        "next_kickoff": next_fix["kickoff"].isoformat(),
                    }), encoding="utf-8")
                except Exception:
                    pass
                logger.info(f"Spurs-live: no match today, sleeping until {wake_at.strftime('%a %d %b %H:%M')} ({desc})")
                return {"__skip__": True, "reason": f"No match today. Next: {desc} — waking {wake_at.strftime('%a %d %b %H:%M')}"}
            return {"__skip__": True, "reason": "No match today, no fixtures found in next 14 days"}

        # Parse kickoff time
        kickoff_str = spurs_match["utcDate"]
        kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00")).astimezone(UK_TZ)

        # Match window: 1 hour before kickoff to 1 hour after expected FT (~105 min)
        window_start = kickoff - timedelta(hours=1)
        window_end = kickoff + timedelta(minutes=165)  # kickoff + 105min match + 60min buffer

        status = spurs_match["status"]
        is_live = status in ("IN_PLAY", "LIVE", "PAUSED")
        is_finished = status == "FINISHED"

        # Outside window and not live/finished -> sleep until window opens
        if not is_live and not is_finished and (now < window_start or now > window_end):
            if now < window_start:
                # Before match — sleep until window opens
                try:
                    state_file.parent.mkdir(parents=True, exist_ok=True)
                    home = spurs_match["homeTeam"]["shortName"]
                    away = spurs_match["awayTeam"]["shortName"]
                    state_file.write_text(json.dumps({
                        "wake_at": window_start.isoformat(),
                        "next_fixture": f"{home} vs {away}",
                        "next_kickoff": kickoff.isoformat(),
                    }), encoding="utf-8")
                except Exception:
                    pass
                return {"__skip__": True, "reason": f"Match at {kickoff.strftime('%H:%M')}, waking at {window_start.strftime('%H:%M')}"}
            else:
                # After match window — find next fixture
                next_fix = await _get_next_spurs_fixture()
                if next_fix:
                    wake_at = next_fix["kickoff"] - timedelta(hours=1)
                    desc = f"{next_fix['home']} vs {next_fix['away']}"
                    try:
                        state_file.write_text(json.dumps({
                            "wake_at": wake_at.isoformat(),
                            "next_fixture": desc,
                            "next_kickoff": next_fix["kickoff"].isoformat(),
                        }), encoding="utf-8")
                    except Exception:
                        pass
                    return {"__skip__": True, "reason": f"Match over. Next: {desc} — waking {wake_at.strftime('%a %d %b %H:%M')}"}
                return {"__skip__": True, "reason": "Match window ended, no upcoming fixtures found"}

        # Build match data
        home = spurs_match["homeTeam"]["shortName"]
        away = spurs_match["awayTeam"]["shortName"]
        score = spurs_match["score"]

        # Dedup: if FINISHED and we already sent the FT notification, sleep until next fixture
        if is_finished:
            try:
                if state_file.exists():
                    state = json.loads(state_file.read_text(encoding="utf-8"))
                    if state.get("date") == today and state.get("status") == "FINISHED":
                        return {"__skip__": True, "reason": "FT already posted"}
            except Exception:
                pass
            # First FT notification — record it and set wake for next fixture
            next_fix = await _get_next_spurs_fixture()
            ft_state = {"date": today, "status": "FINISHED"}
            if next_fix:
                wake_at = next_fix["kickoff"] - timedelta(hours=1)
                ft_state["wake_at"] = wake_at.isoformat()
                ft_state["next_fixture"] = f"{next_fix['home']} vs {next_fix['away']}"
                ft_state["next_kickoff"] = next_fix["kickoff"].isoformat()
                logger.info(f"Spurs-live: FT! Next fixture wake at {wake_at.strftime('%a %d %b %H:%M')}")
            try:
                state_file.parent.mkdir(parents=True, exist_ok=True)
                state_file.write_text(json.dumps(ft_state), encoding="utf-8")
            except Exception as e:
                logger.debug(f"Spurs state write failed: {e}")

        scorers = []
        if spurs_match.get("goals"):
            for g in spurs_match["goals"]:
                scorers.append({
                    "player": g.get("scorer", {}).get("name", "Unknown"),
                    "minute": g.get("minute"),
                    "team": g.get("team", {}).get("shortName", ""),
                })

        return {
            "spurs_playing": True,
            "home": home,
            "away": away,
            "home_score": score["fullTime"]["home"] if score["fullTime"]["home"] is not None else score.get("halfTime", {}).get("home", 0),
            "away_score": score["fullTime"]["away"] if score["fullTime"]["away"] is not None else score.get("halfTime", {}).get("away", 0),
            "status": status,
            "minute": spurs_match.get("minute"),
            "kickoff": kickoff_str,
            "kickoff_uk": kickoff.strftime("%H:%M"),
            "scorers": scorers,
            "venue": spurs_match.get("venue", ""),
            "date": today,
        }

    except Exception as e:
        logger.error(f"Spurs live fetch error: {e}")
        return {"spurs_playing": False, "error": str(e)}


async def get_spurs_matchday_data() -> dict[str, Any]:
    """Fetch today's Spurs fixture for morning match-day reminder.

    Checks both Premier League and Champions League.
    Returns spurs_playing=false if no match today (NO_REPLY).
    """
    import httpx
    from config import FOOTBALL_DATA_API_KEY

    today = datetime.now(UK_TZ).date().isoformat()

    try:
        if not FOOTBALL_DATA_API_KEY:
            return {"spurs_playing": False, "error": "No API key"}

        headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
        params = {"dateFrom": today, "dateTo": today}

        async with httpx.AsyncClient() as client:
            pl_url = "https://api.football-data.org/v4/competitions/PL/matches"
            cl_url = "https://api.football-data.org/v4/competitions/CL/matches"

            pl_resp, cl_resp = await asyncio.gather(
                client.get(pl_url, headers=headers, params=params, timeout=10),
                client.get(cl_url, headers=headers, params=params, timeout=10),
                return_exceptions=True,
            )

        spurs_match = None
        for resp in [pl_resp, cl_resp]:
            if isinstance(resp, Exception):
                continue
            resp.raise_for_status()
            for m in resp.json().get("matches", []):
                if m["homeTeam"]["id"] == 73 or m["awayTeam"]["id"] == 73:
                    spurs_match = m
                    break
            if spurs_match:
                break

        if not spurs_match:
            return {"spurs_playing": False}

        kickoff_str = spurs_match["utcDate"]
        kickoff = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00")).astimezone(UK_TZ)
        home = spurs_match["homeTeam"]["shortName"]
        away = spurs_match["awayTeam"]["shortName"]
        is_home = spurs_match["homeTeam"]["id"] == 73
        venue = spurs_match.get("venue", "")
        competition = spurs_match.get("competition", {}).get("name", "Premier League")

        return {
            "spurs_playing": True,
            "home": home,
            "away": away,
            "is_home": is_home,
            "kickoff": kickoff_str,
            "kickoff_uk": kickoff.strftime("%H:%M"),
            "venue": venue,
            "competition": competition,
            "date": today,
        }

    except Exception as e:
        logger.error(f"Spurs matchday fetch error: {e}")
        return {"spurs_playing": False, "error": str(e)}


async def get_cricket_scores_data() -> dict[str, Any]:
    """Fetch yesterday's cricket scores from CricAPI (cricketdata.org).

    Covers: English Domestic, Australian Domestic, IPL, International.
    Returns no_matches=true if nothing yesterday.
    """
    import httpx
    from config import CRICKET_API_KEY

    yesterday = (datetime.now(UK_TZ) - timedelta(days=1)).date().isoformat()

    try:
        if not CRICKET_API_KEY:
            return {"error": "Cricket API key not configured — sign up at cricketdata.org"}

        url = "https://api.cricapi.com/v1/currentMatches"
        params = {"apikey": CRICKET_API_KEY, "offset": 0}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

        if data.get("status") != "success":
            return {"error": data.get("status", "API error"), "matches_by_competition": {}}

        all_matches = data.get("data", [])

        # Filter to matches that were active yesterday
        competitions = {
            "International": [],
            "IPL": [],
            "English Domestic": [],
            "Australian Domestic": [],
            "Other": [],
        }

        for m in all_matches:
            match_date = m.get("date", "")
            if not match_date.startswith(yesterday):
                # Also check dateTimeGMT for multi-day matches active yesterday
                dt_str = m.get("dateTimeGMT", "")
                if not dt_str or yesterday not in dt_str:
                    continue

            entry = {
                "name": m.get("name", ""),
                "status": m.get("status", ""),
                "match_type": m.get("matchType", ""),
                "venue": m.get("venue", ""),
                "score": m.get("score", []),
                "teams": m.get("teams", []),
            }

            series = (m.get("series_id", "") + " " + m.get("name", "")).lower()
            if m.get("matchType") in ("t20i", "t20", "odi", "test") or "international" in series or "icc" in series or "world cup" in series:
                competitions["International"].append(entry)
            elif "ipl" in series or "indian premier" in series:
                competitions["IPL"].append(entry)
            elif any(k in series for k in ("county", "vitality", "hundred", "blast", "royal london")):
                competitions["English Domestic"].append(entry)
            elif any(k in series for k in ("sheffield", "big bash", "bbl")):
                competitions["Australian Domestic"].append(entry)
            else:
                competitions["Other"].append(entry)

        # Remove empty categories
        competitions = {k: v for k, v in competitions.items() if v}

        if not competitions:
            return {"no_matches": True}

        total = sum(len(v) for v in competitions.values())
        logger.info(f"Cricket scores fetch: {total} matches across {len(competitions)} competitions")
        return {"matches_by_competition": competitions, "date": yesterday}

    except Exception as e:
        logger.error(f"Cricket scores fetch error: {e}")
        return {"error": str(e), "matches_by_competition": {}}


async def get_saturday_sport_preview_data() -> dict[str, Any]:
    """Fetch sport preview data for the coming week.

    Combines football fixtures (Football-Data.org) and cricket fixtures (CricAPI).
    Dover Athletic and TV schedule are handled by web search in the skill.
    """
    import httpx
    from config import FOOTBALL_DATA_API_KEY, CRICKET_API_KEY

    now = datetime.now(UK_TZ)
    today = now.date().isoformat()
    next_week = (now + timedelta(days=7)).date().isoformat()

    result: dict[str, Any] = {"date": today, "week_ending": next_week}

    # Football: next 7 days of PL fixtures (filter for Spurs specifically)
    try:
        if FOOTBALL_DATA_API_KEY:
            url = "https://api.football-data.org/v4/competitions/PL/matches"
            params = {"dateFrom": today, "dateTo": next_week}
            headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()

            matches = data.get("matches", [])
            all_fixtures = []
            spurs_fixture = None
            for m in matches:
                fixture = {
                    "home": m["homeTeam"]["shortName"],
                    "away": m["awayTeam"]["shortName"],
                    "kickoff": m["utcDate"],
                    "status": m["status"],
                }
                all_fixtures.append(fixture)
                if m["homeTeam"]["id"] == 73 or m["awayTeam"]["id"] == 73:
                    spurs_fixture = fixture

            result["pl_fixtures"] = all_fixtures
            result["spurs_fixture"] = spurs_fixture
        else:
            result["pl_fixtures"] = []
            result["pl_error"] = "No Football Data API key"
    except Exception as e:
        logger.error(f"Saturday preview football error: {e}")
        result["pl_fixtures"] = []
        result["pl_error"] = str(e)

    # Cricket: upcoming matches (international + major tournaments + England/Kent)
    try:
        if CRICKET_API_KEY:
            url = "https://api.cricapi.com/v1/matches"
            params = {"apikey": CRICKET_API_KEY, "offset": 0}

            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()

            if data.get("status") == "success":
                upcoming = []
                for m in data.get("data", []):
                    match_date = m.get("date", "")
                    if not match_date or not (today <= match_date <= next_week):
                        continue

                    teams = m.get("teams", [])
                    teams_lower = " ".join(teams).lower()
                    name_lower = (m.get("name", "") + " " + m.get("series_id", "")).lower()
                    is_england = "england" in teams_lower
                    is_kent = "kent" in teams_lower
                    match_type = m.get("matchType", "")

                    # Include: ICC events, IPL, true internationals, England, Kent
                    # Exclude: domestic leagues from other countries (SA provincial, etc.)
                    is_icc = any(k in name_lower for k in ("icc", "world cup", "champions trophy", "world test"))
                    is_ipl = any(k in name_lower for k in ("ipl", "indian premier"))
                    is_domestic_noise = any(k in name_lower for k in (
                        "csa provincial", "csa division", "sheffield shield", "big bash",
                        "super smash", "ranji", "plunket", "ford trophy",
                        "marsh cup", "vijay hazare", "syed mushtaq",
                    ))
                    # Also filter SA franchise teams that leak through as "odi"
                    sa_teams = ("warriors", "knights", "dolphins", "titans", "lions",
                                "kwazulu", "north west", "border", "limpopo",
                                "eastern storm", "mpumalanga", "northern cape",
                                "south western districts", "boland")
                    if not is_icc and not is_england and not is_kent:
                        if any(t in teams_lower for t in sa_teams):
                            is_domestic_noise = True
                    is_true_international = (
                        match_type in ("t20i", "t20", "odi", "test")
                        and not is_domestic_noise
                    )

                    if is_england or is_kent or is_icc or is_ipl or is_true_international:
                        upcoming.append({
                            "name": m.get("name", ""),
                            "date": match_date,
                            "match_type": match_type,
                            "venue": m.get("venue", ""),
                            "teams": teams,
                            "is_england": is_england,
                            "is_kent": is_kent,
                            "is_icc": is_icc,
                            "is_ipl": is_ipl,
                        })
                result["cricket_fixtures"] = upcoming
            else:
                result["cricket_fixtures"] = []
        else:
            result["cricket_fixtures"] = []
            result["cricket_error"] = "No Cricket API key"
    except Exception as e:
        logger.error(f"Saturday preview cricket error: {e}")
        result["cricket_fixtures"] = []
        result["cricket_error"] = str(e)

    # F1: next race weekend from Jolpica API (free, no key)
    try:
        url = "https://api.jolpi.ca/ergast/f1/current/next.json"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        if races:
            race = races[0]
            race_date = race.get("date", "")
            # Include if race is within the next 7 days
            if race_date and today <= race_date <= next_week:
                f1_data = {
                    "race_name": race.get("raceName", ""),
                    "circuit": race.get("Circuit", {}).get("circuitName", ""),
                    "location": race.get("Circuit", {}).get("Location", {}).get("country", ""),
                    "race_date": race_date,
                    "race_time": race.get("time", ""),
                    "round": race.get("round", ""),
                }
                # Add sprint/qualifying times if available
                if race.get("Sprint"):
                    f1_data["sprint_date"] = race["Sprint"].get("date", "")
                    f1_data["sprint_time"] = race["Sprint"].get("time", "")
                if race.get("Qualifying"):
                    f1_data["qualifying_date"] = race["Qualifying"].get("date", "")
                    f1_data["qualifying_time"] = race["Qualifying"].get("time", "")
                if race.get("FirstPractice"):
                    f1_data["fp1_date"] = race["FirstPractice"].get("date", "")
                    f1_data["fp1_time"] = race["FirstPractice"].get("time", "")
                result["f1"] = f1_data
            else:
                result["f1"] = None
        else:
            result["f1"] = None
    except Exception as e:
        logger.error(f"Saturday preview F1 error: {e}")
        result["f1"] = None
        result["f1_error"] = str(e)

    return result


async def get_ballot_reminders_data() -> dict[str, Any]:
    """Check Gmail for recent ticket ballot notifications.

    Searches for ECB, FA, and Oval Invincibles ballot emails from the last 7 days.
    Returns no_ballots=true if nothing found.
    """
    import httpx

    try:
        queries = [
            '(from:ecb OR from:englandcricket OR from:kiaoval) (ballot OR "priority window" OR "register" OR ticket) newer_than:7d',
            '(from:thefa OR from:englandfootball) (ballot OR "priority window" OR "register" OR ticket) newer_than:7d',
        ]

        all_ballots: list[dict] = []

        async with httpx.AsyncClient() as client:
            for query in queries:
                try:
                    response = await client.get(
                        f"{HADLEY_API_URL}/gmail/search",
                        params={"q": query, "max_results": 5},
                        timeout=15,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        messages = data.get("messages", [])
                        for msg in messages:
                            all_ballots.append({
                                "subject": msg.get("subject", ""),
                                "from": msg.get("from", ""),
                                "date": msg.get("date", ""),
                                "snippet": msg.get("snippet", ""),
                            })
                except Exception as e:
                    logger.warning(f"Ballot Gmail search error: {e}")

        if not all_ballots:
            return {"no_ballots": True}

        logger.info(f"Ballot reminders: {len(all_ballots)} emails found")
        return {"ballots": all_ballots, "count": len(all_ballots)}

    except Exception as e:
        logger.error(f"Ballot reminders fetch error: {e}")
        return {"error": str(e), "no_ballots": True}


def _parse_amazon_order_email(body: str) -> list[dict]:
    """Parse Amazon order confirmation email body into structured items.

    Expected format per item:
      * Item Name
        Quantity: N
        XX.XX GBP
    """
    import re

    items = []
    # Normalise line endings
    body = body.replace('\r\n', '\n').replace('\r', '\n')

    # Match: order number
    order_numbers = re.findall(r'Order #\s*\n?\s*([\d-]+)', body)

    # Match item blocks: "* ItemName\n  Quantity: N\n  XX.XX GBP"
    item_pattern = re.compile(
        r'\*\s+(.+?)\n'           # item name after *
        r'\s+Quantity:\s+(\d+)\n'  # quantity
        r'\s+([\d,.]+)\s+GBP',    # price
        re.MULTILINE
    )

    for match in item_pattern.finditer(body):
        name = match.group(1).strip()
        qty = int(match.group(2))
        price = float(match.group(3).replace(",", ""))
        items.append({
            "name": name,
            "quantity": qty,
            "price_gbp": price,
        })

    # Assign order numbers to items (emails may contain multiple orders)
    # Each order block has its own items, but for simplicity assign first order
    # number found before each item block
    if order_numbers and items:
        # Simple: if 1 order number, assign to all items
        if len(order_numbers) == 1:
            for item in items:
                item["order_number"] = order_numbers[0]
        else:
            # Multiple orders in one email — match by position in text
            for item in items:
                item["order_number"] = order_numbers[0]  # default
                item_pos = body.find(item["name"])
                for on in reversed(order_numbers):
                    on_pos = body.find(on)
                    if on_pos < item_pos:
                        item["order_number"] = on
                        break

    return items


def _classify_by_item_name(name: str) -> str:
    """Heuristic classification based on item description keywords."""
    n = name.lower()

    # Business keywords — Hadley Bricks LEGO resale supplies
    biz_keywords = (
        "bubble wrap", "packing tape", "packaging tape", "parcel tape",
        "shipping label", "mailing bag", "jiffy bag", "padded envelope",
        "cardboard box",
        "lego ", "lego\xa0", "minifig",
        "label printer", "thermal label", "barcode",
        "sellotape", "stretch wrap", "void fill", "tissue paper",
        "poly mailer", "postal", "postage", "fragile tape",
        "weighing scale", "letter scale",
    )
    if any(k in n for k in biz_keywords):
        return "business"

    # Personal keywords — household, personal, family
    personal_keywords = (
        "running sock", "running shoe", "garmin", "fitbit",
        "kitchen", "cookware", "pan ", "pot ", "lid for pot",
        "bulb", "lamp", "light ", "lighting",
        "phone holder", "phone case", "phone charger",
        "kids", "children", "toy ", "costume",
        "clothing", "shirt", "socks", "underwear", "shoe",
        "food", "snack", "vitamin", "supplement",
        "book ", "kindle",
        "cleaning", "washing", "laundry", "dishwasher",
        "garden", "plant", "compost",
        "bathroom", "shower", "toothbrush",
        "pet ", "dog ", "cat ",
        "moisture absorber", "dehumidifier",
        "storage box", "storage container", "tote box",
        "picture frame", "hanging", "pegs",
        "radio", "dab",
        "cable", "charger",
    )
    if any(k in n for k in personal_keywords):
        return "personal"

    return "unknown"


async def _classify_amazon_purchase(
    amount: float, email_date: str, item_name: str = ""
) -> str:
    """Classify an Amazon purchase as 'business' or 'personal'.

    Priority: 1) Monzo transaction match, 2) Item name heuristics.
    Chris uses his business card on his personal Amazon account.
    Monzo shows 'AMZNMktplace' for business card, 'AMAZON' for personal.
    """
    import os
    import httpx
    from datetime import datetime, timedelta

    supabase_url = os.getenv("SUPABASE_URL", "")
    api_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_KEY", "")
    if not supabase_url or not api_key:
        return "unknown"

    try:
        # Parse the email date to get a search window (±3 days for settlement lag)
        # Email dates come as e.g. "Thu, 6 Mar 2026 10:23:45 +0000"
        parsed_date = None
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%d"):
            try:
                parsed_date = datetime.strptime(email_date.strip(), fmt).date()
                break
            except ValueError:
                continue
        if not parsed_date:
            # Try just extracting a date-like string
            import re
            m = re.search(r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})', email_date)
            if m:
                from datetime import datetime as dt
                parsed_date = dt.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y").date()
        if not parsed_date:
            return "unknown"

        start = (parsed_date - timedelta(days=3)).isoformat()
        end = (parsed_date + timedelta(days=3)).isoformat()

        headers = {
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Accept-Profile": "finance",
        }

        # Search for Amazon transactions near this amount and date
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{supabase_url}/rest/v1/transactions",
                params={
                    "or": "(description.ilike.*amazon*,description.ilike.*AMZN*)",
                    "date": f"gte.{start}",
                    "and": f"(date.lte.{end})",
                    "select": "description,amount,date",
                    "order": "date.desc",
                    "limit": "20",
                },
                headers=headers,
            )
            if resp.status_code != 200:
                return "unknown"

            txns = resp.json()

        # Match by amount (within £0.05 tolerance for rounding)
        for txn in txns:
            txn_amount = abs(float(txn.get("amount", 0)))
            if abs(txn_amount - amount) < 0.05:
                desc = txn.get("description", "").upper()
                if "AMZNMKTPLACE" in desc or "AMZN MKTP" in desc:
                    return "business"
                elif "AMAZON" in desc:
                    return "personal"

        # No Monzo match — fall back to item name heuristics
        return _classify_by_item_name(item_name)
    except Exception as e:
        logger.debug(f"Monzo classification failed: {e}")
        return _classify_by_item_name(item_name)


async def _sync_amazon_emails(query: str, limit: int, timeout: int) -> dict[str, Any]:
    """Shared logic for syncing Amazon purchase emails to Second Brain."""
    import httpx
    from domains.second_brain import db
    from domains.second_brain.pipeline import process_capture
    from domains.second_brain.types import ContentType, CaptureType

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{HADLEY_API_URL}/gmail/search",
                params={
                    "q": query,
                    "limit": limit,
                    "account": "personal",
                },
                timeout=timeout,
            )
            if response.status_code != 200:
                return {"error": f"Gmail search failed: {response.status_code}"}

            emails = response.json().get("emails", [])
            if not emails:
                return {"synced": 0, "message": "No Amazon orders found"}

            synced = 0
            skipped = 0
            all_items: list[dict] = []

            for email in emails:
                email_id = email["id"]
                email_date = email.get("date", "")

                # Check if already saved (deduplicate by source URL)
                source_url = f"amazon-order://{email_id}"
                existing = await db.get_item_by_source(source_url)
                if existing:
                    skipped += 1
                    continue

                # Fetch full email body
                body_resp = await client.get(
                    f"{HADLEY_API_URL}/gmail/get",
                    params={"id": email_id, "account": "personal"},
                    timeout=15,
                )
                if body_resp.status_code != 200:
                    continue

                body = body_resp.json().get("body", "")
                items = _parse_amazon_order_email(body)

                if not items:
                    continue

                # Save each item as a Second Brain entry
                for item in items:
                    # Classify as business or personal via Monzo
                    total_price = item["price_gbp"] * item["quantity"]
                    category = await _classify_amazon_purchase(total_price, email_date, item["name"])
                    item["category"] = category

                    category_tag = f"amazon-{category}" if category != "unknown" else "amazon"
                    title = f"Amazon Purchase: {item['name'][:80]}"
                    full_text = (
                        f"Amazon Purchase: {item['name']}\n"
                        f"Price: £{item['price_gbp']:.2f}\n"
                        f"Quantity: {item['quantity']}\n"
                        f"Order: {item.get('order_number', 'Unknown')}\n"
                        f"Date: {email_date}\n"
                        f"Category: {category}\n"
                    )
                    result = await process_capture(
                        source=source_url,
                        capture_type=CaptureType.SEED,
                        content_type_override=ContentType.NOTE,
                        text=full_text,
                        title_override=title,
                        user_tags=["amazon", "purchase", category_tag],
                    )
                    if result:
                        synced += 1
                    else:
                        logger.warning(f"Pipeline failed for Amazon item: {title}")
                    all_items.append(item)

            logger.info(f"Amazon purchases sync: {synced} saved, {skipped} skipped")
            return {
                "synced": synced,
                "skipped": skipped,
                "total_emails": len(emails),
                "items": all_items,
            }

    except Exception as e:
        logger.error(f"Amazon purchases sync error: {e}")
        return {"error": str(e), "synced": 0}


async def get_amazon_purchases_data() -> dict[str, Any]:
    """Sync Amazon purchase confirmation emails to Second Brain.

    Searches Gmail for order confirmations from the last 2 days,
    parses items/prices, classifies as business/personal via Monzo,
    and saves structured entries to Second Brain.
    """
    return await _sync_amazon_emails(
        query="from:auto-confirm@amazon.co.uk subject:Ordered newer_than:2d",
        limit=20,
        timeout=30,
    )


async def get_amazon_purchases_backfill_data(days: int = 365) -> dict[str, Any]:
    """Backfill Amazon purchases from the last N days.

    Same as get_amazon_purchases_data but with a wider time window.
    """
    return await _sync_amazon_emails(
        query=f"from:auto-confirm@amazon.co.uk subject:Ordered newer_than:{days}d",
        limit=200,
        timeout=60,
    )


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


async def get_meal_plan_generator_data() -> dict[str, Any]:
    """Fetch all data needed for intelligent meal plan generation.

    Pulls: default template, preferences, Gousto lock-ins, calendar events,
    recent meal history, due staples, and candidate recipes from Second Brain.
    """
    import asyncio
    import httpx

    async def _fetch(endpoint):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{HADLEY_API_URL}{endpoint}", timeout=15)
                return resp.json()
        except Exception as e:
            return {"error": str(e)}

    # Parallel fetch all data sources
    results = await asyncio.gather(
        _fetch("/meal-plan/templates/default"),
        _fetch("/meal-plan/preferences"),
        _fetch("/meal-plan/current"),
        _fetch("/meal-plan/history?days=21"),
        _fetch("/meal-plan/staples/due"),
        _fetch("/calendar/meal-context"),
        _fetch("/recipes/batch-friendly?limit=10"),
        _fetch("/grocery/price-cache"),
    )

    template_data, prefs_data, current_plan, history_data, staples_data, calendar_data, batch_data, price_data = results

    # Search Second Brain for candidate recipes
    recipe_candidates = {"error": "not fetched"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{HADLEY_API_URL}/brain/search",
                params={"query": "family dinner recipe high protein", "limit": "20"},
                timeout=15
            )
            recipe_candidates = resp.json()
    except Exception as e:
        recipe_candidates = {"error": str(e)}

    data = {
        "template": template_data.get("template"),
        "preferences": prefs_data.get("preferences"),
        "current_plan": current_plan.get("plan"),
        "recent_history": history_data.get("history", []),
        "due_staples": staples_data.get("staples", []),
        "calendar_context": calendar_data,
        "recipe_candidates": recipe_candidates.get("results", []),
        "batch_candidates": batch_data.get("recipes", []),
        "price_data": price_data,
        "week_start": (datetime.now().date() - timedelta(days=datetime.now().date().weekday())).isoformat(),
        "date_lookup": {day: (datetime.now().date() - timedelta(days=datetime.now().date().weekday()) + timedelta(days=i)).strftime("%A %d %B → %Y-%m-%d") for i, day in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"], start=0)},
        "next_week_date_lookup": {day: (datetime.now().date() - timedelta(days=datetime.now().date().weekday()) + timedelta(days=7+i)).strftime("%A %d %B → %Y-%m-%d") for i, day in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"], start=0)},
    }

    logger.info(
        f"Meal plan generator data: template={'yes' if data['template'] else 'no'}, "
        f"history={len(data['recent_history'])}, candidates={len(data['recipe_candidates'])}, "
        f"staples_due={len(data['due_staples'])}"
    )
    return data


async def get_meal_rating_data() -> dict[str, Any]:
    """Fetch today's meal plan and any unrated history for the rating prompt."""
    import asyncio

    results = await asyncio.gather(
        _hadley_request("/meal-plan/current"),
        _hadley_request("/meal-plan/history?days=1"),
    )

    current_plan, today_history = results

    # Find today's planned meal
    today = datetime.now().date().isoformat()
    todays_meals = []
    plan = current_plan.get("plan")
    if plan:
        for item in plan.get("items", []):
            if item.get("date") == today:
                todays_meals.append(item)

    # Check if today's meals have been rated
    rated_today = {h.get("meal_name", "").lower() for h in today_history.get("history", [])}

    data = {
        "todays_meals": todays_meals,
        "already_rated": list(rated_today),
        "date": today,
    }

    logger.info(f"Meal rating data: {len(todays_meals)} meals planned, {len(rated_today)} rated")
    return data


async def get_cooking_reminder_data() -> dict[str, Any]:
    """Fetch cooking reminders. Returns evening or morning reminders based on time of day."""
    hour = datetime.now(UK_TZ).hour

    if hour < 12:
        # Morning run — defrost reminders for today
        result = await _hadley_request("/meal-plan/reminders?timing=morning")
        result["reminder_type"] = "morning"
    else:
        # Evening run — prep reminders for tomorrow
        result = await _hadley_request("/meal-plan/reminders?timing=night_before")
        result["reminder_type"] = "evening"

    logger.info(f"Cooking reminders ({result.get('reminder_type')}): {result.get('count', 0)} reminders")
    return result


async def get_price_scanner_data() -> dict[str, Any]:
    """Fetch current price cache for the price scanner report."""
    result = await _hadley_request("/grocery/price-cache")
    logger.info(f"Price cache data: {result.get('on_offer_count', 0)} deals")
    return result


async def get_grocery_shop_data() -> dict[str, Any]:
    """Fetch data needed for grocery shopping: shopping list, trolley, login status."""
    import asyncio

    results = await asyncio.gather(
        _hadley_request("/meal-plan/shopping-list"),
        _hadley_request("/grocery/sainsburys/trolley"),
        _hadley_request("/grocery/sainsburys/login-check"),
    )

    shopping_list, trolley, login_status = results

    data = {
        "shopping_list": shopping_list.get("ingredients", shopping_list.get("items", [])),
        "trolley": trolley if "error" not in trolley else {"items": [], "error": trolley.get("error")},
        "login_status": login_status,
        "store": "sainsburys",
    }

    logger.info(
        f"Grocery shop data: {len(data['shopping_list'])} shopping items, "
        f"trolley={'ok' if 'error' not in trolley else 'error'}, "
        f"login={'yes' if login_status.get('logged_in') else 'no'}"
    )
    return data


async def get_recipe_discovery_data() -> dict[str, Any]:
    """Fetch discovery context for recipe recommendations."""
    result = await _hadley_request("/recipes/discover?count=3")
    logger.info(
        f"Recipe discovery data: {result.get('top_rated_count', 0)} top-rated, "
        f"cuisines={result.get('preferred_cuisines', [])}"
    )
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

    # Step 5: Send pick list summary to Chris via WhatsApp
    amazon_items = result["pick_lists"]["amazon"]["items"]
    ebay_items = result["pick_lists"]["ebay"]["items"]
    if amazon_items > 0 or ebay_items > 0:
        try:
            from integrations.whatsapp import send_to_chris
            lines = ["*Pick List*"]
            if amazon_items > 0:
                amazon_orders = result["pick_lists"]["amazon"].get("orders", 0)
                lines.append(f"Amazon: {amazon_items} items ({amazon_orders} orders)")
                amazon_pick_data = result["pick_lists"]["amazon"].get("data", {})
                for item in amazon_pick_data.get("items", [])[:15]:
                    loc = item.get("location") or "?"
                    set_no = item.get("setNo") or item.get("asin") or "-"
                    qty = item.get("quantity", 1)
                    lines.append(f"  {set_no} x{qty} → {loc}")
                if amazon_items > 15:
                    lines.append(f"  ... +{amazon_items - 15} more")
                lines.append(f"  {app_url}/pick/amazon")
            if ebay_items > 0:
                ebay_orders = result["pick_lists"]["ebay"].get("orders", 0)
                lines.append(f"eBay: {ebay_items} items ({ebay_orders} orders)")
                ebay_pick_data = result["pick_lists"]["ebay"].get("data", {})
                for item in ebay_pick_data.get("items", [])[:15]:
                    loc = item.get("location") or "?"
                    set_no = item.get("setNo") or "-"
                    qty = item.get("quantity", 1)
                    lines.append(f"  {set_no} x{qty} → {loc}")
                if ebay_items > 15:
                    lines.append(f"  ... +{ebay_items - 15} more")
                lines.append(f"  {app_url}/pick/ebay")
            await send_to_chris("\n".join(lines))
        except Exception as e:
            logger.warning(f"WhatsApp pick list send failed: {e}")

    logger.info(f"HB Full Sync complete: {amazon_items} Amazon, {ebay_items} eBay items")
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

    # 1. Recent conversation memories (from Second Brain)
    try:
        from domains.second_brain.db import get_recent_items
        recent_items = await get_recent_items(limit=10)
        if recent_items:
            memories = []
            for item in recent_items:
                title = (item.title or "Untitled")[:80]
                summary = (item.summary or "")[:200]
                memories.append(f"- {title}: {summary}")
            data["recent_memories"] = "\n".join(memories)[:4000]
        else:
            data["recent_memories"] = "(no recent items)"
    except Exception as e:
        logger.warning(f"Self-reflect: Second Brain fetch failed: {e}")
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
    """Fetch queued Peter Queue tasks and recent job health for heartbeat processing.

    Fetches both 'queued' and 'heartbeat_scheduled' tasks, sorts by priority,
    and includes recent job failures for proactive monitoring.
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

    # Sort by priority
    tasks.sort(key=lambda t: PRIORITY_ORDER.get(t.get("priority", "medium"), 2))

    # Fetch recent job failures (last 1 hour for heartbeat context)
    job_health = {"recent_failures": [], "error": None}
    try:
        health_data = await _hadley_request("/jobs/health?hours=1")
        if "error" not in health_data:
            failures = []
            for system in ["dm", "hb"]:
                sys_data = health_data.get(system, {})
                for f in sys_data.get("failures", []):
                    failures.append({
                        "system": "DM" if system == "dm" else "HB",
                        "job": f.get("job", "unknown"),
                        "at": f.get("at", ""),
                        "error": f.get("error", "")[:100],
                    })
            job_health["recent_failures"] = failures
            if failures:
                logger.info(f"Heartbeat: {len(failures)} job failure(s) in last hour")
        else:
            job_health["error"] = health_data.get("error", "unknown")
    except Exception as e:
        logger.warning(f"Heartbeat: failed to fetch job health: {e}")
        job_health["error"] = str(e)

    # Fetch channel health status
    channel_health = {}
    channel_endpoints = {
        "peter-channel": "http://localhost:8104/health",
        "whatsapp-channel": "http://localhost:8102/health",
        "jobs-channel": "http://localhost:8103/health",
    }
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            for name, url in channel_endpoints.items():
                try:
                    resp = await client.get(url, timeout=5.0)
                    channel_health[name] = {"status": "up", "details": resp.json() if resp.status_code == 200 else {}}
                except Exception:
                    channel_health[name] = {"status": "down"}
    except Exception as e:
        logger.warning(f"Heartbeat: failed to check channel health: {e}")
        for name in channel_endpoints:
            channel_health[name] = {"status": "unknown", "error": str(e)}

    down_channels = [n for n, s in channel_health.items() if s.get("status") != "up"]
    if down_channels:
        logger.warning(f"Heartbeat: DOWN channels: {', '.join(down_channels)}")

    logger.info(f"Heartbeat: {len(tasks)} ptask(s) ready for processing")
    return {"ptasks": tasks, "count": len(tasks), "job_health": job_health, "channel_health": channel_health}


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


async def get_school_data() -> dict[str, Any]:
    """Fetch school data: this week's spellings + upcoming events from Supabase.

    Returns:
        Dict with spellings for both children and upcoming school events
    """
    import httpx
    import os
    import json as _json
    from datetime import date, timedelta

    SUPABASE_URL = "https://modjoikyuhqzouxvieua.supabase.co"
    SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }

    try:
        now = datetime.now(UK_TZ)
        today = now.date()
        week_ahead = (today + timedelta(days=7)).isoformat()

        # Calculate teaching week by counting Mondays within term dates
        # (naive calendar weeks overcount by ~8 weeks due to holidays)
        # Calibrated: 2026-03-06 = spelling week 19 (confirmed by parent)
        TERM_DATES_2025_26 = [
            (date(2025, 9, 4),  date(2025, 10, 24)),  # Autumn 1
            (date(2025, 11, 3), date(2025, 12, 19)),   # Autumn 2
            (date(2026, 1, 5),  date(2026, 2, 13)),    # Spring 1
            (date(2026, 2, 23), date(2026, 3, 27)),    # Spring 2
            (date(2026, 4, 13), date(2026, 5, 22)),    # Summer 1
            (date(2026, 6, 1),  date(2026, 7, 22)),    # Summer 2
        ]
        # Offset accounts for inset days and assessment weeks with no spellings
        SPELLING_WEEK_OFFSET = -3
        teaching_week = 0
        for term_start, term_end in TERM_DATES_2025_26:
            monday = term_start + timedelta(days=(7 - term_start.weekday()) % 7)
            while monday <= min(today, term_end):
                teaching_week += 1
                monday += timedelta(days=7)
            if today <= term_end:
                break
        current_week = max(1, min(36, teaching_week + SPELLING_WEEK_OFFSET))

        async with httpx.AsyncClient(timeout=15) as client:
            spellings_resp, events_resp, today_events_resp, inset_resp = await asyncio.gather(
                client.get(
                    f"{SUPABASE_URL}/rest/v1/school_spellings",
                    params={"academic_year": "eq.2025-26", "week_number": f"eq.{current_week}", "select": "*"},
                    headers=headers,
                ),
                client.get(
                    f"{SUPABASE_URL}/rest/v1/school_events",
                    params={"event_date": f"gte.{today.isoformat()}", "order": "event_date", "limit": "10", "select": "*"},
                    headers=headers,
                ),
                client.get(
                    f"{SUPABASE_URL}/rest/v1/school_events",
                    params={"event_date": f"eq.{today.isoformat()}", "select": "*"},
                    headers=headers,
                ),
                client.get(
                    f"{SUPABASE_URL}/rest/v1/school_inset_days",
                    params={"inset_date": f"eq.{today.isoformat()}", "select": "*"},
                    headers=headers,
                ),
                return_exceptions=True,
            )

        spellings = spellings_resp.json() if not isinstance(spellings_resp, Exception) and spellings_resp.status_code == 200 else []
        upcoming_events = events_resp.json() if not isinstance(events_resp, Exception) and events_resp.status_code == 200 else []
        today_events = today_events_resp.json() if not isinstance(today_events_resp, Exception) and today_events_resp.status_code == 200 else []
        is_inset = len(inset_resp.json()) > 0 if not isinstance(inset_resp, Exception) and inset_resp.status_code == 200 else False

        # Parse spelling words (stored as JSON string or list)
        children_spellings = {}
        for s in spellings:
            words = s["words"]
            if isinstance(words, str):
                words = _json.loads(words)
            children_spellings[s["child_name"]] = {
                "words": words,
                "phoneme": s.get("phoneme"),
                "year_group": s["year_group"],
            }

        return {
            "spellings": {"week_number": current_week, "children": children_spellings},
            "today_events": today_events,
            "upcoming_events": upcoming_events[:10],
            "is_inset_day": is_inset,
            "date": today.isoformat(),
        }

    except Exception as e:
        logger.error(f"School data fetch error: {e}")
        return {"error": str(e)}


async def get_github_activity_data(mode: str = "daily") -> dict[str, Any]:
    """Fetch GitHub activity for the github-activity skill.

    Args:
        mode: "daily" (yesterday) or "weekly" (last 7 days)

    Returns:
        Dict with commits and merged PRs per repo
    """
    import os
    import httpx

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return {"error": "GITHUB_TOKEN not configured"}

    repos = [
        "chrishadley1983/discord-messenger",
        "chrishadley1983/hadley-bricks-inventory-management",
        "chrishadley1983/finance-tracker",
        "chrishadley1983/family-meal-planner",
    ]

    now = datetime.now(UK_TZ)
    if mode == "weekly":
        since = (now - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00Z")
        wc_date = now - timedelta(days=7)
        period_label = f"w/c {wc_date.day} {wc_date.strftime('%B')}"
    else:
        since = (now - timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
        yesterday = now - timedelta(days=1)
        period_label = f"{yesterday.strftime('%A')}, {yesterday.day} {yesterday.strftime('%B')}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    repo_data = {}
    total_commits = 0
    total_prs = 0

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            for repo_full in repos:
                repo_name = repo_full.split("/")[1]

                # Fetch commits since period start
                commits_resp = await client.get(
                    f"https://api.github.com/repos/{repo_full}/commits",
                    headers=headers,
                    params={"since": since, "per_page": 50},
                )

                commits = []
                if commits_resp.status_code == 200:
                    for c in commits_resp.json():
                        msg = c.get("commit", {}).get("message", "")
                        if msg.startswith("Merge ") or len(msg) < 10:
                            continue
                        commits.append({
                            "sha": c.get("sha", "")[:7],
                            "message": msg.split("\n")[0][:80],
                            "author": c.get("commit", {}).get("author", {}).get("name", "Unknown"),
                            "date": c.get("commit", {}).get("author", {}).get("date", ""),
                            "url": c.get("html_url", ""),
                        })

                # Fetch merged PRs in period
                prs_resp = await client.get(
                    f"https://api.github.com/repos/{repo_full}/pulls",
                    headers=headers,
                    params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": 20},
                )

                prs_merged = []
                if prs_resp.status_code == 200:
                    for pr in prs_resp.json():
                        merged_at = pr.get("merged_at")
                        if merged_at and merged_at >= since:
                            prs_merged.append({
                                "number": pr["number"],
                                "title": pr["title"][:80],
                                "merged_at": merged_at,
                                "url": pr.get("html_url", ""),
                            })

                if commits or prs_merged:
                    repo_data[repo_name] = {
                        "commits": commits,
                        "prs_merged": prs_merged,
                        "commit_count": len(commits),
                        "pr_count": len(prs_merged),
                    }
                    total_commits += len(commits)
                    total_prs += len(prs_merged)

        return {
            "mode": mode,
            "period": period_label,
            "repos": repo_data,
            "totals": {
                "commits": total_commits,
                "prs_merged": total_prs,
                "active_repos": len(repo_data),
            },
            "fetch_time": now.strftime("%Y-%m-%d %H:%M"),
        }

    except Exception as e:
        logger.error(f"GitHub activity data fetch error: {e}")
        return {"error": str(e)}


async def get_github_daily_data() -> dict[str, Any]:
    """Daily wrapper - yesterday's activity."""
    return await get_github_activity_data(mode="daily")


async def get_github_weekly_data() -> dict[str, Any]:
    """Weekly wrapper - last 7 days activity."""
    return await get_github_activity_data(mode="weekly")


# ---------------------------------------------------------------------------
# Subscription Monitor
# ---------------------------------------------------------------------------

async def get_subscription_monitor_data() -> dict[str, Any]:
    """Analyse subscriptions against bank transactions.

    Detects: price changes, missed payments, new recurring charges,
    upcoming renewals, and cancellation windows.
    """
    import re
    from collections import defaultdict
    from datetime import date

    try:
        from mcp_servers.financial_data.supabase_client import finance_query
    except ImportError:
        return {"error": "finance_query not available"}

    now = datetime.now(UK_TZ)
    today = date.today()
    alerts: list[dict] = []

    try:
        # 1. Fetch all subscriptions
        subs = await finance_query("subscriptions", {
            "select": "*",
            "order": "name.asc",
        }, paginate=True)

        active_subs = [s for s in subs if s.get("status") == "active"]

        # 2. Fetch last 6 months of outgoing transactions for analysis
        six_months_ago = (today - timedelta(days=180)).isoformat()
        all_txns = await finance_query("transactions", {
            "select": "description,amount,date",
            "amount": "lt.0",
            "date": f"gte.{six_months_ago}",
            "order": "date.desc",
        }, paginate=True)

        # 3. For each active sub with a bank pattern, find matching transactions
        tracked_patterns: list[str] = []
        for sub in active_subs:
            pattern = sub.get("bank_description_pattern")
            if not pattern:
                continue

            clean = pattern.replace("*", "").strip()
            if not clean:
                continue

            tracked_patterns.append(clean.lower())

            # Find matching transactions
            matching = [
                t for t in all_txns
                if clean.lower() in t.get("description", "").lower()
            ]

            if not matching:
                continue

            # --- Price change detection ---
            stored_amount = abs(float(sub["amount"]))
            latest_txn = matching[0]
            latest_amount = abs(float(latest_txn["amount"]))

            # Allow 10% tolerance for FX-converted amounts
            if stored_amount > 0 and abs(latest_amount - stored_amount) / stored_amount > 0.10:
                alerts.append({
                    "type": "price_change",
                    "subscription": sub["name"],
                    "scope": sub.get("scope", "personal"),
                    "old_amount": stored_amount,
                    "new_amount": latest_amount,
                    "last_transaction_date": latest_txn["date"],
                    "description": latest_txn["description"][:60],
                })

            # --- Missed payment detection ---
            freq = sub.get("frequency", "monthly")
            expected_gap_days = {
                "weekly": 10,
                "fortnightly": 20,
                "monthly": 45,
                "quarterly": 105,
                "termly": 140,
                "annual": 400,
            }.get(freq, 45)

            latest_date = date.fromisoformat(latest_txn["date"])
            days_since = (today - latest_date).days

            if days_since > expected_gap_days:
                alerts.append({
                    "type": "missed_payment",
                    "subscription": sub["name"],
                    "scope": sub.get("scope", "personal"),
                    "amount": stored_amount,
                    "frequency": freq,
                    "last_payment_date": latest_txn["date"],
                    "days_overdue": days_since - expected_gap_days,
                    "expected_by": (latest_date + timedelta(days=expected_gap_days)).isoformat(),
                })

        # 4. Cancellation window alerts
        for sub in active_subs:
            notice_days = sub.get("cancellation_notice_days")
            renewal_date = sub.get("next_renewal_date")
            if not notice_days or not renewal_date:
                continue

            renewal = date.fromisoformat(renewal_date)
            deadline = renewal - timedelta(days=notice_days)
            # Alert if within the cancellation window (deadline is in next 14 days)
            if today <= deadline <= today + timedelta(days=14):
                alerts.append({
                    "type": "cancellation_window",
                    "subscription": sub["name"],
                    "scope": sub.get("scope", "personal"),
                    "renewal_date": renewal_date,
                    "cancellation_deadline": deadline.isoformat(),
                    "amount": float(sub["amount"]),
                    "frequency": sub.get("frequency", "monthly"),
                })

        # 5. Upcoming renewals (next 7 days)
        upcoming = []
        for sub in active_subs:
            renewal_date = sub.get("next_renewal_date")
            if not renewal_date:
                continue
            renewal = date.fromisoformat(renewal_date)
            if today <= renewal <= today + timedelta(days=7):
                upcoming.append({
                    "name": sub["name"],
                    "renewal_date": renewal_date,
                    "amount": float(sub["amount"]),
                    "frequency": sub.get("frequency", "monthly"),
                    "scope": sub.get("scope", "personal"),
                })

        # 6. Detect new recurring transactions not yet tracked
        groups: dict[str, list[dict]] = defaultdict(list)
        for t in all_txns:
            desc = t.get("description", "").strip()
            norm = re.sub(r"\s+\d{2,}[/-]\d{2,}.*$", "", desc.lower()).strip()
            norm = re.sub(r"\s+", " ", norm)
            if norm:
                groups[norm].append(t)

        # Filter: 3+ occurrences, not already tracked, not MMBILL
        # Load user-dismissed exclusions
        exclusion_rows = await finance_query("subscription_exclusions", {
            "select": "description_pattern",
        })
        user_exclusions = [r["description_pattern"].lower() for r in exclusion_rows]

        # Exclude known non-subscription merchants
        _EXCLUDE = {
            "aldi", "tesco", "sainsbury", "lidl", "asda", "waitrose", "co-op",
            "morrisons", "marks and spencer", "m&s", "ocado",
            "pret a manger", "costa", "starbucks", "greggs", "mcdonalds",
            "nandos", "pizza", "burger", "kitchen", "restaurant", "cafe",
            "bar ", "pub ", "deli", "bakery", "chippy",
            "tfl travel", "ringgo", "parking", "petrol", "shell", "bp ",
            "amazon marketplace", "amazon.co.uk", "ebay", "paypal",
            "hsbc", "non-sterling", "transaction fee", "interest",
            "atm", "cash", "withdrawal",
            "stocks green prima", "burnhill", "next directory",
            "box bar", "se hildenborough", "accenture",
        }

        for desc, txs in groups.items():
            if len(txs) < 3:
                continue
            if "mmbill" in desc.lower() or "mmbil" in desc.lower():
                continue
            if any(excl in desc for excl in _EXCLUDE):
                continue
            if any(excl in desc for excl in user_exclusions):
                continue

            already_tracked = any(tp in desc for tp in tracked_patterns)
            if already_tracked:
                continue

            amounts = [abs(float(t["amount"])) for t in txs]
            avg = sum(amounts) / len(amounts)
            if avg < 2:
                continue

            # Subscription heuristic: consistent amounts (low CV)
            if len(amounts) >= 3:
                std_dev = (sum((a - avg) ** 2 for a in amounts) / len(amounts)) ** 0.5
                cv = std_dev / avg if avg > 0 else 1
                if cv > 0.20:
                    continue

            alerts.append({
                "type": "new_recurring",
                "description": txs[0].get("description", desc)[:60],
                "avg_amount": round(avg, 2),
                "occurrences": len(txs),
                "first_seen": txs[-1].get("date", ""),
                "latest": txs[0].get("date", ""),
            })

        # 7. Summary
        total_monthly = sum(
            _sub_monthly_cost(float(s["amount"]), s.get("frequency", "monthly"))
            for s in active_subs
        )

        return {
            "alerts": alerts,
            "upcoming_renewals": upcoming,
            "summary": {
                "total_active": len(active_subs),
                "total_monthly_cost": round(total_monthly, 2),
                "alerts_count": len(alerts),
                "scanned_transactions": len(all_txns),
            },
            "timestamp": now.strftime("%Y-%m-%d %H:%M"),
        }

    except Exception as e:
        logger.error(f"Subscription monitor data fetch error: {e}")
        return {"error": str(e)}


def _sub_monthly_cost(amount: float, frequency: str) -> float:
    """Convert any frequency to monthly cost."""
    multipliers = {
        "weekly": 52, "fortnightly": 26, "monthly": 12,
        "quarterly": 4, "termly": 3, "annual": 1,
    }
    return amount * multipliers.get(frequency, 12) / 12


async def get_tutor_email_data() -> dict[str, Any]:
    """Fetch the most recent tutor email for 11+ Mate tutor integration.

    Searches Gmail for emails from the tutor (last 7 days),
    fetches the full body, and returns it for Peter to parse.
    """
    import httpx

    # Catherine at 5by5 Tutoring
    queries = [
        'from:catherine@5by5tutoring.co.uk newer_than:7d',
    ]

    try:
        found_emails: list[dict] = []

        async with httpx.AsyncClient() as client:
            for query in queries:
                try:
                    response = await client.get(
                        f"{HADLEY_API_URL}/gmail/search",
                        params={"q": query, "limit": 5, "account": "personal"},
                        timeout=15,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        messages = data.get("emails", data.get("messages", []))
                        for msg in messages:
                            found_emails.append({
                                "id": msg.get("id", ""),
                                "subject": msg.get("subject", ""),
                                "from": msg.get("from", ""),
                                "date": msg.get("date", ""),
                                "snippet": msg.get("snippet", ""),
                            })
                except Exception as e:
                    logger.warning(f"Tutor email search error: {e}")

            if not found_emails:
                return {"no_tutor_email": True, "message": "No tutor emails found in the last 7 days"}

            # Deduplicate by ID
            seen_ids: set[str] = set()
            unique_emails: list[dict] = []
            for em in found_emails:
                if em["id"] not in seen_ids:
                    seen_ids.add(em["id"])
                    unique_emails.append(em)

            # Fetch full body for the most recent email
            most_recent = unique_emails[0]
            try:
                body_resp = await client.get(
                    f"{HADLEY_API_URL}/gmail/get",
                    params={"id": most_recent["id"], "account": "personal"},
                    timeout=15,
                )
                if body_resp.status_code == 200:
                    body_data = body_resp.json()
                    most_recent["body"] = body_data.get("body", body_data.get("text", ""))
                    most_recent["html_body"] = body_data.get("html_body", "")
            except Exception as e:
                logger.warning(f"Tutor email body fetch error: {e}")
                most_recent["body"] = most_recent.get("snippet", "")

            # Construct Gmail web link
            most_recent["gmail_link"] = f"https://mail.google.com/mail/u/0/#inbox/{most_recent['id']}"

            logger.info(f"Tutor email parser: found {len(unique_emails)} emails, fetched body for most recent")
            return {
                "email": most_recent,
                "all_emails": unique_emails,
                "count": len(unique_emails),
            }

    except Exception as e:
        logger.error(f"Tutor email fetch error: {e}")
        return {"error": str(e), "no_tutor_email": True}


async def get_paper_builder_data() -> dict[str, Any]:
    """Check this week's tutor topic and count existing papers per level.

    Returns the topic and paper gaps so the skill knows what to generate.
    """
    import httpx
    from pathlib import Path as WinPath

    anon_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1vZGpvaWt5dWhxem91eHZpZXVhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjYxNDE3MjksImV4cCI6MjA4MTcxNzcyOX0.EWGr0LOwFKFw3krrzZQZP_Gcew13s1Z9H3LxB0-JmPA"
    service_key = "psk_11plusmate_tutor_2026"
    emmie_id = "a5677d2f-9614-4504-94a2-4dae933af2c1"
    frontend_dir = WinPath(r"C:\Users\Chris Hadley\claude-projects\emmie-practice\frontend")

    try:
        # Get this week's tutor topic
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://modjoikyuhqzouxvieua.supabase.co/functions/v1/practice-schedule-manage",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {anon_key}",
                },
                json={
                    "action": "get-tutor-topics",
                    "service_key": service_key,
                    "family_code": "HADLEY",
                    "student_id": emmie_id,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

        topics = data.get("tutor_topics", [])
        if not topics:
            return {"no_topic": True, "message": "No tutor topics logged yet"}

        this_week = topics[0]  # Most recent
        topic_slug = this_week["topic"]
        subject = this_week.get("subject", "unknown")

        # Count existing papers per level for this topic
        levels = ["year4", "year5", "pretest", "actual-test"]
        paper_counts = {}
        for level in levels:
            # Count files matching {level}-{topic}*.html
            pattern = f"{level}-{topic_slug}*.html"
            existing = list(frontend_dir.glob(pattern))
            paper_counts[level] = len(existing)

        # Also count JSON data files
        data_dir = frontend_dir / "data"
        json_counts = {}
        for level in levels:
            pattern = f"{level}-{topic_slug}*.json"
            existing = list(data_dir.glob(pattern)) if data_dir.exists() else []
            json_counts[level] = len(existing)

        # Calculate gaps (need 3 per level)
        target = 3
        gaps = {}
        total_needed = 0
        for level in levels:
            have = paper_counts[level]
            need = max(0, target - have)
            gaps[level] = {"have": have, "need": need, "json_have": json_counts[level]}
            total_needed += need

        logger.info(f"Paper builder: topic={topic_slug}, gaps={gaps}, total_needed={total_needed}")
        return {
            "topic": topic_slug,
            "subject": subject,
            "topic_title": this_week.get("notes", "").split("|")[0].strip()[:100] if this_week.get("notes") else topic_slug,
            "paper_counts": paper_counts,
            "json_counts": json_counts,
            "gaps": gaps,
            "total_needed": total_needed,
            "frontend_dir": str(frontend_dir),
            "all_topics": [{"topic": t["topic"], "subject": t.get("subject"), "week_start": t["week_start"]} for t in topics[:4]],
        }

    except Exception as e:
        logger.error(f"Paper builder fetch error: {e}")
        return {"error": str(e)}


async def get_practice_allocate_data() -> dict[str, Any]:
    """Allocate 11+ Mate practice papers for the week for both students.

    Calls the allocate-practice Edge Function for each student for each day
    of the coming week (Wed-Tue cycle, starting tomorrow).
    """
    import httpx

    base_url = "https://modjoikyuhqzouxvieua.supabase.co/functions/v1/allocate-practice"
    service_key = "psk_11plusmate_tutor_2026"
    family_code = "HADLEY"
    anon_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1vZGpvaWt5dWhxem91eHZpZXVhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjYxNDE3MjksImV4cCI6MjA4MTcxNzcyOX0.EWGr0LOwFKFw3krrzZQZP_Gcew13s1Z9H3LxB0-JmPA"

    students = [
        {"id": "a5677d2f-9614-4504-94a2-4dae933af2c1", "name": "Emmie"},
        {"id": "2d204872-bfaa-4577-bd16-c07863b52cd1", "name": "Max"},
    ]

    now = datetime.now(UK_TZ)
    results = {}

    try:
        async with httpx.AsyncClient() as client:
            for student in students:
                student_results = []
                # Allocate for the next 7 days (tomorrow through 7 days out)
                for day_offset in range(1, 8):
                    target_date = (now + timedelta(days=day_offset)).strftime("%Y-%m-%d")
                    params = {
                        "service_key": service_key,
                        "family_code": family_code,
                        "student_id": student["id"],
                        "date_override": target_date,
                    }
                    resp = await client.get(
                        base_url,
                        params=params,
                        headers={"Authorization": f"Bearer {anon_key}"},
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        student_results.append({
                            "date": target_date,
                            "day_name": data.get("day_name", ""),
                            "allocations": data.get("allocations", []),
                        })
                    else:
                        student_results.append({
                            "date": target_date,
                            "error": f"HTTP {resp.status_code}: {resp.text[:100]}",
                        })

                results[student["name"]] = student_results

        logger.info(f"Practice allocation: allocated for {len(students)} students, 7 days each")
        return {"students": results, "week_start": (now + timedelta(days=1)).strftime("%Y-%m-%d")}

    except Exception as e:
        logger.error(f"Practice allocation fetch error: {e}")
        return {"error": str(e), "students": {}}


async def get_system_health_data() -> dict[str, Any]:
    """Fetch unified job health data from Hadley API.

    Returns combined DM + HB job execution stats for last 24 hours.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get("http://localhost:8100/jobs/health")
            if resp.status_code == 200:
                return {"system_health": resp.json()}
            else:
                logger.warning(f"System health fetch returned {resp.status_code}")
                return {"error": f"API returned {resp.status_code}"}
    except Exception as e:
        logger.error(f"System health fetch error: {e}")
        return {"error": str(e)}


async def get_orphan_embed_data() -> dict[str, Any]:
    """Find and embed orphaned Second Brain items (active but no chunks).

    Runs the full pipeline: fetch orphan IDs via RPC, chunk text, generate
    embeddings via HuggingFace, insert chunks. Returns summary for Peter.
    """
    import httpx
    from config import SUPABASE_URL, SUPABASE_KEY

    rest_url = f"{SUPABASE_URL}/rest/v1"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }

    try:
        # Step 1: Get orphan IDs via server-side RPC
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{rest_url}/rpc/get_orphaned_item_ids",
                headers=headers,
                json={},
            )
            resp.raise_for_status()
            orphan_ids = [row["id"] for row in resp.json()]

        if not orphan_ids:
            return {"orphan_count": 0, "embedded": 0, "skipped": 0, "summary": ""}

        # Step 2: Fetch item data in batches
        all_items = []
        for i in range(0, len(orphan_ids), 100):
            batch_ids = orphan_ids[i:i + 100]
            ids_filter = ",".join(f'"{uid}"' for uid in batch_ids)
            url = f"{rest_url}/knowledge_items?id=in.({ids_filter})&select=id,title,full_text,summary,content_type&order=created_at.asc"
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                all_items.extend(resp.json())

        # Step 3: Chunk + embed in batches of 20
        from domains.second_brain.chunk import chunk_text, chunk_for_embedding
        from domains.second_brain.embed import generate_embeddings_batch
        from domains.second_brain.db import create_knowledge_chunks

        total_embedded = 0
        total_skipped = 0
        BATCH_SIZE = 20

        for batch_start in range(0, len(all_items), BATCH_SIZE):
            batch = all_items[batch_start:batch_start + BATCH_SIZE]

            item_chunks = []
            all_embed_texts = []

            for item in batch:
                text = item.get("full_text") or item.get("summary") or ""
                if not text.strip():
                    total_skipped += 1
                    continue
                chunks = chunk_text(text)
                if not chunks:
                    total_skipped += 1
                    continue
                embed_texts = chunk_for_embedding(text, item.get("title"))
                item_chunks.append((item, chunks, len(embed_texts)))
                all_embed_texts.extend(embed_texts)

            if not all_embed_texts:
                continue

            embeddings = await generate_embeddings_batch(all_embed_texts)

            embed_idx = 0
            for item, chunks, n_embeds in item_chunks:
                chunk_embeddings = embeddings[embed_idx:embed_idx + n_embeds]
                embed_idx += n_embeds
                chunk_data = [
                    {
                        "index": i,
                        "text": chunk.text,
                        "embedding": emb,
                        "start_word": chunk.start_word,
                        "end_word": chunk.end_word,
                    }
                    for i, (chunk, emb) in enumerate(zip(chunks, chunk_embeddings))
                ]
                ok = await create_knowledge_chunks(item["id"], chunk_data)
                if ok:
                    total_embedded += 1
                else:
                    total_skipped += 1

        # Build type breakdown
        from collections import Counter
        type_counts = Counter(item.get("content_type", "unknown") for item in all_items)
        breakdown = ", ".join(f"{ct}: {n}" for ct, n in type_counts.most_common(5))

        return {
            "orphan_count": len(orphan_ids),
            "embedded": total_embedded,
            "skipped": total_skipped,
            "breakdown": breakdown,
            "summary": f"Embedded {total_embedded} orphaned items ({breakdown})"
                       + (f", {total_skipped} skipped (no text)" if total_skipped else ""),
        }

    except Exception as e:
        logger.error(f"Orphan embed failed: {e}")
        return {"error": str(e), "orphan_count": -1, "embedded": 0, "skipped": 0, "summary": f"Error: {e}"}


async def get_pocket_money_weekly_data() -> dict[str, Any]:
    """Fetch pocket money grid calculation from IHD dashboard.

    Calls the /api/kids/pocket-money/calculate endpoint to get the
    weekly grid summary with totals for each child.
    """
    import httpx

    IHD_BASE = "http://192.168.0.110:3000"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{IHD_BASE}/api/kids/pocket-money/calculate")
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.warning(f"Pocket money calculate returned {resp.status_code}")
                return {"error": f"API returned {resp.status_code}"}
    except Exception as e:
        logger.error(f"Pocket money data fetch error: {e}")
        return {"error": str(e)}


# ============================================================
# Life Admin Agent Data Fetchers
# ============================================================


async def get_life_admin_scan_data() -> dict[str, Any]:
    """Fetch alert and dashboard data for life-admin-scan skill."""
    try:
        alerts_result, dashboard_result = await asyncio.gather(
            _hadley_request("/life-admin/alerts"),
            _hadley_request("/life-admin/dashboard"),
            return_exceptions=True,
        )

        # Handle individual failures
        if isinstance(alerts_result, Exception):
            logger.warning(f"Life admin alerts fetch failed: {alerts_result}")
            alerts_result = {"error": str(alerts_result)}
        if isinstance(dashboard_result, Exception):
            logger.warning(f"Life admin dashboard fetch failed: {dashboard_result}")
            dashboard_result = {"error": str(dashboard_result)}

        now = datetime.now(UK_TZ)

        # Structure alerts by priority
        alerts_by_priority = {
            "overdue": [],
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
        }
        if isinstance(alerts_result, dict) and "error" not in alerts_result:
            for alert in alerts_result.get("alerts", []):
                priority = alert.get("alert_priority", "medium")
                if alert.get("overdue"):
                    alerts_by_priority["overdue"].append(alert)
                elif priority in alerts_by_priority:
                    alerts_by_priority[priority].append(alert)

        # Build summary from dashboard data
        summary = {}
        if isinstance(dashboard_result, dict) and "error" not in dashboard_result:
            summary = {
                "total_active": dashboard_result.get("total_active", 0),
                "due_this_week": dashboard_result.get("due_this_week", 0),
                "due_this_month": dashboard_result.get("due_this_month", 0),
                "overdue": dashboard_result.get("overdue", 0),
            }

        return {
            "alerts": alerts_by_priority,
            "summary": summary,
            "date": now.strftime("%Y-%m-%d"),
        }
    except Exception as e:
        logger.error(f"Life admin scan data fetch error: {e}")
        return {"error": str(e)}


async def get_life_admin_email_scan_data() -> dict[str, Any]:
    """Fetch Gmail emails and existing obligations for life-admin-email-scan skill."""
    try:
        # Run all Gmail searches and obligation fetch in parallel
        (
            insurance_result,
            dvla_result,
            mot_result,
            council_result,
            utility_result,
            passport_result,
            domain_result,
            school_result,
            warranty_result,
            obligations_result,
        ) = await asyncio.gather(
            _hadley_request("/gmail/search?q=subject:(renewal OR premium OR policy) newer_than:2d&max_results=10"),
            _hadley_request("/gmail/search?q=from:dvla newer_than:7d&max_results=5"),
            _hadley_request("/gmail/search?q=subject:(MOT OR service OR booking) from:(garage OR halfords OR kwik-fit) newer_than:7d&max_results=5"),
            _hadley_request("/gmail/search?q=from:(council OR .gov.uk) subject:(council tax OR bill) newer_than:7d&max_results=5"),
            _hadley_request("/gmail/search?q=subject:(bill OR statement OR renewal) from:(british gas OR octopus OR bulb OR sky OR bt) newer_than:2d&max_results=10"),
            _hadley_request("/gmail/search?q=from:hmpo subject:passport newer_than:30d&max_results=3"),
            _hadley_request("/gmail/search?q=subject:(domain renewal OR domain expir) newer_than:7d&max_results=5"),
            _hadley_request("/gmail/search?q=from:(school OR parentpay) subject:(payment OR meal OR trip) newer_than:2d&max_results=5"),
            _hadley_request("/gmail/search?q=subject:(warranty OR guarantee OR registration) newer_than:7d&max_results=5"),
            _hadley_request("/life-admin/obligations"),
            return_exceptions=True,
        )

        now = datetime.now(UK_TZ)

        # Build email results dict, handling individual failures
        email_categories = {
            "insurance": insurance_result,
            "dvla": dvla_result,
            "mot_service": mot_result,
            "council": council_result,
            "utility": utility_result,
            "passport": passport_result,
            "domain": domain_result,
            "school": school_result,
            "warranty": warranty_result,
        }

        email_results = {}
        for category, result in email_categories.items():
            if isinstance(result, Exception):
                logger.warning(f"Life admin email scan '{category}' failed: {result}")
                email_results[category] = []
            elif isinstance(result, dict) and "error" in result:
                logger.warning(f"Life admin email scan '{category}' error: {result['error']}")
                email_results[category] = []
            else:
                email_results[category] = result.get("emails", result) if isinstance(result, dict) else result

        # Handle obligations result
        existing_obligations = []
        if isinstance(obligations_result, Exception):
            logger.warning(f"Life admin obligations fetch failed: {obligations_result}")
        elif isinstance(obligations_result, dict) and "error" not in obligations_result:
            existing_obligations = obligations_result.get("obligations", obligations_result)

        return {
            "email_results": email_results,
            "existing_obligations": existing_obligations,
            "scan_timestamp": now.strftime("%Y-%m-%d %H:%M"),
        }
    except Exception as e:
        logger.error(f"Life admin email scan data fetch error: {e}")
        return {"error": str(e)}


async def get_life_admin_compare_data() -> dict[str, Any]:
    """Fetch all active obligations for life-admin-compare conversational skill."""
    try:
        obligations_result = await _hadley_request("/life-admin/obligations")

        now = datetime.now(UK_TZ)

        obligations = []
        if isinstance(obligations_result, dict) and "error" not in obligations_result:
            obligations = obligations_result.get("obligations", obligations_result)

        return {
            "obligations": obligations,
            "date": now.strftime("%Y-%m-%d"),
        }
    except Exception as e:
        logger.error(f"Life admin compare data fetch error: {e}")
        return {"error": str(e)}


async def get_life_admin_dashboard_data() -> dict[str, Any]:
    """Fetch dashboard and scan history for life-admin-dashboard weekly skill."""
    try:
        dashboard_result, scans_result = await asyncio.gather(
            _hadley_request("/life-admin/dashboard"),
            _hadley_request("/life-admin/scans?limit=7"),
            return_exceptions=True,
        )

        now = datetime.now(UK_TZ)

        # Handle individual failures
        dashboard = {}
        if isinstance(dashboard_result, Exception):
            logger.warning(f"Life admin dashboard fetch failed: {dashboard_result}")
        elif isinstance(dashboard_result, dict) and "error" not in dashboard_result:
            dashboard = dashboard_result

        recent_scans = []
        if isinstance(scans_result, Exception):
            logger.warning(f"Life admin scans fetch failed: {scans_result}")
        elif isinstance(scans_result, dict) and "error" not in scans_result:
            recent_scans = scans_result.get("scans", scans_result)

        return {
            "dashboard": dashboard,
            "recent_scans": recent_scans,
            "date": now.strftime("%Y-%m-%d"),
        }
    except Exception as e:
        logger.error(f"Life admin dashboard data fetch error: {e}")
        return {"error": str(e)}


async def get_commitment_nudge_data() -> dict[str, Any]:
    """Fetch open commitments for the daily nudge skill."""
    try:
        from domains.commitments import get_open_commitments

        # Get commitments older than 4 hours (give Chris time to follow through)
        open_items = await get_open_commitments(min_age_hours=4, limit=10)

        # Filter out items nudged today already
        now = datetime.now(ZoneInfo("Europe/London"))
        filtered = []
        for item in open_items:
            last_nudged = item.get("last_nudged_at")
            if last_nudged:
                from datetime import datetime as dt
                nudged_dt = dt.fromisoformat(last_nudged.replace("Z", "+00:00"))
                if (now - nudged_dt).total_seconds() < 18 * 3600:  # Don't re-nudge within 18h
                    continue
            # Calculate age in hours
            detected = dt.fromisoformat(item["detected_at"].replace("Z", "+00:00"))
            item["age_hours"] = round((now - detected).total_seconds() / 3600)
            filtered.append(item)

        # Count today's resolved/dismissed for context
        resolved_today = 0
        dismissed_today = 0

        return {
            "open_commitments": filtered[:5],  # Cap at 5 for the nudge
            "count": len(filtered),
            "total_open": len(open_items),
            "resolved_today": resolved_today,
            "dismissed_today": dismissed_today,
        }
    except Exception as e:
        logger.error(f"Commitment nudge data fetch error: {e}")
        return {"error": str(e)}


async def get_flight_prices_data() -> dict[str, Any]:
    """Fetch flight price data for flight-prices skill.

    Runs a quick check on the cheapest dates found so far,
    plus scans new date pairs if budget allows.
    """
    try:
        from services.flight_prices import FlightPriceMonitor

        monitor = FlightPriceMonitor()

        if not monitor.api_key:
            return {"error": "SERPAPI_KEY not set", "__skip__": True, "reason": "No API key configured"}

        # Run a scan of the next 3 cheapest weekend departures (uses 3 API calls)
        from services.flight_prices import generate_date_pairs
        pairs = generate_date_pairs("weekends", window_days=180, trip_lengths=[10, 14])

        # Pick a sample: next 3 upcoming departure dates (6 calls total — 3 dates x 2 trip lengths)
        # Group by outbound date, take first 3 unique dates
        seen_dates = set()
        sample_pairs = []
        for out, ret in pairs:
            if out not in seen_dates and len(seen_dates) < 3:
                seen_dates.add(out)
            if out in seen_dates:
                sample_pairs.append((out, ret))

        results = await monitor.check_all_routes(date_pairs=sample_pairs)

        # Get overall cheapest from DB
        cheapest = monitor.get_cheapest(days_back=30, limit=5)
        deals = monitor.detect_deals()
        summary = monitor.get_summary(days_back=7)

        return {
            "scan_results": {
                label: {
                    "results": [
                        {
                            "outbound": r["outbound"],
                            "return": r["return"],
                            "price_pp": r["cheapest"]["price_pp"],
                            "price_total": r["cheapest"]["price_total"],
                            "airline": r["cheapest"]["airline"],
                            "duration_min": r["cheapest"]["duration_min"],
                            "insights": r["insights"],
                        }
                        for r in data["results"]
                    ]
                }
                for label, data in results.items()
            },
            "cheapest_overall": [
                {
                    "label": c["label"],
                    "outbound": c["outbound_date"],
                    "return": c["return_date"],
                    "price_pp": c["price_pp"],
                    "price_total": c["price_total"],
                    "airline": c["airline"],
                }
                for c in cheapest
            ],
            "deals": [
                {
                    "label": d["label"],
                    "outbound": d["outbound_date"],
                    "price_pp": d["price_pp"],
                    "deal_type": d.get("deal_type"),
                    "drop_pct": d.get("drop_pct"),
                }
                for d in deals
            ],
            "summary": summary,
            "timestamp": datetime.now(UK_TZ).isoformat(),
        }

    except Exception as e:
        logger.error(f"Flight prices data fetch error: {e}")
        return {"error": str(e)}


async def get_accountability_weekly_data() -> dict[str, Any]:
    """Fetch accountability data for weekly report.

    Runs auto-updates first, then generates weekly report data.
    """
    try:
        from domains.accountability.auto_sources import run_auto_updates
        from domains.accountability.service import get_report_data

        await run_auto_updates()
        return await get_report_data(period="week")

    except Exception as e:
        logger.error(f"Accountability weekly data fetch error: {e}")
        return {"error": str(e)}


async def get_accountability_monthly_data() -> dict[str, Any]:
    """Fetch accountability data for monthly report.

    Runs auto-updates first, then generates monthly report data.
    """
    try:
        from domains.accountability.auto_sources import run_auto_updates
        from domains.accountability.service import get_report_data

        await run_auto_updates()
        return await get_report_data(period="month")

    except Exception as e:
        logger.error(f"Accountability monthly data fetch error: {e}")
        return {"error": str(e)}


async def get_fitness_advisor_data() -> dict[str, Any]:
    """Pre-fetch fitness advisor data for the proactive advisor skill."""
    try:
        from domains.fitness.advisor import get_advice
        return await get_advice()
    except Exception as e:
        logger.error(f"Fitness advisor data fetch error: {e}")
        return {"error": str(e)}


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
    "whatsapp-health": get_whatsapp_health_data,
    "football-scores": get_football_scores_data,
    "pl-results": get_pl_results_data,
    "spurs-live": get_spurs_live_data,
    "spurs-matchday": get_spurs_matchday_data,
    "cricket-scores": get_cricket_scores_data,
    "saturday-sport-preview": get_saturday_sport_preview_data,
    "ballot-reminders": get_ballot_reminders_data,
    # Meal plan
    "meal-plan": get_meal_plan_data,
    "meal-plan-generator": get_meal_plan_generator_data,
    "meal-rating": get_meal_rating_data,
    "grocery-shop": get_grocery_shop_data,
    "recipe-discovery": get_recipe_discovery_data,
    "price-scanner": get_price_scanner_data,
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
    # School - spellings + events
    "school-weekly-spellings": get_school_data,
    # GitHub activity
    "github-activity": get_github_daily_data,
    "github-weekly": get_github_weekly_data,
    # Subscriptions
    "subscription-monitor": get_subscription_monitor_data,
    # Amazon purchases
    "amazon-purchases": get_amazon_purchases_data,
    # Cooking reminders
    "cooking-reminder": get_cooking_reminder_data,
    # 11+ Mate
    "tutor-email-parser": get_tutor_email_data,
    "paper-builder": get_paper_builder_data,
    "practice-allocate": get_practice_allocate_data,
    # System health monitoring
    "system-health": get_system_health_data,
    # Pocket money weekly
    "pocket-money-weekly": get_pocket_money_weekly_data,
    # Second Brain orphan embedding
    "orphan-embed": get_orphan_embed_data,
    # Life Admin
    "life-admin-scan": get_life_admin_scan_data,
    "life-admin-email-scan": get_life_admin_email_scan_data,
    "life-admin-compare": get_life_admin_compare_data,
    "life-admin-dashboard": get_life_admin_dashboard_data,
    # Commitment Nudge
    "commitment-nudge": get_commitment_nudge_data,
    # Flight prices
    "flight-prices": get_flight_prices_data,
    # Accountability Tracker
    "accountability-weekly": get_accountability_weekly_data,
    "accountability-monthly": get_accountability_monthly_data,
    # Fitness advisor
    "fitness-advisor": get_fitness_advisor_data,
}
