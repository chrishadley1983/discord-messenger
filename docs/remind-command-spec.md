# /remind Command Specification

## Overview

Add one-off reminder capability to Peter using APScheduler's `date` trigger. Reminders trigger Peter with a prompt at the specified time, allowing him to use existing skills.

---

## User Interface

### Natural Language Input
```
"Remind me at 9am tomorrow to check traffic to Brickstop"
"Set a reminder for 2pm to take medication"
"At 6pm remind me to call mum"
"Reminder: Monday 8am - submit tax return"
```

### Peter's Response
```
✅ Reminder set for Sun 1 Feb 09:00 UK

> Check traffic to Brickstop

I'll ping you in #reminders when it's time.
```

### When Reminder Fires
Peter receives the prompt and acts on it:
```
🔔 Reminder for @Chris:

> Check traffic to Brickstop

[Peter then executes the task or prompts user]
```

---

## Architecture

### Components

```
discord-messenger/
├── domains/peterbot/
│   ├── reminders/
│   │   ├── __init__.py
│   │   ├── parser.py        # NLP parsing of reminder text
│   │   ├── store.py         # Supabase persistence
│   │   ├── scheduler.py     # APScheduler job management
│   │   └── executor.py      # Fires reminder back to Peter
│   └── router.py            # Add reminder intent detection
```

### Database Schema (Required)

```sql
CREATE TABLE reminders (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    task TEXT NOT NULL,
    run_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    fired_at TIMESTAMPTZ
);

CREATE INDEX idx_reminders_pending ON reminders(run_at) WHERE fired_at IS NULL;
```

### Data Flow

```
1. User: "Remind me at 9am to check traffic"
           ↓
2. Peter detects reminder intent
           ↓
3. parser.py extracts: {time: "09:00", date: "tomorrow", task: "check traffic"}
           ↓
4. scheduler.py adds APScheduler job with date trigger
           ↓
5. [Time passes...]
           ↓
6. APScheduler fires → executor.py
           ↓
7. executor.py sends message to Peter's channel as system prompt
           ↓
8. Peter handles "check traffic" using existing skills
```

---

## Implementation

### 1. Reminder Parser (`reminders/parser.py`)

```python
"""Parse natural language reminders into structured data."""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dataclasses import dataclass

@dataclass
class ParsedReminder:
    task: str
    run_at: datetime
    channels: list[str]  # Where to send reminder
    raw_time: str  # Original time string for display

def parse_reminder(text: str, now: datetime = None) -> ParsedReminder | None:
    """
    Parse reminder from natural language.

    Examples:
    - "at 9am tomorrow check traffic"
    - "remind me 2pm to take meds"
    - "Monday 8am submit tax return"
    """
    now = now or datetime.now(ZoneInfo("Europe/London"))

    # Time patterns
    time_pattern = r'(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)'
    date_pattern = r'(tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec))'

    # Extract time
    time_match = re.search(time_pattern, text, re.IGNORECASE)
    if not time_match:
        return None

    raw_time = time_match.group(1)
    hour, minute = _parse_time(raw_time)

    # Extract date (default: today if time is future, else tomorrow)
    date_match = re.search(date_pattern, text, re.IGNORECASE)
    target_date = _parse_date(date_match.group(1) if date_match else None, now)

    # Combine into datetime
    run_at = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # If time has passed today, assume tomorrow
    if run_at <= now and not date_match:
        run_at += timedelta(days=1)

    # Extract task (remove time/date phrases)
    task = text
    task = re.sub(time_pattern, '', task, flags=re.IGNORECASE)
    task = re.sub(date_pattern, '', task, flags=re.IGNORECASE)
    task = re.sub(r'\b(remind me|reminder|at|to|set a)\b', '', task, flags=re.IGNORECASE)
    task = re.sub(r'\s+', ' ', task).strip()

    return ParsedReminder(
        task=task,
        run_at=run_at,
        channels=["discord"],  # Default, can be extended
        raw_time=run_at.strftime("%a %d %b %H:%M")
    )

def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse time string to (hour, minute)."""
    time_str = time_str.lower().strip()

    # Handle "9am", "9:30pm", "14:00"
    is_pm = 'pm' in time_str
    is_am = 'am' in time_str
    time_str = re.sub(r'[ap]m', '', time_str).strip()

    if ':' in time_str:
        hour, minute = map(int, time_str.split(':'))
    else:
        hour = int(time_str)
        minute = 0

    if is_pm and hour < 12:
        hour += 12
    elif is_am and hour == 12:
        hour = 0

    return hour, minute

def _parse_date(date_str: str | None, now: datetime) -> datetime:
    """Parse date string to datetime."""
    if not date_str:
        return now

    date_str = date_str.lower()

    if date_str == 'today':
        return now
    elif date_str == 'tomorrow':
        return now + timedelta(days=1)

    # Day names
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    if date_str in days:
        target_day = days.index(date_str)
        current_day = now.weekday()
        days_ahead = (target_day - current_day) % 7
        if days_ahead == 0:
            days_ahead = 7  # Next week if same day
        return now + timedelta(days=days_ahead)

    # Date like "1st Feb" - parse with current year
    # (extend as needed)
    return now
```

### 2. Reminder Store (`reminders/store.py`)

```python
"""Supabase persistence for reminders."""

from datetime import datetime
import httpx
from config import SUPABASE_URL, SUPABASE_KEY
from logger import logger

def _headers():
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
    """Persist reminder to Supabase."""
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
    """Mark reminder as fired (keeps history)."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(
                f"{SUPABASE_URL}/rest/v1/reminders?id=eq.{reminder_id}",
                headers=_headers(),
                json={"fired_at": datetime.utcnow().isoformat()},
                timeout=10
            )
            response.raise_for_status()
            return True
    except Exception as e:
        logger.error(f"Failed to mark reminder fired: {e}")
        return False

async def delete_reminder(reminder_id: str) -> bool:
    """Delete a cancelled reminder."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"{SUPABASE_URL}/rest/v1/reminders?id=eq.{reminder_id}",
                headers=_headers(),
                timeout=10
            )
            response.raise_for_status()
            return True
    except Exception as e:
        logger.error(f"Failed to delete reminder: {e}")
        return False

async def get_pending_reminders() -> list[dict]:
    """Fetch all unfired reminders (for startup reload)."""
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
    """Fetch pending reminders for a specific user."""
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
```

### 4. Reminder Scheduler (`reminders/scheduler.py`)

```python
"""Manage reminder jobs with APScheduler."""

from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from dateutil.parser import parse as parse_datetime

from logger import logger
from .store import save_reminder, delete_reminder, get_pending_reminders

async def add_reminder(
    scheduler: AsyncIOScheduler,
    reminder_id: str,
    run_at: datetime,
    task: str,
    user_id: int,
    channel_id: int,
    executor_func
) -> str:
    """
    Add a one-off reminder job.

    Returns: job_id for cancellation
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

    logger.info(f"Added reminder {reminder_id}: '{task}' at {run_at}")
    return job.id

async def cancel_reminder(scheduler: AsyncIOScheduler, reminder_id: str) -> bool:
    """Cancel a pending reminder."""
    try:
        scheduler.remove_job(reminder_id)
        await delete_reminder(reminder_id)
        logger.info(f"Cancelled reminder {reminder_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to cancel reminder {reminder_id}: {e}")
        return False

async def reload_pending_reminders(scheduler: AsyncIOScheduler, executor_func) -> int:
    """
    Reload all pending reminders from Supabase into APScheduler.

    Call this on bot startup to restore reminders after restart.
    Returns count of reminders loaded.
    """
    pending = await get_pending_reminders()
    now = datetime.now(timezone.utc)
    loaded = 0

    for r in pending:
        run_at = parse_datetime(r["run_at"])

        # Skip if already past (will be cleaned up separately)
        if run_at <= now:
            logger.warning(f"Skipping past reminder {r['id']}: was due {run_at}")
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
            loaded += 1
        except Exception as e:
            logger.error(f"Failed to reload reminder {r['id']}: {e}")

    logger.info(f"Reloaded {loaded} pending reminders from Supabase")
    return loaded
```

### 5. Reminder Executor (`reminders/executor.py`)

```python
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
    """
    Fire a reminder - send to channel and optionally trigger Peter.

    This function is called by APScheduler when the reminder time arrives.
    """
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            channel = await bot.fetch_channel(channel_id)

        user_mention = f"<@{user_id}>"

        # Post reminder notification
        await channel.send(
            f"**🔔 Reminder** {user_mention}\n\n> {task}"
        )

        # For actionable reminders (like "check traffic"), trigger Peter:
        if _is_actionable(task):
            await _trigger_peter(channel, task, user_id, bot)

        logger.info(f"Fired reminder {reminder_id}: {task}")

    except Exception as e:
        logger.error(f"Failed to execute reminder {reminder_id}: {e}")

    finally:
        # Mark as fired in Supabase (keeps history, prevents re-fire on restart)
        await mark_reminder_fired(reminder_id)

def _is_actionable(task: str) -> bool:
    """Check if task should trigger Peter to act, not just notify."""
    actionable_keywords = [
        'check', 'send', 'post', 'update', 'fetch', 'get',
        'traffic', 'weather', 'briefing', 'summary'
    ]
    task_lower = task.lower()
    return any(kw in task_lower for kw in actionable_keywords)

async def _trigger_peter(channel, task: str, user_id: int, bot):
    """Inject task into Peter's handler as a system-triggered request."""
    from domains.peterbot.router import handle_reminder_task

    await handle_reminder_task(
        channel=channel,
        task=task,
        user_id=user_id,
        bot=bot
    )
```

### 6. Router Integration (`router.py` changes)

```python
# Add to existing router.py

from .reminders.parser import parse_reminder
from .reminders.scheduler import add_reminder, cancel_reminder, reload_pending_reminders
from .reminders.store import get_user_reminders
from .reminders.executor import execute_reminder
import uuid

async def handle_reminder_intent(message, content: str, scheduler, bot):
    """Handle reminder-related requests."""
    content_lower = content.lower()

    # List reminders
    if content_lower in ['list reminders', 'show reminders', 'my reminders']:
        reminders = await get_user_reminders(user_id=message.author.id)
        if not reminders:
            return "No active reminders."

        lines = ["**Your reminders:**\n"]
        for r in reminders:
            from dateutil.parser import parse as parse_dt
            run_at = parse_dt(r['run_at'])
            lines.append(f"• {run_at.strftime('%a %d %b %H:%M')} - {r['task']}")
            lines.append(f"  `cancel: {r['id'][:8]}`")
        return "\n".join(lines)

    # Cancel reminder
    if content_lower.startswith('cancel reminder'):
        reminder_id_partial = content.split()[-1]
        reminders = await get_user_reminders(user_id=message.author.id)
        for r in reminders:
            if r['id'].startswith(reminder_id_partial):
                if await cancel_reminder(scheduler, r['id']):
                    return f"✅ Cancelled reminder: {r['task']}"
        return "Reminder not found."

    # Set new reminder
    parsed = parse_reminder(content)
    if not parsed:
        return None  # Not a reminder request

    reminder_id = f"remind_{uuid.uuid4().hex[:8]}"

    # Create executor wrapper with bot reference
    async def executor_wrapper(task, user_id, channel_id, rid):
        await execute_reminder(task, user_id, channel_id, rid, bot)

    await add_reminder(
        scheduler=scheduler,
        reminder_id=reminder_id,
        run_at=parsed.run_at,
        task=parsed.task,
        user_id=message.author.id,
        channel_id=message.channel.id,
        executor_func=executor_wrapper
    )

    return f"✅ **Reminder set for {parsed.raw_time}**\n\n> {parsed.task}"

async def handle_reminder_task(channel, task: str, user_id: int, bot):
    """Handle an actionable reminder by processing it as a Peter request."""
    # Implementation depends on your router structure
    # Option 1: Call existing skill lookup
    # Option 2: Send as synthetic message to handle_message()
    pass
```

### 7. Bot Startup (`bot.py` changes)

```python
# In bot.py on_ready or startup

from domains.peterbot.reminders.scheduler import reload_pending_reminders
from domains.peterbot.reminders.executor import execute_reminder

async def on_ready():
    # ... existing startup code ...

    # Reload any reminders that were pending before restart
    async def executor_wrapper(task, user_id, channel_id, rid):
        await execute_reminder(task, user_id, channel_id, rid, bot)

    count = await reload_pending_reminders(scheduler, executor_wrapper)
    logger.info(f"Bot ready. Reloaded {count} pending reminders.")
```

---

## Example Conversations

### Setting a Reminder
```
User: Remind me at 9am tomorrow to check traffic to Brickstop
Peter: ✅ Reminder set for Sun 01 Feb 09:00

        > check traffic to Brickstop
```

### When It Fires
```
Peter: 🔔 Reminder @Chris

        > check traffic to Brickstop

        Checking traffic now...

        [Peter executes traffic skill and posts results]
```

### Listing Reminders
```
User: Show my reminders
Peter: **Your reminders:**

        • Sun 01 Feb 09:00 - check traffic to Brickstop
          `cancel: remind_a1b2`
        • Mon 02 Feb 14:00 - call dentist
          `cancel: remind_c3d4`
```

### Cancelling
```
User: Cancel reminder a1b2
Peter: ✅ Cancelled reminder: check traffic to Brickstop
```

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `domains/peterbot/reminders/__init__.py` | Create |
| `domains/peterbot/reminders/parser.py` | Create |
| `domains/peterbot/reminders/store.py` | Create - Supabase persistence |
| `domains/peterbot/reminders/scheduler.py` | Create |
| `domains/peterbot/reminders/executor.py` | Create |
| `domains/peterbot/router.py` | Add reminder intent handling |
| `bot.py` | Add startup reload + pass scheduler to router |
| **Supabase** | Run `CREATE TABLE reminders` migration |

---

## Testing

```python
def test_parse_reminder():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 1, 31, 22, 0, tzinfo=ZoneInfo("Europe/London"))

    # Test basic parsing
    r = parse_reminder("remind me at 9am tomorrow to check traffic", now)
    assert r.task == "check traffic"
    assert r.run_at.hour == 9
    assert r.run_at.day == 1  # Feb 1

    # Test day name
    r = parse_reminder("Monday 8am submit tax return", now)
    assert r.task == "submit tax return"
    assert r.run_at.weekday() == 0  # Monday

async def test_reminder_persistence():
    """Test Supabase save/load cycle."""
    from domains.peterbot.reminders.store import (
        save_reminder, get_pending_reminders, mark_reminder_fired, delete_reminder
    )

    test_id = "test_remind_123"
    run_at = datetime.now(timezone.utc) + timedelta(hours=1)

    # Save
    assert await save_reminder(test_id, 12345, 67890, "test task", run_at)

    # Retrieve
    pending = await get_pending_reminders()
    assert any(r["id"] == test_id for r in pending)

    # Mark fired
    assert await mark_reminder_fired(test_id)

    # Should no longer be in pending
    pending = await get_pending_reminders()
    assert not any(r["id"] == test_id for r in pending)

    # Cleanup
    await delete_reminder(test_id)
```

---

## Summary

- Uses APScheduler's built-in `date` trigger - auto-deletes after firing
- Natural language parsing for times/dates
- Fires reminder back through Peter so he can use existing skills
- No file changes needed (unlike SCHEDULE.md approach)
- List and cancel support
- Optional Supabase persistence for restart resilience
