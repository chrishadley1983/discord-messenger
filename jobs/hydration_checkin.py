"""Hydration & Steps Check-in scheduled job.

Runs every 2 hours (9am-9pm UK) to post water intake and step progress.
Posts to #food-log channel with progress vs targets and motivational advice.
Uses Claude Haiku for personalized, context-aware messages (~$0.02/month).
"""

import random
from datetime import datetime

from config import call_claude_via_cli
from domains.nutrition.services import get_today_totals, get_steps
from domains.nutrition.config import CHANNEL_ID, DAILY_TARGETS
from logger import logger



def _progress_bar(current: float, target: float, width: int = 10) -> str:
    """Create a simple text progress bar."""
    if target == 0:
        return "─" * width

    percentage = min(current / target, 1.0)
    filled = int(percentage * width)
    empty = width - filled
    return "█" * filled + "░" * empty


def _get_time_emoji() -> str:
    """Get emoji based on time of day."""
    hour = datetime.now().hour
    if hour < 12:
        return "🌅"  # Morning
    elif hour < 17:
        return "☀️"  # Afternoon
    else:
        return "🌆"  # Evening


async def _get_haiku_motivation(water_ml: float, water_target: float, water_pct: float,
                                 steps: int, steps_target: int, steps_pct: float,
                                 hour: int) -> str:
    """Get personalized motivation from Claude Haiku."""
    try:
        time_of_day = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
        hours_left = 21 - hour  # Until 9pm

        prompt = f"""You are Pete, a cheeky but supportive fitness coach. Give a brief (2-3 sentences max) motivational message about hydration and steps progress.

Current stats:
- Water: {water_ml:.0f}ml / {water_target:.0f}ml ({water_pct:.0f}%)
- Steps: {steps:,} / {steps_target:,} ({steps_pct:.0f}%)
- Time: {hour}:00 ({time_of_day}), {hours_left} hours until 9pm

Be specific about the numbers. If behind, be encouraging but direct. If on track, celebrate. Use 1-2 emojis max. Keep it punchy and personal."""

        result = await call_claude_via_cli(prompt, max_tokens=150, timeout=15)
        if result:
            logger.info(f"Claude motivation generated ({len(result)} chars)")
            return result
        return _get_fallback_motivation(water_pct, steps_pct, hour)

    except Exception as e:
        logger.error(f"Claude motivation error: {e}")
        return _get_fallback_motivation(water_pct, steps_pct, hour)


def _get_fallback_motivation(water_pct: float, steps_pct: float, hour: int) -> str:
    """Fallback template-based motivation if Haiku fails."""
    water_msg = _get_water_motivation(water_pct, hour)
    steps_msg = _get_steps_motivation(steps_pct, hour)
    return f"{water_msg}\n{steps_msg}"


def _get_water_motivation(pct: float, hour: int) -> str:
    """Get motivational message for water intake."""
    if pct >= 100:
        return random.choice([
            "💪 Hydration complete! Keep sipping if you feel thirsty.",
            "🎯 Water target smashed! Great work staying hydrated.",
            "✅ You've hit your water goal - well done!"
        ])
    elif pct >= 80:
        return random.choice([
            "🔥 Nearly there! Just a few more glasses.",
            "💧 Almost at target - finish strong!",
            "👊 So close! One more bottle should do it."
        ])
    elif pct >= 50:
        if hour >= 17:
            return "⚡ Half done but evening's here - pick up the pace!"
        return random.choice([
            "👍 On track. Keep the water coming.",
            "📈 Good progress - stay consistent.",
            "💧 Halfway mark. Time for another glass!"
        ])
    elif pct >= 30:
        if hour >= 15:
            return "⚠️ Behind schedule - time to catch up!"
        return "💧 Good start. Try to drink more before lunch."
    else:
        if hour >= 13:
            return "🚨 Water is way behind! Get a big glass now."
        elif hour >= 11:
            return "⚠️ Behind on water - set a reminder to drink!"
        return "💧 Fresh day ahead. Start with a big glass!"


def _get_steps_motivation(pct: float, hour: int) -> str:
    """Get motivational message for steps."""
    if pct >= 100:
        return random.choice([
            "🏆 Step goal crushed! Bonus points for any extra.",
            "🎉 Steps complete! Great day of movement.",
            "💪 You've smashed your step target!"
        ])
    elif pct >= 80:
        return random.choice([
            "🔥 Almost there! A short walk will finish it.",
            "👟 So close - a quick stroll will do it.",
            "🚶 Nearly at target - keep moving!"
        ])
    elif pct >= 50:
        if hour >= 19:
            return "⚡ Half done - an evening walk could catch you up!"
        return random.choice([
            "👍 Solid progress. Keep active this afternoon.",
            "📈 On pace. Look for chances to move more.",
            "🚶 Halfway there. Find excuses to walk!"
        ])
    elif pct >= 30:
        if hour >= 17:
            return "⚠️ Steps behind - time for a walk before it gets late!"
        return "👟 Time to get moving! Try a walking break."
    else:
        if hour >= 15:
            return "🚨 Steps are low! Get outside for a walk."
        elif hour >= 12:
            return "⚠️ Low steps - try a lunchtime walk?"
        return "🌅 New day, fresh steps. Get moving early!"


async def hydration_checkin(bot):
    """Post hydration and steps check-in with fresh Garmin data."""
    logger.info(f"Hydration check-in starting - looking for channel {CHANNEL_ID}")

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(CHANNEL_ID)
        except Exception as e:
            logger.error(f"Could not find #food-log channel {CHANNEL_ID}: {e}")
            return

    try:
        # Get current data (get_steps fetches fresh from Garmin)
        totals = await get_today_totals()
        steps_data = await get_steps()

        water_ml = totals.get("water_ml", 0)
        water_target = DAILY_TARGETS["water_ml"]
        water_pct = (water_ml / water_target * 100) if water_target else 0

        raw_steps = steps_data.get("steps") if steps_data else None
        steps = raw_steps if raw_steps is not None else 0
        steps_available = raw_steps is not None and steps_data.get("error") is None
        steps_target = DAILY_TARGETS["steps"]
        steps_pct = (steps / steps_target * 100) if steps_target and steps_available else 0

        # Get time info
        now = datetime.now()
        hour = now.hour
        time_emoji = _get_time_emoji()

        # Get personalized motivation from Haiku
        motivation = await _get_haiku_motivation(
            water_ml, water_target, water_pct,
            steps, steps_target, steps_pct,
            hour
        )

        # Build message
        if steps_available:
            steps_line = f"🚶 **Steps:** {steps:,} / {steps_target:,} ({steps_pct:.0f}%)"
            steps_bar = f"   {_progress_bar(steps, steps_target)}"
        else:
            steps_line = "🚶 **Steps:** ⚠️ unavailable (Garmin sync pending)"
            steps_bar = ""

        lines = [
            f"{time_emoji} **{hour}:00 Check-in**",
            "",
            f"💧 **Water:** {water_ml:,.0f}ml / {water_target:,}ml ({water_pct:.0f}%)",
            f"   {_progress_bar(water_ml, water_target)}",
            "",
            steps_line,
        ]
        if steps_bar:
            lines.append(steps_bar)
        lines += [
            "",
            "---",
            motivation,
        ]

        message = "\n".join(lines)
        await channel.send(message)
        logger.info(f"Posted hydration check-in - Water: {water_ml}ml ({water_pct:.0f}%), Steps: {steps} ({steps_pct:.0f}%)")

    except Exception as e:
        logger.error(f"Failed to post hydration check-in: {e}")


def register_hydration_checkin(scheduler, bot):
    """Register the hydration check-in job with the scheduler."""
    scheduler.add_job(
        hydration_checkin,
        'cron',
        args=[bot],
        hour='9,11,13,15,17,19,21',  # Every 2 hours, 9am-9pm
        minute=0,
        timezone="Europe/London",
        id="hydration_checkin"
    )
    logger.info("Registered hydration check-in job (every 2h, 9am-9pm UK)")
