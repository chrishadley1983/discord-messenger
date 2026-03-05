"""Octopus Energy sync jobs.

Two schedules:
- Daily at 10:00 AM UK: Pull half-hourly consumption, calculate costs, post to Discord #energy
- Weekly Sunday 9:00 AM UK: Post weekly digest with totals, trends, EV summary

Posts to Discord #energy channel via webhook (script handles its own posting).
"""

import asyncio
import subprocess
import sys
import os

from logger import logger

# Path to energy scripts (in hadley-bricks repo)
ENERGY_SCRIPTS_DIR = os.path.join(
    os.path.expanduser("~"), "claude-projects",
    "hadley-bricks-inventory-management", "scripts", "energy",
)


def _run_script(name: str, script: str, timeout: int = 300) -> tuple[bool, str]:
    """Run an energy script and return (success, output)."""
    script_path = os.path.join(ENERGY_SCRIPTS_DIR, script)
    if not os.path.exists(script_path):
        return False, f"Script not found: {script_path}"

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=ENERGY_SCRIPTS_DIR,
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


async def energy_daily_sync(bot=None):
    """Daily sync: pull consumption data from Octopus Energy API.

    The sync script handles Discord posting via webhook directly.
    """
    logger.info("Starting energy daily sync...")

    success, output = await asyncio.to_thread(
        _run_script, "Octopus Sync", "octopus_sync.py", timeout=180
    )
    logger.info(f"Octopus Sync: {'OK' if success else 'FAILED'}")

    if not success:
        logger.error(f"Energy sync failed: {output[-300:]}")

    return {"Octopus Sync": (success, output)}


async def energy_weekly_digest(bot=None):
    """Weekly digest: post summary of the week's energy usage."""
    logger.info("Starting energy weekly digest...")

    success, output = await asyncio.to_thread(
        _run_script, "Weekly Digest", "weekly_digest.py", timeout=120
    )
    logger.info(f"Weekly Digest: {'OK' if success else 'FAILED'}")

    if not success:
        logger.error(f"Energy weekly digest failed: {output[-300:]}")

    return {"Weekly Digest": (success, output)}


async def energy_monthly_billing(bot=None):
    """Monthly billing: query GraphQL for account balance and bill data."""
    logger.info("Starting energy monthly billing sync...")

    success, output = await asyncio.to_thread(
        _run_script, "Monthly Billing", "monthly_billing.py", timeout=120
    )
    logger.info(f"Monthly Billing: {'OK' if success else 'FAILED'}")

    if not success:
        logger.error(f"Energy monthly billing failed: {output[-300:]}")

    return {"Monthly Billing": (success, output)}


def register_energy_sync(scheduler, bot=None):
    """Register energy sync jobs with the scheduler.

    - Daily at 10:00 AM UK: Consumption sync + daily summary
    - Weekly Sunday 9:00 AM UK: Weekly digest
    - Monthly 1st at 10:30 AM UK: Billing data sync
    """
    scheduler.add_job(
        energy_daily_sync,
        'cron',
        hour=10,
        minute=0,
        timezone="Europe/London",
        id="energy_daily_sync",
        max_instances=1,
        coalesce=True,
        args=[bot],
    )
    logger.info("Registered energy daily sync (10:00 AM UK)")

    scheduler.add_job(
        energy_weekly_digest,
        'cron',
        day_of_week='sun',
        hour=9,
        minute=0,
        timezone="Europe/London",
        id="energy_weekly_digest",
        max_instances=1,
        coalesce=True,
        args=[bot],
    )
    logger.info("Registered energy weekly digest (Sunday 9:00 AM UK)")

    scheduler.add_job(
        energy_monthly_billing,
        'cron',
        day=1,
        hour=10,
        minute=30,
        timezone="Europe/London",
        id="energy_monthly_billing",
        max_instances=1,
        coalesce=True,
        args=[bot],
    )
    logger.info("Registered energy monthly billing (1st of month 10:30 AM UK)")
