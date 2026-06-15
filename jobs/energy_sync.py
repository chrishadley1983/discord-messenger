"""Energy sync jobs — Octopus consumption, weekly digest, monthly billing.

Jun 2026: rewired from subprocess calls into the hadley-bricks repo to
in-process calls on domains.energy (consolidated module). Cross-repo script
dependencies silently killed the WhatsApp and school pipelines; energy now
lives in this repo. Exceptions propagate so _tracked_job records real
failures and #alerts fires.
"""

import asyncio

from logger import logger


async def energy_daily_sync(bot=None):
    """Daily half-hourly consumption + tariff sync (complete days only)."""
    logger.info("Starting energy daily sync (domains.energy)...")
    from domains.energy import octopus_sync
    await asyncio.to_thread(octopus_sync.main)
    logger.info("Energy daily sync complete")


async def energy_weekly_digest(bot=None):
    """Weekly 7-day recap to #energy."""
    logger.info("Starting energy weekly digest...")
    from domains.energy import weekly_digest
    await asyncio.to_thread(weekly_digest.main)
    logger.info("Energy weekly digest complete")


async def energy_monthly_billing(bot=None):
    """Monthly account balance/billing snapshot + tariff what-if to #energy."""
    logger.info("Starting energy monthly billing...")
    from domains.energy import monthly_billing, tariff_whatif
    await asyncio.to_thread(monthly_billing.main)
    result = await asyncio.to_thread(tariff_whatif.post_comparison)
    logger.info(f"Energy monthly billing complete (what-if: {str(result)[:120]})")


def register_energy_sync(scheduler, bot=None):
    """Register energy jobs: daily 10:00, weekly Sun 09:00, monthly 1st 10:30 UK."""
    scheduler.add_job(
        energy_daily_sync, 'cron', hour=10, minute=0,
        timezone="Europe/London", id="energy_daily_sync",
        max_instances=1, coalesce=True, args=[bot],
    )
    scheduler.add_job(
        energy_weekly_digest, 'cron', day_of_week='sun', hour=9, minute=0,
        timezone="Europe/London", id="energy_weekly_digest",
        max_instances=1, coalesce=True, args=[bot],
    )
    scheduler.add_job(
        energy_monthly_billing, 'cron', day=1, hour=10, minute=30,
        timezone="Europe/London", id="energy_monthly_billing",
        max_instances=1, coalesce=True, args=[bot],
    )
    logger.info("Energy sync jobs registered (daily 10:00, weekly Sun 09:00, monthly 1st 10:30 UK)")
