"""API Usage domain scheduled tasks."""

from datetime import datetime

from domains.base import ScheduledTask
from .services import get_anthropic_usage, get_openai_usage
from .config import CHANNEL_ID

from logger import logger


async def weekly_summary(bot, domain):
    """Post weekly API usage summary."""
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        logger.error(f"Could not find api-usage channel {CHANNEL_ID}")
        return

    try:
        anthropic_data = await get_anthropic_usage(days=7)
        openai_data = await get_openai_usage(days=7)

        today = datetime.now()
        date_str = today.strftime("%d %b %Y")

        lines = [
            f"📊 **Weekly API Usage Summary** - {date_str}",
            ""
        ]

        # Anthropic
        if anthropic_data.get("total_cost") is not None:
            lines.append(f"🔮 **Claude (Anthropic):** ${anthropic_data['total_cost']:.2f}")
        else:
            lines.append(f"🔮 **Claude (Anthropic):** {anthropic_data.get('note', 'unavailable')}")

        # OpenAI
        if openai_data.get("total_cost") is not None:
            lines.append(f"🤖 **OpenAI:** ${openai_data['total_cost']:.2f}")
        else:
            lines.append(f"🤖 **OpenAI:** {openai_data.get('note', 'unavailable')}")

        # Total
        total = 0
        if anthropic_data.get("total_cost"):
            total += anthropic_data["total_cost"]
        if openai_data.get("total_cost"):
            total += openai_data["total_cost"]

        if total > 0:
            lines.append("")
            lines.append(f"💰 **Total:** ${total:.2f}")

        message = "\n".join(lines)
        await channel.send(message)
        logger.info("Posted weekly API usage summary")

    except Exception as e:
        logger.error(f"Failed to post weekly summary: {e}")


SCHEDULES = [
    ScheduledTask(
        name="weekly_summary",
        handler=weekly_summary,
        hour=9,
        minute=0,
        day_of_week="mon",  # Weekly on Monday
        timezone="Europe/London"
    )
]
