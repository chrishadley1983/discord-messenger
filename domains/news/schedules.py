"""News domain scheduled tasks."""

from datetime import datetime

from domains.base import ScheduledTask
from .services import fetch_feed
from .config import CHANNEL_ID

from logger import logger


async def morning_briefing(bot, domain):
    """Post 7am news briefing."""
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        logger.error(f"Could not find news channel {CHANNEL_ID}")
        return

    try:
        # Fetch headlines from all categories
        tech_news = await fetch_feed("tech", limit=3)
        uk_news = await fetch_feed("uk", limit=2)
        f1_news = await fetch_feed("f1", limit=2)

        today = datetime.now()
        weekday = today.strftime("%A")
        date_str = today.strftime("%d %b")

        lines = [
            f"📰 **Morning Briefing** - {weekday} {date_str}",
            "",
            "**🖥️ Tech**"
        ]

        for h in tech_news.get("headlines", [])[:3]:
            lines.append(f"• [{h['title']}]({h['url']}) - {h['source']}")

        lines.append("")
        lines.append("**🇬🇧 UK News**")
        for h in uk_news.get("headlines", [])[:2]:
            lines.append(f"• [{h['title']}]({h['url']}) - {h['source']}")

        lines.append("")
        lines.append("**🏎️ F1**")
        for h in f1_news.get("headlines", [])[:2]:
            lines.append(f"• [{h['title']}]({h['url']}) - {h['source']}")

        message = "\n".join(lines)
        await channel.send(message)
        logger.info("Posted morning news briefing")

    except Exception as e:
        logger.error(f"Failed to post morning briefing: {e}")


SCHEDULES = [
    ScheduledTask(
        name="morning_briefing",
        handler=morning_briefing,
        hour=7,
        minute=0,
        timezone="Europe/London"
    )
]
