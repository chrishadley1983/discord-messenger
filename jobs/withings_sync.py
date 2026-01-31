"""Withings sync scheduled job.

Syncs latest weight data from Withings API to the database.
Runs before the morning message to ensure fresh data.
"""

from logger import logger


async def sync_withings_weight():
    """Fetch latest weight from Withings and store in database."""
    try:
        from domains.nutrition.services.withings import get_weight

        logger.info("Starting Withings sync...")
        result = await get_weight()

        if result.get("error"):
            logger.error(f"Withings sync failed: {result['error']}")
            return {"success": False, "error": result["error"]}

        if result.get("weight_kg"):
            logger.info(f"Withings sync complete: {result['weight_kg']}kg from {result['date']}")
            return {"success": True, "weight_kg": result["weight_kg"], "date": result["date"]}
        else:
            logger.warning("Withings sync: no weight data returned")
            return {"success": False, "error": "No weight data"}

    except Exception as e:
        logger.error(f"Withings sync error: {e}")
        return {"success": False, "error": str(e)}


def register_withings_sync(scheduler):
    """Register the Withings sync job with the scheduler.

    Runs at 7:55 AM UK time, 5 minutes before the morning message.
    """
    scheduler.add_job(
        sync_withings_weight,
        'cron',
        hour=7,
        minute=55,
        timezone="Europe/London",
        id="withings_sync"
    )
    logger.info("Registered Withings sync job (7:55 AM UK)")
