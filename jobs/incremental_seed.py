"""Incremental Seed Import job.

Runs daily at 1am to load new calendar entries, emails, and GitHub activity
into Second Brain. Uses small limits for incremental updates.

Duplicates are automatically skipped by source_url check in runner.
"""

import asyncio

from logger import logger


async def incremental_seed_import():
    """Run incremental seed import for key adapters.

    Imports:
    - Calendar: 50 items (new events)
    - Email: 100 items (new emails, filtered)
    - GitHub: 30 items (new commits/repos)
    - Garmin: 30 items (recent activities/health data)

    Skips:
    - Bookmarks (manual process)
    """
    from domains.second_brain.seed.runner import run_seed_import, get_available_adapters

    # Import adapters to register them
    from domains.second_brain.seed.adapters import calendar, email, github, garmin

    adapters = get_available_adapters()

    # Define limits per adapter (incremental, not full backfill)
    adapter_limits = {
        "calendar-events": 50,
        "email-import": 100,
        "github-projects": 30,
        "garmin-activities": 30,
    }

    results = []
    total_imported = 0
    total_skipped = 0
    total_failed = 0

    for adapter_name, limit in adapter_limits.items():
        if adapter_name not in adapters:
            logger.warning(f"Adapter {adapter_name} not found, skipping")
            continue

        adapter_class = adapters[adapter_name]

        try:
            logger.info(f"Running incremental import: {adapter_name} (limit={limit})")

            # Configure adapter for incremental (shorter time window)
            # Note: adapters auto-skip duplicates via source_url check
            config = {}
            if adapter_name == "calendar-events":
                config = {"years_back": 0.1}  # ~5 weeks back
            elif adapter_name == "email-import":
                config = {"years_back": 0.1}  # ~5 weeks back only
            elif adapter_name == "github-projects":
                config = {}  # No time config, uses dedup
            elif adapter_name == "garmin-activities":
                config = {"years_back": 0.02}  # ~1 week of activities

            adapter = adapter_class(config)
            result = await run_seed_import(adapter, limit=limit)

            results.append(result)
            total_imported += result.items_imported
            total_skipped += result.items_skipped
            total_failed += result.items_failed

            logger.info(
                f"  {adapter_name}: {result.items_imported} imported, "
                f"{result.items_skipped} skipped, {result.items_failed} failed"
            )

        except Exception as e:
            logger.error(f"Adapter {adapter_name} failed: {e}")

    logger.info(
        f"Incremental seed complete: {total_imported} imported, "
        f"{total_skipped} skipped, {total_failed} failed"
    )

    return results


def register_incremental_seed(scheduler, bot=None):
    """Register the incremental seed job with the scheduler.

    Args:
        scheduler: APScheduler instance
        bot: Discord bot instance (not used, but kept for API consistency)
    """
    scheduler.add_job(
        incremental_seed_import,
        'cron',
        hour=1,
        minute=0,
        timezone="Europe/London",
        id="incremental_seed",
        max_instances=1,
        coalesce=True,
    )
    logger.info("Registered incremental seed job (daily at 1:00 AM UK)")
