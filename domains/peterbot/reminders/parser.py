"""Parse natural language reminders into structured data."""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from typing import Optional

UK_TZ = ZoneInfo("Europe/London")


@dataclass
class ParsedReminder:
    """Parsed reminder data."""
    task: str
    run_at: datetime
    channels: list[str]
    raw_time: str  # Original time string for display


def parse_reminder(text: str, now: datetime = None) -> Optional[ParsedReminder]:
    """Parse reminder from natural language.

    Examples:
    - "at 9am tomorrow check traffic"
    - "remind me 2pm to take meds"
    - "Monday 8am submit tax return"
    - "at 8:30am Sunday to check traffic to Brickstop"

    Args:
        text: Natural language reminder text
        now: Current time (defaults to now in UK timezone)

    Returns:
        ParsedReminder if successfully parsed, None otherwise
    """
    now = now or datetime.now(UK_TZ)
    text_lower = text.lower()

    # Check if this looks like a reminder request
    reminder_keywords = ['remind', 'reminder', 'at ', 'tomorrow', 'monday', 'tuesday',
                         'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    if not any(kw in text_lower for kw in reminder_keywords):
        return None

    # Time patterns - match HH:MM, HH.MM, or H am/pm formats
    time_pattern = r'(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?)'

    # Date patterns
    date_pattern = r'(tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)(?:\w*)?)'

    # Extract time
    time_match = re.search(time_pattern, text_lower)
    if not time_match:
        return None

    raw_time = time_match.group(1)
    hour, minute = _parse_time(raw_time)
    if hour is None:
        return None

    # Extract date (default: today if time is future, else tomorrow)
    date_match = re.search(date_pattern, text_lower)
    target_date = _parse_date(date_match.group(1) if date_match else None, now)

    # Combine into datetime
    run_at = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # If time has passed today and no explicit date, assume tomorrow
    if run_at <= now and not date_match:
        run_at += timedelta(days=1)

    # Extract task (remove time/date phrases and reminder keywords)
    task = text
    # Remove time
    task = re.sub(time_pattern, '', task, flags=re.IGNORECASE)
    # Remove date
    task = re.sub(date_pattern, '', task, flags=re.IGNORECASE)
    # Remove reminder keywords and common phrases
    task = re.sub(r'\b(remind me|reminder|remind|set a reminder|can you remind me)\b', '', task, flags=re.IGNORECASE)
    task = re.sub(r'\b(at|to|for|this morning|this afternoon|this evening|tonight)\b', '', task, flags=re.IGNORECASE)
    task = re.sub(r'\b(in the morning|in the afternoon|in the evening)\b', '', task, flags=re.IGNORECASE)
    task = re.sub(r'\b(please|can you|could you|peter|lets try again)\b', '', task, flags=re.IGNORECASE)
    # Remove am/pm that might be left over
    task = re.sub(r'\b(am|pm)\b', '', task, flags=re.IGNORECASE)
    # Clean up whitespace
    task = re.sub(r'\s+', ' ', task).strip()
    # Remove leading/trailing punctuation and dashes
    task = task.strip('.,;:!-–—')
    # Remove leading "to" if present after cleanup
    task = re.sub(r'^to\s+', '', task, flags=re.IGNORECASE).strip()

    if not task:
        return None

    return ParsedReminder(
        task=task,
        run_at=run_at,
        channels=["discord"],  # Default, can extend for WhatsApp etc
        raw_time=run_at.strftime("%a %d %b %H:%M")
    )


def _parse_time(time_str: str) -> tuple[Optional[int], int]:
    """Parse time string to (hour, minute).

    Args:
        time_str: Time string like "9am", "9:30pm", "14:00", "8.45"

    Returns:
        Tuple of (hour, minute), or (None, 0) if invalid
    """
    time_str = time_str.lower().strip()

    # Detect am/pm
    is_pm = 'pm' in time_str
    is_am = 'am' in time_str
    time_str = re.sub(r'[ap]m', '', time_str).strip()

    try:
        # Handle both : and . as separators
        if ':' in time_str or '.' in time_str:
            parts = re.split(r'[:.]', time_str)
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        else:
            hour = int(time_str)
            minute = 0
    except ValueError:
        return None, 0

    # Convert 12-hour to 24-hour
    if is_pm and hour < 12:
        hour += 12
    elif is_am and hour == 12:
        hour = 0

    # Validate
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None, 0

    return hour, minute


def _parse_date(date_str: Optional[str], now: datetime) -> datetime:
    """Parse date string to datetime.

    Args:
        date_str: Date string like "today", "tomorrow", "monday", "1st Feb"
        now: Current datetime

    Returns:
        Target date as datetime (time will be replaced later)
    """
    if not date_str:
        return now

    date_str = date_str.lower().strip()

    if date_str == 'today':
        return now
    elif date_str == 'tomorrow':
        return now + timedelta(days=1)

    # Day names
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    for i, day in enumerate(days):
        if date_str.startswith(day[:3]):  # Match first 3 chars
            target_day = i
            current_day = now.weekday()
            days_ahead = (target_day - current_day) % 7
            # If days_ahead is 0, it means today - keep it as 0 (same day)
            # Only go to next week if we explicitly need "next Monday" etc
            # For reminders, same day or tomorrow is more intuitive
            return now + timedelta(days=days_ahead)

    # Date like "1st Feb" - parse with current year
    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }

    # Match "1st Feb", "15th March", etc
    date_match = re.match(r'(\d{1,2})(?:st|nd|rd|th)?\s+(\w{3})', date_str)
    if date_match:
        day = int(date_match.group(1))
        month_str = date_match.group(2).lower()[:3]
        month = month_map.get(month_str)
        if month:
            year = now.year
            target = now.replace(year=year, month=month, day=day)
            # If date is in the past, use next year
            if target < now:
                target = target.replace(year=year + 1)
            return target

    return now


def is_reminder_request(text: str) -> bool:
    """Quick check if text looks like a reminder request.

    Args:
        text: Message text to check

    Returns:
        True if likely a reminder request
    """
    text_lower = text.lower()

    # Strong indicators
    if 'remind me' in text_lower or 'reminder' in text_lower:
        return True

    # Time + day patterns that suggest reminder
    has_time = bool(re.search(r'\d{1,2}(?::\d{2})?\s*(?:am|pm)?', text_lower))
    has_day = bool(re.search(r'(tomorrow|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday)', text_lower))

    return has_time and has_day
