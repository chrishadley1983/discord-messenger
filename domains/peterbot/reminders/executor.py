"""Execute reminders by triggering Peter."""

import discord

from logger import logger
from .store import mark_reminder_fired


async def execute_reminder(
    task: str,
    user_id: int,
    channel_id: int,
    reminder_id: str,
    bot: discord.Client
):
    """Fire a reminder - send to channel and optionally trigger Peter.

    This function is called by APScheduler when the reminder time arrives.

    Args:
        task: The reminder task/message
        user_id: Discord user ID to mention
        channel_id: Discord channel ID to post in
        reminder_id: The reminder ID
        bot: Discord bot instance
    """
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            channel = await bot.fetch_channel(channel_id)

        user_mention = f"<@{user_id}>"

        # Post reminder notification
        await channel.send(
            f"**Reminder** {user_mention}\n\n> {task}"
        )

        logger.info(f"Fired reminder {reminder_id}: {task}")

        # For actionable reminders (like "check traffic"), trigger Peter
        if _is_actionable(task):
            await _trigger_peter(channel, task, user_id, bot)

    except Exception as e:
        logger.error(f"Failed to execute reminder {reminder_id}: {e}")

    finally:
        # Mark as fired in Supabase (keeps history, prevents re-fire on restart)
        await mark_reminder_fired(reminder_id)


def _is_actionable(task: str) -> bool:
    """Check if task should trigger Peter to act, not just notify.

    Args:
        task: The reminder task text

    Returns:
        True if Peter should execute the task
    """
    actionable_keywords = [
        'check', 'send', 'post', 'update', 'fetch', 'get',
        'traffic', 'weather', 'briefing', 'summary', 'search',
        'look up', 'find'
    ]
    task_lower = task.lower()
    return any(kw in task_lower for kw in actionable_keywords)


async def _trigger_peter(channel, task: str, user_id: int, bot):
    """Inject task into Peter's handler as a system-triggered request.

    Args:
        channel: Discord channel
        task: The task to execute
        user_id: Discord user ID
        bot: Discord bot instance
    """
    try:
        # Import here to avoid circular imports
        from ..router import handle_message

        # Prefix so Peter knows this is from the reminder system
        reminder_prompt = f"[REMINDER TRIGGERED] The user set a reminder to: {task}. Please help them with this now."

        # Send task to Peter's message handler
        response = await handle_message(reminder_prompt, user_id, channel.id)

        if response and response != "(No response captured)":
            # Split long messages
            if len(response) > 2000:
                for i in range(0, len(response), 2000):
                    await channel.send(response[i:i+2000])
            else:
                await channel.send(response)

    except Exception as e:
        logger.error(f"Failed to trigger Peter for reminder: {e}")
        await channel.send(f"*I tried to help with '{task}' but encountered an error.*")
