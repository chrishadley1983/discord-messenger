"""Nutrition Morning Motivation scheduled job.

Posts daily at 7:00 AM UK time to #food-log channel with:
- Motivational message tied to goal
- Days remaining to deadline
- Yesterday's summary if available
- Today's focus advice
"""

import random
from datetime import datetime, timedelta

import httpx

from config import SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY
from logger import logger

# Channel ID for #food-log
FOOD_LOG_CHANNEL_ID = 1465294449038069912


def _get_headers():
    """Get headers for Supabase API calls."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }


async def _get_goals() -> dict:
    """Get current user goals."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/user_goals",
                headers=_get_headers(),
                params={"user_id": "eq.chris", "limit": "1"},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

        if data:
            goals = data[0]
            deadline = datetime.strptime(goals["deadline"], "%Y-%m-%d").date()
            days_remaining = (deadline - datetime.now().date()).days
            return {
                "target_weight_kg": float(goals["target_weight_kg"]),
                "deadline": goals["deadline"],
                "goal_reason": goals["goal_reason"],
                "days_remaining": days_remaining,
                "calories": goals["calories_target"],
                "protein_g": goals["protein_target_g"]
            }
        return {}
    except Exception as e:
        logger.error(f"Failed to get goals: {e}")
        return {}


async def _get_yesterday_summary() -> dict:
    """Get yesterday's nutrition totals."""
    try:
        yesterday = (datetime.now() - timedelta(days=1)).date().isoformat()
        today = datetime.now().date().isoformat()

        # PostgREST: use proper 'and' filter syntax for multiple conditions
        filter_str = f"and=(logged_at.gte.{yesterday}T00:00:00,logged_at.lt.{today}T00:00:00)"
        url = f"{SUPABASE_URL}/rest/v1/nutrition_logs?select=calories,protein_g,carbs_g,fat_g,water_ml&{filter_str}"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers=_get_headers(),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

        if data:
            return {
                "calories": sum(r["calories"] or 0 for r in data),
                "protein_g": sum(r["protein_g"] or 0 for r in data),
                "carbs_g": sum(r["carbs_g"] or 0 for r in data),
                "fat_g": sum(r["fat_g"] or 0 for r in data),
                "water_ml": sum(r["water_ml"] or 0 for r in data),
            }
        return {}
    except Exception as e:
        logger.error(f"Failed to get yesterday summary: {e}")
        return {}


async def _get_garmin_data() -> dict:
    """Get Garmin health metrics (steps, sleep, HR)."""
    try:
        from domains.nutrition.services import get_daily_summary
        return await get_daily_summary()
    except Exception as e:
        logger.error(f"Failed to get Garmin data: {e}")
        return {}


async def _get_steps_trend() -> dict:
    """Get step history for trend analysis from garmin_daily_summary."""
    try:
        # Get last 14 days of step data
        start_date = (datetime.now() - timedelta(days=14)).date().isoformat()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/garmin_daily_summary",
                headers=_get_headers(),
                params={
                    "select": "date,steps,steps_goal",
                    "user_id": "eq.chris",
                    "date": f"gte.{start_date}",
                    "order": "date.desc",
                    "limit": "14"
                },
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Steps trend query failed: {response.status_code} - {response.text}")
                return {}

            data = response.json()

        logger.info(f"Steps history fetched: {len(data)} days")

        if not data:
            return {}

        result = {}

        # Calculate 7-day average (exclude today as it's incomplete)
        recent_days = [d for d in data if d["steps"] and d["date"] != datetime.now().date().isoformat()][:7]
        if recent_days:
            avg = sum(d["steps"] for d in recent_days) / len(recent_days)
            result["week_avg"] = int(avg)
            logger.info(f"Steps 7d avg: {result['week_avg']} from {len(recent_days)} days")

        # Calculate hit rate (days that hit goal in last 7)
        if len(recent_days) >= 3:
            goal = recent_days[0].get("steps_goal", 15000)
            hits = sum(1 for d in recent_days if d["steps"] >= goal)
            result["hit_rate"] = f"{hits}/{len(recent_days)}"
            logger.info(f"Steps hit rate: {result['hit_rate']}")

        # Weekly trend (this week vs last week)
        this_week = recent_days[:7]
        last_week_data = [d for d in data if d["steps"]][7:14]
        if this_week and last_week_data:
            this_avg = sum(d["steps"] for d in this_week) / len(this_week)
            last_avg = sum(d["steps"] for d in last_week_data) / len(last_week_data)
            result["weekly_trend"] = int(this_avg - last_avg)
            logger.info(f"Steps weekly trend: {result['weekly_trend']}")

        return result

    except Exception as e:
        logger.error(f"Failed to get steps trend: {e}")
        return {}


def _judge_sleep(hours: float, score: int | None) -> tuple[str, str]:
    """Return emoji and judgement for sleep quality."""
    if hours is None:
        return "❓", "No data"

    if score and score >= 80:
        return "🟢", "Excellent recovery"
    elif score and score >= 60:
        return "🟡", "Decent rest"
    elif score:
        return "🔴", "Poor recovery - take it easy"

    # Fallback to hours only
    if hours >= 7.5:
        return "🟢", "Solid sleep"
    elif hours >= 6:
        return "🟡", "Could use more"
    else:
        return "🔴", "Sleep debt - prioritise rest"


def _judge_resting_hr(hr: int | None) -> tuple[str, str]:
    """Return emoji and judgement for resting heart rate."""
    if hr is None:
        return "❓", ""

    if hr <= 55:
        return "🟢", "Great cardiovascular health"
    elif hr <= 65:
        return "🟢", "Healthy"
    elif hr <= 75:
        return "🟡", "Normal"
    else:
        return "🔴", "Elevated - stress or fatigue?"


def _judge_steps(steps: int, goal: int) -> tuple[str, str]:
    """Return emoji and judgement for steps (as of morning)."""
    # Morning check - can't judge yet, just show target
    pct = (steps / goal * 100) if goal else 0
    if pct >= 30:  # Already 30% by morning is good
        return "🟢", "Strong start"
    else:
        return "⬜", f"Target: {goal:,}"


async def _get_weight_trend() -> dict:
    """Get recent weight readings for trend analysis."""
    try:
        # Get last 14 days of weight readings for better trend
        start_date = (datetime.now() - timedelta(days=14)).isoformat()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/weight_readings",
                headers=_get_headers(),
                params={
                    "select": "weight_kg,measured_at",
                    "user_id": "eq.chris",
                    "measured_at": f"gte.{start_date}",
                    "order": "measured_at.desc",
                    "limit": "20"
                },
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Weight query failed: {response.status_code} - {response.text}")
                return {}

            data = response.json()

        logger.info(f"Weight readings fetched: {len(data)} records")
        if data:
            logger.info(f"Latest reading: {data[0]}")

        if not data:
            return {}

        latest = float(data[0]["weight_kg"])
        result = {
            "current_kg": latest,
            "date": data[0]["measured_at"]
        }

        # Calculate change from previous reading (daily change)
        if len(data) >= 2:
            previous = float(data[1]["weight_kg"])
            change = round(latest - previous, 1)
            result["change_from_last"] = change
            logger.info(f"Weight change from last: {change}kg (current: {latest}, previous: {previous})")

        # Calculate 7-day average (use up to 7 most recent readings)
        recent_readings = data[:7] if len(data) >= 7 else data
        if len(recent_readings) >= 2:
            avg = sum(float(r["weight_kg"]) for r in recent_readings) / len(recent_readings)
            result["week_avg"] = round(avg, 1)
            logger.info(f"7-day avg: {result['week_avg']}kg from {len(recent_readings)} readings")

        # Calculate weekly trend (compare this week avg to last week avg)
        if len(data) >= 7:
            this_week = data[:7]
            last_week = data[7:14] if len(data) >= 14 else []
            if last_week:
                this_week_avg = sum(float(r["weight_kg"]) for r in this_week) / len(this_week)
                last_week_avg = sum(float(r["weight_kg"]) for r in last_week) / len(last_week)
                result["weekly_trend"] = round(this_week_avg - last_week_avg, 1)
                logger.info(f"Weekly trend: {result['weekly_trend']}kg")

        return result

    except Exception as e:
        logger.error(f"Failed to get weight trend: {e}")
        return {}


async def _generate_motivation(goals: dict, yesterday: dict) -> str:
    """Generate motivational message using Claude Haiku (cost-effective)."""
    try:
        if not ANTHROPIC_API_KEY:
            return _get_fallback_motivation(goals)

        prompt = f"""Generate a brief, punchy morning motivation message (2-3 sentences max) for Chris.

Context:
- Goal: {goals.get('target_weight_kg', 80)}kg by {goals.get('deadline', 'April 2026')}
- Reason: {goals.get('goal_reason', 'Family trip to Japan')}
- Days remaining: {goals.get('days_remaining', 'unknown')}
- Yesterday's protein: {yesterday.get('protein_g', 'not tracked')}g (target: {goals.get('protein_g', 160)}g)
- Yesterday's calories: {yesterday.get('calories', 'not tracked')} (target: {goals.get('calories', 2100)})

Style:
- Direct, PT-style motivation
- Reference the Japan goal occasionally
- Call out wins or gaps from yesterday
- End with today's focus (usually protein)
- NO emoji overload, maybe 1-2 max
- NO "Good morning!" fluff"""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 200,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                message = data["content"][0]["text"]
                logger.info(f"Haiku motivation generated ({len(message)} chars)")
                return message
            else:
                logger.warning(f"Haiku API returned {response.status_code}")
                return _get_fallback_motivation(goals)

    except Exception as e:
        logger.error(f"Haiku motivation error: {e}")
        return _get_fallback_motivation(goals)


def _get_fallback_motivation(goals: dict) -> str:
    """Fallback motivations if Claude fails."""
    days = goals.get('days_remaining', 100)
    reason = goals.get('goal_reason', 'your goal')

    motivations = [
        f"**{days} days to Japan.** Every meal counts. Protein first, excuses never.",
        f"New day, same mission. {days} days left. Make today's choices match your goal.",
        f"**{days} days.** Hit your protein, hit your steps, get closer to {reason}.",
        f"Yesterday's done. Today's opportunity. {days} days - let's make them count.",
        f"You didn't come this far to only come this far. {days} days to show up for yourself.",
    ]
    return random.choice(motivations)


async def nutrition_morning_message(bot):
    """Post the nutrition morning motivation."""
    channel = bot.get_channel(FOOD_LOG_CHANNEL_ID)
    if not channel:
        logger.error(f"Could not find food-log channel {FOOD_LOG_CHANNEL_ID}")
        return

    try:
        # Gather data
        goals = await _get_goals()
        yesterday = await _get_yesterday_summary()
        weight = await _get_weight_trend()
        garmin = await _get_garmin_data()
        steps_trend = await _get_steps_trend()

        # Generate motivation
        motivation = await _generate_motivation(goals, yesterday)

        # Build message
        today = datetime.now()
        day_name = today.strftime("%A")

        lines = [
            f"**☀️ {day_name} Morning**",
            "",
            motivation,
            ""
        ]

        # Health metrics section
        lines.append("**📊 Health Check**")

        # Weight update with daily change, target, and trend
        if weight.get("current_kg"):
            target = goals.get("target_weight_kg", 80)
            current = weight["current_kg"]
            to_go = round(current - target, 1)

            # Build weight line: current weight
            weight_line = f"⚖️ **{current}kg**"

            # Add daily change (even if 0)
            if "change_from_last" in weight:
                change = weight["change_from_last"]
                if change < 0:
                    weight_line += f" (↓{abs(change)}kg)"
                elif change > 0:
                    weight_line += f" (↑+{change}kg)"
                else:
                    weight_line += " (→ no change)"

            # Add distance to goal
            weight_line += f" | {to_go}kg to go"
            lines.append(weight_line)

            # Second line: 7-day average and weekly trend
            trend_parts = []
            if weight.get("week_avg"):
                trend_parts.append(f"7d avg: {weight['week_avg']}kg")
            if weight.get("weekly_trend"):
                wt = weight["weekly_trend"]
                if wt < 0:
                    trend_parts.append(f"weekly: ↓{abs(wt)}kg")
                elif wt > 0:
                    trend_parts.append(f"weekly: ↑+{wt}kg")
            if trend_parts:
                lines.append(f"   📈 {' | '.join(trend_parts)}")

        # Sleep
        sleep = garmin.get("sleep", {})
        if sleep.get("total_hours"):
            sleep_emoji, sleep_judge = _judge_sleep(sleep["total_hours"], sleep.get("quality_score"))
            sleep_line = f"😴 **{sleep['total_hours']}h sleep**"
            if sleep.get("quality_score"):
                sleep_line += f" (score: {sleep['quality_score']})"
            sleep_line += f" {sleep_emoji} {sleep_judge}"
            lines.append(sleep_line)

        # Resting HR
        hr = garmin.get("heart_rate", {})
        if hr.get("resting"):
            hr_emoji, hr_judge = _judge_resting_hr(hr["resting"])
            lines.append(f"❤️ **{hr['resting']} bpm** resting HR {hr_emoji} {hr_judge}")

        # Steps (morning snapshot with trend)
        steps = garmin.get("steps", {})
        if steps.get("count") is not None:
            step_emoji, step_judge = _judge_steps(steps["count"], steps.get("goal", 15000))
            lines.append(f"🚶 {steps['count']:,} steps so far {step_emoji} {step_judge}")

            # Add step trend line
            step_trend_parts = []
            if steps_trend.get("week_avg"):
                step_trend_parts.append(f"7d avg: {steps_trend['week_avg']:,}")
            if steps_trend.get("hit_rate"):
                step_trend_parts.append(f"hit rate: {steps_trend['hit_rate']} days")
            if steps_trend.get("weekly_trend"):
                wt = steps_trend["weekly_trend"]
                if wt > 0:
                    step_trend_parts.append(f"weekly: ↑+{wt:,}")
                elif wt < 0:
                    step_trend_parts.append(f"weekly: ↓{abs(wt):,}")
            if step_trend_parts:
                lines.append(f"   📈 {' | '.join(step_trend_parts)}")

        lines.append("")  # Blank line before nutrition

        # Yesterday's full nutrition summary
        if yesterday:
            cals = yesterday.get('calories', 0)
            protein = yesterday.get('protein_g', 0)
            carbs = yesterday.get('carbs_g', 0)
            fat = yesterday.get('fat_g', 0)
            water = yesterday.get('water_ml', 0)

            target_cals = goals.get('calories', 2100)
            target_protein = goals.get('protein_g', 160)

            protein_hit = protein >= target_protein * 0.9
            cals_ok = cals <= target_cals * 1.1

            # Status emoji based on performance
            if protein_hit and cals_ok:
                status = "✅"
                verdict = "solid day"
            elif not protein_hit:
                status = "⚠️"
                verdict = f"protein gap ({target_protein - protein:.0f}g short)"
            elif cals > target_cals * 1.1:
                status = "⚠️"
                verdict = f"over calories (+{cals - target_cals:.0f})"
            else:
                status = "📊"
                verdict = ""

            lines.append(f"**🍽️ Yesterday's Macros** {status}")
            lines.append(f"   {cals:.0f} cal | P: {protein:.0f}g | C: {carbs:.0f}g | F: {fat:.0f}g")
            lines.append(f"   💧 {water:.0f}ml water")
            if verdict:
                lines.append(f"   → {verdict}")

        # Days countdown
        if goals.get('days_remaining'):
            lines.append(f"📅 **{goals['days_remaining']} days** until {goals.get('goal_reason', 'your goal')}")

        message = "\n".join(lines)
        await channel.send(message)
        logger.info("Posted nutrition morning motivation")

    except Exception as e:
        logger.error(f"Failed to post nutrition morning message: {e}")


def register_nutrition_morning(scheduler, bot):
    """Register the nutrition morning message job with the scheduler."""
    scheduler.add_job(
        nutrition_morning_message,
        'cron',
        args=[bot],
        hour=8,
        minute=0,
        timezone="Europe/London",
        id="nutrition_morning_message"
    )
    logger.info("Registered nutrition morning message job (8:00 AM UK)")
