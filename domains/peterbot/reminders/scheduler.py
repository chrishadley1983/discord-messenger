"""Manage reminder jobs with APScheduler."""

from datetime import datetime, timezone
from typing import Callable, Awaitable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from dateutil.parser import parse as parse_datetime

from logger import logger
from .store import save_reminder, delete_reminder, get_pending_reminders

# Track which reminder IDs are already scheduled in APScheduler
_scheduled_ids: set[str] = set()


async def add_reminder(
    scheduler: AsyncIOScheduler,
    reminder_id: str,
    run_at: datetime,
    task: str,
    user_id: int,
    channel_id: int,
    executor_func: Callable[..., Awaitable]
) -> str:
    """Add a one-off reminder job.

    Args:
        scheduler: APScheduler instance
        reminder_id: Unique reminder ID
        run_at: When to fire the reminder
        task: The reminder task/message
        user_id: Discord user ID
        channel_id: Discord channel ID
        executor_func: Async function to call when reminder fires

    Returns:
        job_id for cancellation

    Raises:
        Exception: If reminder fails to save to database
    """
    # Persist to Supabase first
    saved = await save_reminder(reminder_id, user_id, channel_id, task, run_at)
    if not saved:
        raise Exception("Failed to save reminder to database")

    # Add to APScheduler
    job = scheduler.add_job(
        executor_func,
        trigger=DateTrigger(run_date=run_at),
        args=[task, user_id, channel_id, reminder_id],
        id=reminder_id,
        name=f"reminder:{task[:30]}",
        replace_existing=True
    )

    _scheduled_ids.add(reminder_id)
    logger.info(f"Added reminder {reminder_id}: '{task}' at {run_at}")
    return job.id


async def cancel_reminder(scheduler: AsyncIOScheduler, reminder_id: str) -> bool:
    """Cancel a pending reminder.

    Args:
        scheduler: APScheduler instance
        reminder_id: The reminder ID to cancel

    Returns:
        True if cancelled successfully
    """
    try:
        scheduler.remove_job(reminder_id)
        await delete_reminder(reminder_id)
        logger.info(f"Cancelled reminder {reminder_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to cancel reminder {reminder_id}: {e}")
        return False


async def reload_pending_reminders(
    scheduler: AsyncIOScheduler,
    executor_func: Callable[..., Awaitable]
) -> int:
    """Reload all pending reminders from Supabase into APScheduler.

    Call this on bot startup to restore reminders after restart.

    Args:
        scheduler: APScheduler instance
        executor_func: Async function to call when reminders fire

    Returns:
        Count of reminders loaded
    """
    pending = await get_pending_reminders()
    now = datetime.now(timezone.utc)
    loaded = 0
    skipped = 0

    for r in pending:
        run_at = parse_datetime(r["run_at"])

        # Ensure timezone aware
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)

        # Skip if already past
        if run_at <= now:
            logger.warning(f"Skipping past reminder {r['id']}: was due {run_at}")
            skipped += 1
            continue

        try:
            scheduler.add_job(
                executor_func,
                trigger=DateTrigger(run_date=run_at),
                args=[r["task"], r["user_id"], r["channel_id"], r["id"]],
                id=r["id"],
                name=f"reminder:{r['task'][:30]}",
                replace_existing=True
            )
            _scheduled_ids.add(r["id"])
            loaded += 1
        except Exception as e:
            logger.error(f"Failed to reload reminder {r['id']}: {e}")

    logger.info(f"Reloaded {loaded} pending reminders from Supabase (skipped {skipped} past)")
    return loaded


async def poll_for_new_reminders(
    scheduler: AsyncIOScheduler,
    executor_func: Callable[..., Awaitable]
) -> int:
    """Poll Supabase for new reminders not yet in APScheduler.

    Call this periodically (e.g., every 60 seconds) to pick up reminders
    added externally (e.g., by Peter via curl).

    Args:
        scheduler: APScheduler instance
        executor_func: Async function to call when reminders fire

    Returns:
        Count of new reminders scheduled
    """
    pending = await get_pending_reminders()
    now = datetime.now(timezone.utc)
    added = 0

    for r in pending:
        # Skip if already scheduled
        if r["id"] in _scheduled_ids:
            continue

        run_at = parse_datetime(r["run_at"])

        # Ensure timezone aware
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)

        # Skip if already past
        if run_at <= now:
            continue

        try:
            scheduler.add_job(
                executor_func,
                trigger=DateTrigger(run_date=run_at),
                args=[r["task"], r["user_id"], r["channel_id"], r["id"]],
                id=r["id"],
                name=f"reminder:{r['task'][:30]}",
                replace_existing=True
            )
            _scheduled_ids.add(r["id"])
            added += 1
            logger.info(f"Picked up new reminder from Supabase: {r['id']} - {r['task'][:30]}")
        except Exception as e:
            logger.error(f"Failed to schedule new reminder {r['id']}: {e}")

    return added
