"""Monthly Health Summary scheduled job.

Schedule:
- 1st of each month at 9:00 AM (Europe/London)

Posts to Discord #food-log with:
- Weight progress over the month
- Nutrition averages and consistency
- Activity/steps summary
- Sleep quality trends
- Month-over-month comparison
- Progress toward goal
- Visual graphs
"""

import io
from datetime import datetime, timedelta

import discord
import httpx
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from config import SUPABASE_URL, SUPABASE_KEY, ANTHROPIC_API_KEY
from logger import logger

# Discord channel for monthly health summary
MONTHLY_HEALTH_CHANNEL_ID = 1465294449038069912  # #food-log


def _get_headers() -> dict:
    """Get Supabase API headers."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }


async def _get_weight_month() -> dict:
    """Get weight data for the past month."""
    try:
        start_date = (datetime.now() - timedelta(days=30)).isoformat()

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
        logger.error(f"Failed to get weight month: {e}")
        return {}


async def _get_nutrition_month() -> dict:
    """Get nutrition averages for the past month."""
    try:
        start_date = (datetime.now() - timedelta(days=30)).date().isoformat()
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

        # Sort by date for graph (weekly averages)
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
            "protein_days_hit": sum(1 for d in daily.values() if d["protein"] >= 144),
            "tracking_rate": round((days / 30) * 100),
            "raw_dates": raw_dates,
            "raw_calories": raw_calories,
            "raw_protein": raw_protein
        }
    except Exception as e:
        logger.error(f"Failed to get nutrition month: {e}")
        return {}


async def _get_steps_month() -> dict:
    """Get steps data for the past 30 days."""
    try:
        end_date = datetime.now().date().isoformat()
        start_date = (datetime.now() - timedelta(days=30)).date().isoformat()

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
            "worst_day": min(steps) if steps else 0,
            "goal": goal,
            "raw_steps": steps,
            "raw_dates": dates
        }
    except Exception as e:
        logger.error(f"Failed to get steps month: {e}")
        return {}


async def _get_sleep_month() -> dict:
    """Get sleep data for the past month."""
    try:
        start_date = (datetime.now() - timedelta(days=30)).date().isoformat()

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
            "worst_night": min(sleep_hours) if sleep_hours else None,
            "nights_7plus": sum(1 for h in sleep_hours if h >= 7)
        }
    except Exception as e:
        logger.error(f"Failed to get sleep month: {e}")
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


async def _get_previous_month() -> dict:
    """Get summary from previous month for comparison."""
    try:
        # Previous month: 60 to 30 days ago
        end_date = (datetime.now() - timedelta(days=30)).date().isoformat()
        start_date = (datetime.now() - timedelta(days=60)).date().isoformat()

        # Weight
        async with httpx.AsyncClient() as client:
            weight_resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/weight_readings",
                headers=_get_headers(),
                params={
                    "select": "weight_kg",
                    "user_id": "eq.chris",
                    "measured_at": f"gte.{start_date}",
                    "measured_at": f"lt.{end_date}",
                    "order": "measured_at.asc"
                },
                timeout=30
            )

            weight_data = weight_resp.json() if weight_resp.status_code == 200 else []
            weights = [float(r["weight_kg"]) for r in weight_data] if weight_data else []

            # Steps
            filter_str = f"and=(date.gte.{start_date},date.lt.{end_date})"
            steps_url = f"{SUPABASE_URL}/rest/v1/garmin_daily_summary?select=steps&user_id=eq.chris&{filter_str}"
            steps_resp = await client.get(steps_url, headers=_get_headers(), timeout=30)

            steps_data = steps_resp.json() if steps_resp.status_code == 200 else []
            steps = [d["steps"] for d in steps_data if d.get("steps")]

        return {
            "avg_weight": round(sum(weights) / len(weights), 1) if weights else None,
            "avg_steps": round(sum(steps) / len(steps)) if steps else None
        }
    except Exception as e:
        logger.error(f"Failed to get previous month: {e}")
        return {}


async def _generate_monthly_summary(weight: dict, nutrition: dict, steps: dict, goals: dict, prev: dict) -> str:
    """Generate AI monthly summary using Claude Haiku."""
    try:
        if not ANTHROPIC_API_KEY:
            return "Another month down. Keep pushing! 💪"

        prompt = f"""Generate a brief (3-4 sentences) monthly health summary for Chris.

This month's data:
- Weight: Started {weight.get('start', '?')}kg, ended {weight.get('end', '?')}kg ({weight.get('change', 0):+.1f}kg change)
- Avg weight: {weight.get('avg', '?')}kg (previous month: {prev.get('avg_weight', '?')}kg)
- Nutrition: {nutrition.get('avg_calories', '?')} avg cal/day, {nutrition.get('avg_protein', '?')}g protein
- Protein target hit: {nutrition.get('protein_days_hit', '?')}/{nutrition.get('days_tracked', 30)} days
- Tracking consistency: {nutrition.get('tracking_rate', '?')}%
- Steps: {steps.get('avg', '?')} avg/day (previous month: {prev.get('avg_steps', '?')})
- Step goal hit: {steps.get('days_hit_goal', '?')}/{steps.get('days', 30)} days

Goal: {goals.get('target_weight_kg', 80)}kg for {goals.get('goal_reason', 'Japan trip')} in {goals.get('days_remaining', '?')} days

Style: PT summary - celebrate wins, call out areas to improve, set focus for next month. No fluff."""

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
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                return data["content"][0]["text"]
            else:
                return "Another month down. Keep pushing toward Japan! 🇯🇵"

    except Exception as e:
        logger.error(f"Haiku summary error: {e}")
        return "Another month down. Keep pushing toward Japan! 🇯🇵"


def _generate_monthly_graphs(weight: dict, nutrition: dict, steps: dict) -> io.BytesIO | None:
    """Generate monthly graph image."""
    try:
        plt.style.use('dark_background')

        has_weight = bool(weight.get("raw_weights") and len(weight["raw_weights"]) >= 3)
        has_nutrition = bool(nutrition.get("raw_dates") and len(nutrition["raw_dates"]) >= 3)
        has_steps = bool(steps.get("raw_steps") and len(steps["raw_steps"]) >= 3)

        num_graphs = sum([has_weight, has_nutrition, has_steps])
        if num_graphs == 0:
            return None

        fig, axes = plt.subplots(num_graphs, 1, figsize=(12, 3.5 * num_graphs))
        if num_graphs == 1:
            axes = [axes]

        ax_idx = 0

        # Weight graph with trend line
        if has_weight:
            ax = axes[ax_idx]
            dates = weight["raw_dates"]
            weights = weight["raw_weights"]

            ax.plot(dates, weights, 'o-', color='#00d4aa', linewidth=2, markersize=6, alpha=0.8)
            ax.fill_between(dates, weights, min(weights) - 0.5, alpha=0.2, color='#00d4aa')

            # Add trend line
            import numpy as np
            if len(dates) >= 3:
                x_numeric = np.array([(d - dates[0]).days for d in dates])
                z = np.polyfit(x_numeric, weights, 1)
                p = np.poly1d(z)
                ax.plot(dates, p(x_numeric), '--', color='#feca57', linewidth=2, alpha=0.8, label='Trend')

            ax.axhline(y=80, color='#ff6b6b', linestyle='--', alpha=0.7, label='Target: 80kg')
            ax.set_ylabel('Weight (kg)', fontsize=11)
            ax.set_title('Weight Trend (30 Days)', fontsize=13, fontweight='bold', color='white')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
            ax.legend(loc='upper right', fontsize=9)
            ax.grid(True, alpha=0.3)
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

            ax_idx += 1

        # Nutrition graph
        if has_nutrition:
            ax = axes[ax_idx]
            dates = nutrition["raw_dates"]
            calories = nutrition["raw_calories"]
            protein = nutrition["raw_protein"]

            ax.bar(dates, calories, color='#ff9f43', alpha=0.7, width=0.8, label='Calories')
            ax.axhline(y=1850, color='#ff6b6b', linestyle='--', alpha=0.7, label='Cal target: 1850')
            ax.set_ylabel('Calories', fontsize=11, color='#ff9f43')
            ax.set_title('Nutrition (30 Days)', fontsize=13, fontweight='bold', color='white')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))

            ax2 = ax.twinx()
            ax2.plot(dates, protein, 'o-', color='#54a0ff', linewidth=2, markersize=4, label='Protein')
            ax2.axhline(y=160, color='#54a0ff', linestyle=':', alpha=0.7, label='Protein target: 160g')
            ax2.set_ylabel('Protein (g)', fontsize=11, color='#54a0ff')

            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=8)
            ax.grid(True, alpha=0.3)
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

            ax_idx += 1

        # Steps graph
        if has_steps:
            ax = axes[ax_idx]
            dates = steps["raw_dates"]
            step_vals = steps["raw_steps"]
            goal = steps.get("goal", 15000)

            colors = ['#00d4aa' if s >= goal else '#ff6b6b' for s in step_vals]
            ax.bar(dates, step_vals, color=colors, alpha=0.7, width=0.8)
            ax.axhline(y=goal, color='#feca57', linestyle='--', linewidth=2, label=f'Goal: {goal:,}')
            ax.set_ylabel('Steps', fontsize=11)
            ax.set_title('Daily Steps (30 Days)', fontsize=13, fontweight='bold', color='white')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
            ax.legend(loc='upper right', fontsize=9)
            ax.grid(True, alpha=0.3)
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight',
                    facecolor='#2f3136', edgecolor='none')
        buf.seek(0)
        plt.close(fig)

        return buf

    except Exception as e:
        logger.error(f"Failed to generate monthly graphs: {e}")
        return None


async def monthly_health_summary(bot):
    """Generate and send the monthly health summary."""
    try:
        channel = bot.get_channel(MONTHLY_HEALTH_CHANNEL_ID)
        if not channel:
            logger.error(f"Monthly health channel {MONTHLY_HEALTH_CHANNEL_ID} not found")
            return

        # Gather data
        weight = await _get_weight_month()
        nutrition = await _get_nutrition_month()
        steps = await _get_steps_month()
        sleep = await _get_sleep_month()
        goals = await _get_goals()
        prev = await _get_previous_month()

        # Generate AI summary
        ai_summary = await _generate_monthly_summary(weight, nutrition, steps, goals, prev)

        # Format date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        month_name = start_date.strftime('%B %Y')

        # Build message
        lines = [
            f"**📅 MONTHLY HEALTH REVIEW** — {month_name}",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            ai_summary,
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "**⚖️ Weight**"
        ]

        if weight.get("start"):
            change_str = f"{weight['change']:+.1f}kg" if weight['change'] != 0 else "no change"
            lines.append(f"📉 {weight['start']}kg → {weight['end']}kg ({change_str})")
            lines.append(f"   Range: {weight['min']} - {weight['max']}kg | Avg: {weight['avg']}kg")
            if prev.get("avg_weight"):
                mom_change = round(weight['avg'] - prev['avg_weight'], 1)
                mom_str = f"{mom_change:+.1f}kg" if mom_change != 0 else "same"
                lines.append(f"   vs last month: {mom_str}")
        else:
            lines.append("⚠️ No weight data this month")

        lines.extend(["", "**🍽️ Nutrition**"])
        if nutrition.get("avg_calories"):
            lines.append(f"🔥 {nutrition['avg_calories']} cal/day avg | {nutrition['days_tracked']} days tracked ({nutrition['tracking_rate']}%)")
            lines.append(f"🥩 {nutrition['avg_protein']}g protein avg | Hit target: {nutrition['protein_days_hit']}/{nutrition['days_tracked']} days")
            lines.append(f"   C: {nutrition['avg_carbs']}g | F: {nutrition['avg_fat']}g | 💧 {nutrition['avg_water']}ml water")
        else:
            lines.append("⚠️ No nutrition data this month")

        lines.extend(["", "**🚶 Activity**"])
        if steps.get("total"):
            lines.append(f"👟 {steps['total']:,} total steps ({steps['avg']:,}/day)")
            lines.append(f"🎯 Hit {steps['goal']:,} goal: {steps['days_hit_goal']}/{steps['days']} days ({round(steps['days_hit_goal']/steps['days']*100)}%)")
            lines.append(f"📊 Best: {steps['best_day']:,} | Worst: {steps['worst_day']:,}")
            if prev.get("avg_steps"):
                mom_change = steps['avg'] - prev['avg_steps']
                mom_str = f"{mom_change:+,}" if mom_change != 0 else "same"
                lines.append(f"   vs last month: {mom_str} steps/day")
        else:
            lines.append("⚠️ No step data this month")

        lines.extend(["", "**😴 Sleep**"])
        if sleep.get("avg_hours"):
            score_str = f" (score: {sleep['avg_score']})" if sleep.get("avg_score") else ""
            lines.append(f"🛏️ {sleep['avg_hours']}h avg{score_str}")
            lines.append(f"   7h+ nights: {sleep.get('nights_7plus', 0)}/{sleep['days']} | Best: {sleep['best_night']}h | Worst: {sleep['worst_night']}h")
        else:
            lines.append("⚠️ No sleep data this month")

        # Goal progress
        if goals.get("days_remaining") and weight.get("end"):
            target = goals.get("target_weight_kg", 80)
            current = weight["end"]
            to_go = round(current - target, 1)
            lines.extend([
                "",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"🎯 **Goal Progress**",
                f"   Current: {current}kg | Target: {target}kg | To go: {to_go}kg",
                f"📅 **{goals['days_remaining']} days** until {goals.get('goal_reason', 'your goal')}"
            ])

        message = "\n".join(lines)

        # Generate graphs
        graph_buf = _generate_monthly_graphs(weight, nutrition, steps)

        if graph_buf:
            file = discord.File(graph_buf, filename="monthly_health.png")
            await channel.send(message, file=file)
            logger.info("Posted monthly health summary with graphs")
        else:
            await channel.send(message)
            logger.info("Posted monthly health summary (no graphs)")

    except Exception as e:
        logger.error(f"Failed to post monthly health summary: {e}")


def register_monthly_health(scheduler, bot):
    """Register the monthly health summary job with the scheduler."""
    scheduler.add_job(
        monthly_health_summary,
        'cron',
        args=[bot],
        day=1,
        hour=9,
        minute=0,
        timezone="Europe/London",
        id="monthly_health_summary"
    )
    logger.info("Registered monthly health summary job (1st of month 9:00 AM UK)")
