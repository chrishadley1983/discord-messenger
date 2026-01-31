"""Nutrition domain scheduled tasks."""

import os
from datetime import datetime

from domains.base import ScheduledTask
from .services import get_today_totals, get_steps, get_weight
from .config import CHANNEL_ID, DAILY_TARGETS

from logger import logger


def _get_emoji(actual: float, target: float, is_upper_bound: bool = False) -> str:
    """Get emoji based on progress percentage."""
    if target == 0:
        return "➖"

    percentage = (actual / target) * 100

    if is_upper_bound:
        # For calories, being under is good
        if percentage <= 110:
            return "✅"
        elif percentage <= 130:
            return "🟡"
        else:
            return "❌"
    else:
        # For other metrics, hitting target is good
        if percentage >= 90:
            return "✅"
        elif percentage >= 70:
            return "🟡"
        else:
            return "❌"


async def daily_summary(bot, domain):
    """Post 9pm daily summary."""
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        logger.error(f"Could not find nutrition channel {CHANNEL_ID}")
        return

    try:
        totals = await get_today_totals()
        steps_data = await get_steps()
        weight_data = await get_weight()

        # Build summary message
        today = datetime.now()
        weekday = today.strftime("%A")
        date_str = today.strftime("%d %b")

        lines = [
            f"📊 **Daily Summary** - {weekday} {date_str}",
            "",
            f"{_get_emoji(totals['calories'], DAILY_TARGETS['calories'], is_upper_bound=True)} **Calories:** {totals['calories']:,.0f} / {DAILY_TARGETS['calories']:,}",
            f"{_get_emoji(totals['protein_g'], DAILY_TARGETS['protein_g'])} **Protein:** {totals['protein_g']:.0f}g / {DAILY_TARGETS['protein_g']}g",
            f"{_get_emoji(totals['carbs_g'], DAILY_TARGETS['carbs_g'])} **Carbs:** {totals['carbs_g']:.0f}g / {DAILY_TARGETS['carbs_g']}g",
            f"{_get_emoji(totals['fat_g'], DAILY_TARGETS['fat_g'])} **Fat:** {totals['fat_g']:.0f}g / {DAILY_TARGETS['fat_g']}g",
            f"{_get_emoji(totals['water_ml'], DAILY_TARGETS['water_ml'])} **Water:** {totals['water_ml']:,.0f}ml / {DAILY_TARGETS['water_ml']:,}ml",
        ]

        # Add steps if available
        if steps_data.get("steps") is not None:
            lines.append(f"{_get_emoji(steps_data['steps'], DAILY_TARGETS['steps'])} **Steps:** {steps_data['steps']:,} / {DAILY_TARGETS['steps']:,}")
        else:
            lines.append("➖ **Steps:** unavailable")

        # Add weight if available
        if weight_data.get("weight_kg") is not None:
            remaining = weight_data["weight_kg"] - 80  # Target is 80kg
            lines.append("")
            lines.append(f"⚖️ **{weight_data['weight_kg']}kg** → 80kg. {remaining:.1f}kg to go.")

        message = "\n".join(lines)
        await channel.send(message)
        logger.info("Posted daily nutrition summary")

    except Exception as e:
        logger.error(f"Failed to post daily summary: {e}")


SCHEDULES = [
    ScheduledTask(
        name="daily_summary",
        handler=daily_summary,
        hour=21,
        minute=0,
        timezone="Europe/London"
    )
]
