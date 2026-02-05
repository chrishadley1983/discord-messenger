"""Reminder intent handler for Peter's router."""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from logger import logger
from .parser import parse_reminder, is_reminder_request
from .scheduler import add_reminder, cancel_reminder, reload_pending_reminders, poll_for_new_reminders
from .store import get_user_reminders
from .executor import execute_reminder

UK_TZ = ZoneInfo("Europe/London")


async def handle_reminder_intent(
    content: str,
    user_id: int,
    channel_id: int,
    scheduler: AsyncIOScheduler,
    bot
) -> str | None:
    """Handle reminder-related requests.

    Args:
        content: Message content
        user_id: Discord user ID
        channel_id: Discord channel ID
        scheduler: APScheduler instance
        bot: Discord bot instance

    Returns:
        Response string if handled, None if not a reminder request
    """
    content_lower = content.lower().strip()

    # List reminders
    if content_lower in ['list reminders', 'show reminders', 'my reminders', 'reminders']:
        return await _list_reminders(user_id)

    # Cancel reminder
    if content_lower.startswith('cancel reminder'):
        reminder_id_partial = content.split()[-1]
        return await _cancel_reminder(user_id, reminder_id_partial, scheduler)

    # Check if it looks like a reminder request
    if not is_reminder_request(content):
        return None

    # Try to parse as a new reminder
    parsed = parse_reminder(content)
    if not parsed:
        return None  # Not a valid reminder format

    # Generate unique ID
    reminder_id = f"remind_{uuid.uuid4().hex[:8]}"

    # Create executor wrapper with bot reference
    async def executor_wrapper(task, uid, cid, rid):
        await execute_reminder(task, uid, cid, rid, bot)

    try:
        await add_reminder(
            scheduler=scheduler,
            reminder_id=reminder_id,
            run_at=parsed.run_at,
            task=parsed.task,
            user_id=user_id,
            channel_id=channel_id,
            executor_func=executor_wrapper
        )

        return f"**Reminder set for {parsed.raw_time}**\n\n> {parsed.task}"

    except Exception as e:
        logger.error(f"Failed to add reminder: {e}")
        return f"Failed to set reminder: {e}"


async def _list_reminders(user_id: int) -> str:
    """List pending reminders for a user."""
    reminders = await get_user_reminders(user_id)

    if not reminders:
        return "No active reminders."

    lines = ["**Your reminders:**\n"]
    for r in reminders:
        from dateutil.parser import parse as parse_dt
        run_at = parse_dt(r['run_at'])
        # Convert to UK time for display
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=UK_TZ)
        else:
            run_at = run_at.astimezone(UK_TZ)

        lines.append(f"- {run_at.strftime('%a %d %b %H:%M')} - {r['task']}")
        lines.append(f"  `cancel reminder {r['id'][:8]}`")

    return "\n".join(lines)


async def _cancel_reminder(user_id: int, reminder_id_partial: str, scheduler) -> str:
    """Cancel a reminder by partial ID."""
    reminders = await get_user_reminders(user_id)

    for r in reminders:
        if r['id'].startswith(reminder_id_partial) or r['id'].endswith(reminder_id_partial):
            if await cancel_reminder(scheduler, r['id']):
                return f"Cancelled reminder: {r['task']}"
            else:
                return "Failed to cancel reminder."

    return "Reminder not found. Use `list reminders` to see your reminders."


async def reload_reminders_on_startup(scheduler: AsyncIOScheduler, bot) -> int:
    """Reload pending reminders from Supabase on bot startup.

    Args:
        scheduler: APScheduler instance
        bot: Discord bot instance

    Returns:
        Count of reminders loaded
    """
    async def executor_wrapper(task, user_id, channel_id, reminder_id):
        await execute_reminder(task, user_id, channel_id, reminder_id, bot)

    return await reload_pending_reminders(scheduler, executor_wrapper)


def start_reminder_polling(scheduler: AsyncIOScheduler, bot):
    """Start polling for new reminders every 60 seconds.

    This allows Peter (or external systems) to insert reminders into Supabase
    and have the bot pick them up without a restart.

    Args:
        scheduler: APScheduler instance
        bot: Discord bot instance
    """
    from apscheduler.triggers.interval import IntervalTrigger

    async def poll_task():
        async def executor_wrapper(task, user_id, channel_id, reminder_id):
            await execute_reminder(task, user_id, channel_id, reminder_id, bot)

        count = await poll_for_new_reminders(scheduler, executor_wrapper)
        if count > 0:
            logger.info(f"Polling picked up {count} new reminder(s)")

    scheduler.add_job(
        poll_task,
        trigger=IntervalTrigger(seconds=60),
        id="reminder_polling",
        name="Poll for new reminders",
        replace_existing=True
    )
    logger.info("Started reminder polling (every 60s)")
