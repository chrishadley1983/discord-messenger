"""Supabase persistence for reminders."""

from datetime import datetime
import httpx

from config import SUPABASE_URL, SUPABASE_KEY
from logger import logger


def _headers():
    """Get headers for Supabase API calls."""
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


async def save_reminder(
    reminder_id: str,
    user_id: int,
    channel_id: int,
    task: str,
    run_at: datetime
) -> bool:
    """Persist reminder to Supabase.

    Args:
        reminder_id: Unique reminder ID
        user_id: Discord user ID
        channel_id: Discord channel ID to post reminder in
        task: The reminder task/message
        run_at: When to fire the reminder

    Returns:
        True if saved successfully
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase not configured, reminder not persisted")
        return True  # Allow in-memory only operation

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SUPABASE_URL}/rest/v1/reminders",
                headers=_headers(),
                json={
                    "id": reminder_id,
                    "user_id": user_id,
                    "channel_id": channel_id,
                    "task": task,
                    "run_at": run_at.isoformat()
                },
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Saved reminder {reminder_id} to Supabase")
            return True
    except Exception as e:
        logger.error(f"Failed to save reminder: {e}")
        return False


async def mark_reminder_fired(reminder_id: str) -> bool:
    """Mark reminder as fired (keeps history, prevents re-fire on restart).

    Args:
        reminder_id: The reminder ID to mark

    Returns:
        True if marked successfully
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return True

    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/reminders?id=eq.{reminder_id}",
                headers=_headers(),
                json={"fired_at": datetime.utcnow().isoformat()},
                timeout=10
            )
            response.raise_for_status()
            logger.debug(f"Marked reminder {reminder_id} as fired")
            return True
    except Exception as e:
        logger.error(f"Failed to mark reminder fired: {e}")
        return False


async def delete_reminder(reminder_id: str) -> bool:
    """Delete a cancelled reminder.

    Args:
        reminder_id: The reminder ID to delete

    Returns:
        True if deleted successfully
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return True

    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{SUPABASE_URL}/rest/v1/reminders?id=eq.{reminder_id}",
                headers=_headers(),
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Deleted reminder {reminder_id}")
            return True
    except Exception as e:
        logger.error(f"Failed to delete reminder: {e}")
        return False


async def get_pending_reminders() -> list[dict]:
    """Fetch all unfired reminders (for startup reload).

    Returns:
        List of pending reminder dicts
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/reminders?fired_at=is.null&select=*",
                headers=_headers(),
                timeout=10
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch pending reminders: {e}")
        return []


async def get_user_reminders(user_id: int) -> list[dict]:
    """Fetch pending reminders for a specific user.

    Args:
        user_id: Discord user ID

    Returns:
        List of pending reminder dicts for user, sorted by run_at
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/reminders?user_id=eq.{user_id}&fired_at=is.null&select=*&order=run_at",
                headers=_headers(),
                timeout=10
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch user reminders: {e}")
        return []
