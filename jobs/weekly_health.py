"""Weekly Health Summary scheduled job.

Schedule:
- Every Sunday at 9:00 AM (Europe/London)

Posts to Discord #food-log with:
- Weight trend for the week
- Nutrition averages
- Activity/steps summary
- Sleep quality
- Heart rate trends
- Overall PT grade
- Visual graphs (weight, nutrition, steps)
"""

import io
from datetime import datetime, timedelta

import discord
import httpx
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from config import SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY
from logger import logger

# Discord channel for weekly health summary
WEEKLY_HEALTH_CHANNEL_ID = 1465294449038069912  # #food-log


def _get_headers() -> dict:
    """Get Supabase API headers."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }


async def _get_weight_week() -> dict:
    """Get weight data for the past week."""
    try:
        start_date = (datetime.now() - timedelta(days=7)).isoformat()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/weight_readings",
                headers=_get_headers(),
                params={
                    "select": "weight_kg,measured_at",
                    "user_id": "eq.chris",
                    "measured_at": f"gte.{start_date}",
                    "order": "measured_at.asc"
                },
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Weight query failed: {response.status_code}")
                return {}

            data = response.json()

        if not data:
            return {}

        weights = [float(r["weight_kg"]) for r in data]
        dates = [datetime.fromisoformat(r["measured_at"].replace("Z", "+00:00")) for r in data]
        return {
            "start": weights[0] if weights else None,
            "end": weights[-1] if weights else None,
            "change": round(weights[-1] - weights[0], 1) if len(weights) >= 2 else 0,
            "min": min(weights) if weights else None,
            "max": max(weights) if weights else None,
            "avg": round(sum(weights) / len(weights), 1) if weights else None,
            "readings": len(weights),
            "raw_weights": weights,
            "raw_dates": dates
        }
    except Exception as e:
        logger.error(f"Failed to get weight week: {e}")
        return {}


async def _get_nutrition_week() -> dict:
    """Get nutrition averages for the past week."""
    try:
        start_date = (datetime.now() - timedelta(days=7)).date().isoformat()
        end_date = datetime.now().date().isoformat()

        filter_str = f"and=(logged_at.gte.{start_date}T00:00:00,logged_at.lt.{end_date}T00:00:00)"
        url = f"{SUPABASE_URL}/rest/v1/nutrition_logs?select=calories,protein_g,carbs_g,fat_g,water_ml,logged_at&{filter_str}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=_get_headers(), timeout=30)

            if response.status_code != 200:
                logger.error(f"Nutrition query failed: {response.status_code}")
                return {}

            data = response.json()

        if not data:
            return {}

        # Group by day
        daily = {}
        for r in data:
            day = r["logged_at"][:10]
            if day not in daily:
                daily[day] = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "water": 0}
            daily[day]["calories"] += r["calories"] or 0
            daily[day]["protein"] += r["protein_g"] or 0
            daily[day]["carbs"] += r["carbs_g"] or 0
            daily[day]["fat"] += r["fat_g"] or 0
            daily[day]["water"] += r["water_ml"] or 0

        days = len(daily)
        if days == 0:
            return {}

        # Sort by date for graph
        sorted_days = sorted(daily.keys())
        raw_dates = [datetime.strptime(d, "%Y-%m-%d") for d in sorted_days]
        raw_calories = [daily[d]["calories"] for d in sorted_days]
        raw_protein = [daily[d]["protein"] for d in sorted_days]

        return {
            "days_tracked": days,
            "avg_calories": round(sum(d["calories"] for d in daily.values()) / days),
            "avg_protein": round(sum(d["protein"] for d in daily.values()) / days),
            "avg_carbs": round(sum(d["carbs"] for d in daily.values()) / days),
            "avg_fat": round(sum(d["fat"] for d in daily.values()) / days),
            "avg_water": round(sum(d["water"] for d in daily.values()) / days),
            "protein_days_hit": sum(1 for d in daily.values() if d["protein"] >= 144),  # 90% of 160g target
            "raw_dates": raw_dates,
            "raw_calories": raw_calories,
            "raw_protein": raw_protein
        }
    except Exception as e:
        logger.error(f"Failed to get nutrition week: {e}")
        return {}


async def _get_steps_week() -> dict:
    """Get steps data for the past 7 days (excluding today)."""
    try:
        # 7 days ago to yesterday (exclude today as it's incomplete)
        end_date = datetime.now().date().isoformat()
        start_date = (datetime.now() - timedelta(days=7)).date().isoformat()

        filter_str = f"and=(date.gte.{start_date},date.lt.{end_date})"
        url = f"{SUPABASE_URL}/rest/v1/garmin_daily_summary?select=date,steps,steps_goal&user_id=eq.chris&{filter_str}&order=date.asc"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=_get_headers(), timeout=30)

            if response.status_code != 200:
                logger.error(f"Steps query failed: {response.status_code}")
                return {}

            data = response.json()

        if not data:
            return {}

        steps = [d["steps"] for d in data if d["steps"]]
        dates = [datetime.strptime(d["date"], "%Y-%m-%d") for d in data if d["steps"]]
        goal = data[0].get("steps_goal", 15000) if data else 15000

        return {
            "total": sum(steps),
            "avg": round(sum(steps) / len(steps)) if steps else 0,
            "days": len(steps),
            "days_hit_goal": sum(1 for s in steps if s >= goal),
            "best_day": max(steps) if steps else 0,
            "goal": goal,
            "raw_steps": steps,
            "raw_dates": dates
        }
    except Exception as e:
        logger.error(f"Failed to get steps week: {e}")
        return {}


async def _get_sleep_week() -> dict:
    """Get sleep data for the past week from Garmin."""
    try:
        start_date = (datetime.now() - timedelta(days=7)).date().isoformat()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/garmin_daily_summary",
                headers=_get_headers(),
                params={
                    "select": "date,sleep_hours,sleep_score",
                    "user_id": "eq.chris",
                    "date": f"gte.{start_date}",
                    "order": "date.asc"
                },
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Sleep query failed: {response.status_code}")
                return {}

            data = response.json()

        if not data:
            return {}

        sleep_hours = [d["sleep_hours"] for d in data if d.get("sleep_hours")]
        sleep_scores = [d["sleep_score"] for d in data if d.get("sleep_score")]

        return {
            "avg_hours": round(sum(sleep_hours) / len(sleep_hours), 1) if sleep_hours else None,
            "avg_score": round(sum(sleep_scores) / len(sleep_scores)) if sleep_scores else None,
            "days": len(sleep_hours),
            "best_night": max(sleep_hours) if sleep_hours else None,
            "worst_night": min(sleep_hours) if sleep_hours else None
        }
    except Exception as e:
        logger.error(f"Failed to get sleep week: {e}")
        return {}


async def _get_heart_rate_week() -> dict:
    """Get resting heart rate data for the past week."""
    try:
        start_date = (datetime.now() - timedelta(days=7)).date().isoformat()

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/garmin_daily_summary",
                headers=_get_headers(),
                params={
                    "select": "date,resting_hr",
                    "user_id": "eq.chris",
                    "date": f"gte.{start_date}",
                    "order": "date.asc"
                },
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"HR query failed: {response.status_code}")
                return {}

            data = response.json()

        if not data:
            return {}

        hrs = [d["resting_hr"] for d in data if d.get("resting_hr")]

        return {
            "avg": round(sum(hrs) / len(hrs)) if hrs else None,
            "min": min(hrs) if hrs else None,
            "max": max(hrs) if hrs else None,
            "days": len(hrs)
        }
    except Exception as e:
        logger.error(f"Failed to get HR week: {e}")
        return {}


async def _get_goals() -> dict:
    """Get user's goals from nutrition_goals table."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/nutrition_goals",
                headers=_get_headers(),
                params={
                    "select": "*",
                    "user_id": "eq.chris",
                    "limit": "1"
                },
                timeout=30
            )

            if response.status_code != 200:
                return {}

            data = response.json()
            return data[0] if data else {}
    except Exception as e:
        logger.error(f"Failed to get goals: {e}")
        return {}


def _calculate_grade(weight: dict, nutrition: dict, steps: dict, sleep: dict, hr: dict) -> tuple[str, str]:
    """Calculate overall PT grade for the week."""
    score = 0
    max_score = 0

    # Weight (20 points) - lost weight = good
    if weight.get("change") is not None:
        max_score += 20
        if weight["change"] < -0.5:
            score += 20  # Lost significant weight
        elif weight["change"] < 0:
            score += 15  # Lost some weight
        elif weight["change"] == 0:
            score += 10  # Maintained
        else:
            score += 5  # Gained weight

    # Protein (25 points) - hitting targets
    if nutrition.get("protein_days_hit") is not None:
        max_score += 25
        hit_rate = nutrition["protein_days_hit"] / max(nutrition["days_tracked"], 1)
        score += round(25 * hit_rate)

    # Steps (25 points) - hitting goal
    if steps.get("days_hit_goal") is not None and steps.get("days"):
        max_score += 25
        hit_rate = steps["days_hit_goal"] / steps["days"]
        score += round(25 * hit_rate)

    # Sleep (15 points) - good sleep
    if sleep.get("avg_hours") is not None:
        max_score += 15
        if sleep["avg_hours"] >= 7.5:
            score += 15
        elif sleep["avg_hours"] >= 7:
            score += 12
        elif sleep["avg_hours"] >= 6.5:
            score += 8
        else:
            score += 4

    # Heart rate (15 points) - lower is better
    if hr.get("avg") is not None:
        max_score += 15
        if hr["avg"] <= 55:
            score += 15
        elif hr["avg"] <= 60:
            score += 12
        elif hr["avg"] <= 65:
            score += 8
        else:
            score += 4

    if max_score == 0:
        return "?", "Insufficient data"

    percentage = round((score / max_score) * 100)

    if percentage >= 90:
        return "A+", "Outstanding week! 🏆"
    elif percentage >= 80:
        return "A", "Excellent work! 💪"
    elif percentage >= 70:
        return "B", "Good progress! 👍"
    elif percentage >= 60:
        return "C", "Decent effort, room to improve"
    elif percentage >= 50:
        return "D", "Below target - refocus next week"
    else:
        return "F", "Tough week - fresh start Monday"


async def _generate_pt_summary(weight: dict, nutrition: dict, steps: dict, sleep: dict, goals: dict) -> str:
    """Generate AI PT summary using Claude Haiku."""
    try:
        if not ANTHROPIC_API_KEY:
            return "Keep pushing towards Japan! 🇯🇵"

        prompt = f"""Generate a brief (2-3 sentences) weekly PT summary for Chris based on this week's data:

Weight: Started {weight.get('start', '?')}kg, ended {weight.get('end', '?')}kg ({weight.get('change', 0):+.1f}kg change)
Nutrition: {nutrition.get('avg_calories', '?')} avg cal/day, {nutrition.get('avg_protein', '?')}g protein, {nutrition.get('protein_days_hit', '?')}/{nutrition.get('days_tracked', 7)} days hit protein target
Steps: {steps.get('avg', '?')} avg/day, {steps.get('days_hit_goal', '?')}/{steps.get('days', 7)} days hit 15K goal
Sleep: {sleep.get('avg_hours', '?')}h avg

Goal: {goals.get('target_weight_kg', 80)}kg for {goals.get('goal_reason', 'Japan trip')} in {goals.get('days_remaining', '?')} days

Style: Direct, motivational, PT-style. Call out wins and areas to improve. No fluff."""

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
                return data["content"][0]["text"]
            else:
                return "Keep pushing towards Japan! 🇯🇵"

    except Exception as e:
        logger.error(f"Haiku summary error: {e}")
        return "Keep pushing towards Japan! 🇯🇵"


def _generate_weekly_graphs(weight: dict, nutrition: dict, steps: dict) -> io.BytesIO | None:
    """Generate a combined graph image for the weekly summary."""
    try:
        # Set dark theme for Discord
        plt.style.use('dark_background')

        # Count how many graphs we have data for
        has_weight = bool(weight.get("raw_weights") and len(weight["raw_weights"]) >= 2)
        has_nutrition = bool(nutrition.get("raw_dates") and len(nutrition["raw_dates"]) >= 2)
        has_steps = bool(steps.get("raw_steps") and len(steps["raw_steps"]) >= 2)

        num_graphs = sum([has_weight, has_nutrition, has_steps])
        if num_graphs == 0:
            return None

        fig, axes = plt.subplots(num_graphs, 1, figsize=(10, 3 * num_graphs))
        if num_graphs == 1:
            axes = [axes]

        ax_idx = 0

        # Weight graph
        if has_weight:
            ax = axes[ax_idx]
            dates = weight["raw_dates"]
            weights = weight["raw_weights"]

            ax.plot(dates, weights, 'o-', color='#00d4aa', linewidth=2, markersize=8)
            ax.fill_between(dates, weights, min(weights) - 0.5, alpha=0.3, color='#00d4aa')
            ax.set_ylabel('Weight (kg)', fontsize=11)
            ax.set_title('Weight Trend', fontsize=13, fontweight='bold', color='white')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%a'))
            ax.grid(True, alpha=0.3)

            # Add target line if available
            ax.axhline(y=80, color='#ff6b6b', linestyle='--', alpha=0.7, label='Target: 80kg')
            ax.legend(loc='upper right', fontsize=9)

            ax_idx += 1

        # Nutrition graph (calories + protein)
        if has_nutrition:
            ax = axes[ax_idx]
            dates = nutrition["raw_dates"]
            calories = nutrition["raw_calories"]
            protein = nutrition["raw_protein"]

            # Bar chart for calories
            ax.bar(dates, calories, color='#ff9f43', alpha=0.8, label='Calories')
            ax.axhline(y=1850, color='#ff6b6b', linestyle='--', alpha=0.7, label='Cal target: 1850')
            ax.set_ylabel('Calories', fontsize=11, color='#ff9f43')
            ax.set_title('Nutrition', fontsize=13, fontweight='bold', color='white')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%a'))

            # Secondary axis for protein
            ax2 = ax.twinx()
            ax2.plot(dates, protein, 'o-', color='#54a0ff', linewidth=2, markersize=6, label='Protein')
            ax2.axhline(y=160, color='#54a0ff', linestyle=':', alpha=0.7, label='Protein target: 160g')
            ax2.set_ylabel('Protein (g)', fontsize=11, color='#54a0ff')

            # Combine legends
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=8)
            ax.grid(True, alpha=0.3)

            ax_idx += 1

        # Steps graph
        if has_steps:
            ax = axes[ax_idx]
            dates = steps["raw_dates"]
            step_vals = steps["raw_steps"]
            goal = steps.get("goal", 15000)

            # Color bars based on goal achievement
            colors = ['#00d4aa' if s >= goal else '#ff6b6b' for s in step_vals]
            ax.bar(dates, step_vals, color=colors, alpha=0.8)
            ax.axhline(y=goal, color='#feca57', linestyle='--', linewidth=2, label=f'Goal: {goal:,}')
            ax.set_ylabel('Steps', fontsize=11)
            ax.set_title('Daily Steps', fontsize=13, fontweight='bold', color='white')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%a'))
            ax.legend(loc='upper right', fontsize=9)
            ax.grid(True, alpha=0.3)

            # Format y-axis with commas
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))

        plt.tight_layout()

        # Save to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight',
                    facecolor='#2f3136', edgecolor='none')
        buf.seek(0)
        plt.close(fig)

        return buf

    except Exception as e:
        logger.error(f"Failed to generate graphs: {e}")
        return None


async def weekly_health_summary(bot):
    """Generate and send the weekly health summary."""
    try:
        channel = bot.get_channel(WEEKLY_HEALTH_CHANNEL_ID)
        if not channel:
            logger.error(f"Weekly health channel {WEEKLY_HEALTH_CHANNEL_ID} not found")
            return

        # Gather data
        weight = await _get_weight_week()
        nutrition = await _get_nutrition_week()
        steps = await _get_steps_week()
        sleep = await _get_sleep_week()
        hr = await _get_heart_rate_week()
        goals = await _get_goals()

        # Calculate grade
        grade, grade_desc = _calculate_grade(weight, nutrition, steps, sleep, hr)

        # Generate PT summary
        pt_summary = await _generate_pt_summary(weight, nutrition, steps, sleep, goals)

        # Format date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        date_range = f"{start_date.strftime('%d %b')} - {end_date.strftime('%d %b')}"

        # Build message
        lines = [
            f"**📊 WEEKLY HEALTH REVIEW** — {date_range}",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            f"**🎯 Overall Grade: {grade}** — {grade_desc}",
            "",
            pt_summary,
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "**⚖️ Weight**"
        ]

        if weight.get("start"):
            change_str = f"{weight['change']:+.1f}kg" if weight['change'] != 0 else "no change"
            lines.append(f"📉 {weight['start']}kg → {weight['end']}kg ({change_str})")
            lines.append(f"   Range: {weight['min']} - {weight['max']}kg | Avg: {weight['avg']}kg")
        else:
            lines.append("⚠️ No weight data this week")

        lines.extend(["", "**🍽️ Nutrition**"])
        if nutrition.get("avg_calories"):
            lines.append(f"🔥 {nutrition['avg_calories']} cal/day avg | {nutrition['days_tracked']} days tracked")
            lines.append(f"🥩 {nutrition['avg_protein']}g protein avg | Hit target: {nutrition['protein_days_hit']}/{nutrition['days_tracked']} days")
            lines.append(f"   C: {nutrition['avg_carbs']}g | F: {nutrition['avg_fat']}g | 💧 {nutrition['avg_water']}ml water")
        else:
            lines.append("⚠️ No nutrition data this week")

        lines.extend(["", "**🚶 Activity**"])
        if steps.get("total"):
            lines.append(f"👟 {steps['total']:,} total steps ({steps['avg']:,}/day)")
            lines.append(f"🎯 Hit {steps['goal']:,} goal: {steps['days_hit_goal']}/{steps['days']} days")
            lines.append(f"🏆 Best day: {steps['best_day']:,} steps")
        else:
            lines.append("⚠️ No step data this week")

        lines.extend(["", "**😴 Sleep**"])
        if sleep.get("avg_hours"):
            score_str = f" (score: {sleep['avg_score']})" if sleep.get("avg_score") else ""
            lines.append(f"🛏️ {sleep['avg_hours']}h avg{score_str}")
            lines.append(f"   Best: {sleep['best_night']}h | Worst: {sleep['worst_night']}h")
        else:
            lines.append("⚠️ No sleep data this week")

        lines.extend(["", "**❤️ Heart Rate**"])
        if hr.get("avg"):
            lines.append(f"💓 {hr['avg']} bpm resting avg")
            lines.append(f"   Range: {hr['min']} - {hr['max']} bpm")
        else:
            lines.append("⚠️ No heart rate data this week")

        # Days remaining
        if goals.get("days_remaining"):
            lines.extend([
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"📅 **{goals['days_remaining']} days** until {goals.get('goal_reason', 'your goal')}"
            ])

        message = "\n".join(lines)

        # Generate graphs
        graph_buf = _generate_weekly_graphs(weight, nutrition, steps)

        if graph_buf:
            # Send message with graph attachment
            file = discord.File(graph_buf, filename="weekly_health.png")
            await channel.send(message, file=file)
            logger.info("Posted weekly health summary with graphs")
        else:
            # Send text only if no graphs
            await channel.send(message)
            logger.info("Posted weekly health summary (no graphs)")

    except Exception as e:
        logger.error(f"Failed to post weekly health summary: {e}")


def register_weekly_health(scheduler, bot):
    """Register the weekly health summary job with the scheduler."""
    scheduler.add_job(
        weekly_health_summary,
        'cron',
        args=[bot],
        day_of_week='sun',
        hour=9,
        minute=0,
        timezone="Europe/London",
        id="weekly_health_summary"
    )
    logger.info("Registered weekly health summary job (Sunday 9:00 AM UK)")
