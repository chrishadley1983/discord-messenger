"""School integration sync jobs.

Two schedules:
- Daily at 7:00 AM UK: Gmail parser (spellings + events from emails) + Arbor monitor
- Weekly Saturday 6:00 AM UK: Newsletter scraper + term date poller + Google Calendar sync

Posts summary to Discord #alerts channel.
"""

import asyncio
import subprocess
import sys
import os

from logger import logger

ALERTS_CHANNEL_ID = 1466019126194606286  # #alerts

# Path to school scripts (in hadley-bricks repo)
SCHOOL_SCRIPTS_DIR = os.path.join(
    os.path.expanduser("~"), "claude-projects",
    "hadley-bricks-inventory-management", "scripts", "school",
)


def _run_script(name: str, script: str, timeout: int = 300) -> tuple[bool, str]:
    """Run a school script and return (success, output)."""
    script_path = os.path.join(SCHOOL_SCRIPTS_DIR, script)
    if not os.path.exists(script_path):
        return False, f"Script not found: {script_path}"

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=SCHOOL_SCRIPTS_DIR,
        )
        output = result.stdout[-1000:] if result.stdout else ""
        if result.returncode != 0:
            error = result.stderr[-500:] if result.stderr else "Unknown error"
            return False, f"{output}\nERROR: {error}"
        return True, output
    except subprocess.TimeoutExpired:
        return False, f"Timeout after {timeout}s"
    except Exception as e:
        return False, str(e)


async def school_daily_sync(bot=None):
    """Daily sync: Gmail parser + Arbor monitor.

    Checks for new school emails (spellings, events) and Arbor notifications.
    """
    logger.info("Starting school daily sync...")

    results = {}

    # Run Gmail parser
    success, output = await asyncio.to_thread(
        _run_script, "Gmail Parser", "gmail_school_parser.py", timeout=120
    )
    results["Gmail Parser"] = (success, output)
    logger.info(f"Gmail Parser: {'OK' if success else 'FAILED'}")

    # Run Arbor portal scraper (balances, attendance, notices)
    success, output = await asyncio.to_thread(
        _run_script, "Arbor Scraper", "arbor_scraper.py", timeout=120
    )
    results["Arbor Scraper"] = (success, output)
    logger.info(f"Arbor Scraper: {'OK' if success else 'FAILED'}")

    # Run Arbor email monitor (parses Arbor notification emails)
    success, output = await asyncio.to_thread(
        _run_script, "Arbor Monitor", "arbor_monitor.py", timeout=120
    )
    results["Arbor Monitor"] = (success, output)
    logger.info(f"Arbor Monitor: {'OK' if success else 'FAILED'}")

    # Post summary to Discord
    if bot:
        await _post_summary(bot, "Daily School Sync", results)

    return results


async def school_weekly_sync(bot=None):
    """Weekly sync: term dates + newsletters + calendar sync.

    Polls for term date PDF changes, scrapes new newsletters, syncs to Google Calendar.
    """
    logger.info("Starting school weekly sync...")

    results = {}

    # Run term dates poller
    success, output = await asyncio.to_thread(
        _run_script, "Term Dates Poller", "term_dates_poller.py", timeout=180
    )
    results["Term Dates"] = (success, output)
    logger.info(f"Term Dates Poller: {'OK' if success else 'FAILED'}")

    # Run newsletter scraper
    success, output = await asyncio.to_thread(
        _run_script, "Newsletter Scraper", "newsletter_scraper.py", timeout=180
    )
    results["Newsletters"] = (success, output)
    logger.info(f"Newsletter Scraper: {'OK' if success else 'FAILED'}")

    # Run calendar sync
    success, output = await asyncio.to_thread(
        _run_script, "Calendar Sync", "calendar_sync.py", timeout=120
    )
    results["Calendar Sync"] = (success, output)
    logger.info(f"Calendar Sync: {'OK' if success else 'FAILED'}")

    # Post summary to Discord
    if bot:
        await _post_summary(bot, "Weekly School Sync", results)

    return results


async def _post_summary(bot, title: str, results: dict):
    """Post a summary of school sync results to #alerts."""
    try:
        all_pass = all(s for s, _ in results.values())
        emoji = "\u2705" if all_pass else "\u26a0\ufe0f"

        lines = [f"{emoji} **School Integration \u2014 {title}**", "```"]
        for name, (success, output) in results.items():
            status = "OK" if success else "FAILED"
            lines.append(f"  [{status}] {name}")
        lines.append("```")

        # Add details for failures
        failures = {k: v for k, v in results.items() if not v[0]}
        if failures:
            for name, (_, output) in failures.items():
                lines.append(f"**{name} error:** {output[:200]}")

        message = "\n".join(lines)

        channel = bot.get_channel(ALERTS_CHANNEL_ID)
        if not channel:
            channel = await bot.fetch_channel(ALERTS_CHANNEL_ID)
        if channel:
            await channel.send(message)
            logger.info(f"Posted school sync summary to #alerts")
    except Exception as e:
        logger.error(f"Failed to post school sync summary: {e}")


def register_school_sync(scheduler, bot=None):
    """Register school sync jobs with the scheduler.

    - Daily at 7:00 AM UK: Gmail parser + Arbor monitor
    - Weekly Saturday 6:00 AM UK: Newsletter + term dates + calendar sync
    """
    scheduler.add_job(
        school_daily_sync,
        'cron',
        hour=7,
        minute=0,
        timezone="Europe/London",
        id="school_daily_sync",
        max_instances=1,
        coalesce=True,
        args=[bot],
    )
    logger.info("Registered school daily sync (7:00 AM UK)")

    scheduler.add_job(
        school_weekly_sync,
        'cron',
        day_of_week='sat',
        hour=6,
        minute=0,
        timezone="Europe/London",
        id="school_weekly_sync",
        max_instances=1,
        coalesce=True,
        args=[bot],
    )
    logger.info("Registered school weekly sync (Saturday 6:00 AM UK)")
