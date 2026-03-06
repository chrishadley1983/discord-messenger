"""WhatsApp Web scraper job.

Runs daily using Playwright to scrape configured WhatsApp chats,
extract insights with Claude, and save to Second Brain.

Also keeps the Gmail export scanner as a fallback.
"""
import asyncio
import subprocess
import sys
import os

from logger import logger

ALERTS_CHANNEL_ID = 1466019126194606286  # #alerts
PETER_CHAT_CHANNEL_ID = 1319048819299143731  # #peter-chat

WHATSAPP_SCRIPTS_DIR = os.path.join(
    os.path.expanduser("~"), "claude-projects",
    "hadley-bricks-inventory-management", "scripts", "whatsapp",
)


async def whatsapp_web_scrape(bot=None):
    """Scrape WhatsApp Web for recent messages and save to Second Brain."""
    logger.info("Starting WhatsApp Web scrape...")

    script_path = os.path.join(WHATSAPP_SCRIPTS_DIR, "whatsapp_scraper.py")
    if not os.path.exists(script_path):
        logger.error(f"Script not found: {script_path}")
        return

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, script_path, "scrape"],
            capture_output=True,
            text=True,
            timeout=600,  # 10 min — scraping + Claude extraction
            cwd=WHATSAPP_SCRIPTS_DIR,
        )

        output = result.stdout[-1500:] if result.stdout else ""
        if result.returncode != 0:
            error = result.stderr[-500:] if result.stderr else "Unknown error"
            logger.error(f"WhatsApp scrape failed: {error}")
            # Post error to Discord if bot available
            if bot:
                await _post_error(bot, f"WhatsApp scrape failed: {error[:200]}")
            return

        logger.info(f"WhatsApp scrape complete: {output[-300:]}")

        # Post summary to Discord
        if bot and "Scrape Summary" in output:
            summary = output[output.index("Scrape Summary"):]
            await _post_summary(bot, summary[:500])

    except subprocess.TimeoutExpired:
        logger.error("WhatsApp scrape timed out (10 min)")
    except Exception as e:
        logger.error(f"WhatsApp scrape error: {e}")


async def whatsapp_export_scan(bot=None):
    """Fallback: Check Gmail for WhatsApp export emails."""
    logger.info("Starting WhatsApp export scan (Gmail fallback)...")

    script_path = os.path.join(WHATSAPP_SCRIPTS_DIR, "gmail_whatsapp_scanner.py")
    if not os.path.exists(script_path):
        logger.error(f"Script not found: {script_path}")
        return

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=WHATSAPP_SCRIPTS_DIR,
        )

        output = result.stdout[-1000:] if result.stdout else ""
        if result.returncode != 0:
            error = result.stderr[-500:] if result.stderr else "Unknown error"
            logger.error(f"WhatsApp Gmail scan failed: {error}")
            return

        logger.info(f"WhatsApp Gmail scan complete: {output[-200:]}")

    except subprocess.TimeoutExpired:
        logger.error("WhatsApp Gmail scan timed out")
    except Exception as e:
        logger.error(f"WhatsApp Gmail scan error: {e}")


async def _post_summary(bot, summary: str):
    """Post scrape summary to #peter-chat."""
    channel = bot.get_channel(PETER_CHAT_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(PETER_CHAT_CHANNEL_ID)
        except Exception:
            return
    await channel.send(f"**WhatsApp Sync Complete**\n```\n{summary}\n```")


async def _post_error(bot, error: str):
    """Post error to #alerts."""
    channel = bot.get_channel(ALERTS_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(ALERTS_CHANNEL_ID)
        except Exception:
            return
    await channel.send(f"**WhatsApp Scrape Error**\n{error}")


def register_whatsapp_sync(scheduler, bot=None):
    """Register WhatsApp sync jobs with the scheduler.

    - Daily at 10:00 AM UK: Playwright scrape of WhatsApp Web
    - Daily at 10:30 AM UK: Gmail fallback scan for manual exports
    """
    scheduler.add_job(
        whatsapp_web_scrape,
        'cron',
        hour=10,
        minute=0,
        timezone="Europe/London",
        id="whatsapp_web_scrape",
        max_instances=1,
        coalesce=True,
        args=[bot],
    )
    logger.info("Registered WhatsApp Web scrape (daily 10:00 AM UK)")

    scheduler.add_job(
        whatsapp_export_scan,
        'cron',
        hour=10,
        minute=30,
        timezone="Europe/London",
        id="whatsapp_export_scan",
        max_instances=1,
        coalesce=True,
        args=[bot],
    )
    logger.info("Registered WhatsApp Gmail scan fallback (daily 10:30 AM UK)")
