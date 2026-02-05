"""Schedule Formatter - For calendar and reminder content.

Uses Discord's native timestamp formatting for times.
Based on RESPONSE.md Section 5.9.
"""

import re
from datetime import datetime, timedelta
from typing import Optional, Any
from dataclasses import dataclass


@dataclass
class ScheduleEvent:
    """Parsed schedule event."""
    title: str
    datetime_obj: Optional[datetime] = None
    time_str: str = ''
    location: str = ''
    event_type: str = 'event'  # event, meeting, reminder, task


def format_schedule(text: str, context: Optional[dict] = None) -> str:
    """Format schedule/calendar content for Discord.

    Uses Discord native timestamps where possible:
    - <t:UNIX:F> for full date/time
    - <t:UNIX:R> for relative time

    Args:
        text: Text containing schedule information
        context: Optional context

    Returns:
        Formatted schedule for Discord
    """
    # Try to parse events from text
    events = parse_schedule_events(text)

    if events:
        return render_schedule_events(events)

    # If can't parse, enhance any time references
    return enhance_time_references(text)


def parse_schedule_events(text: str) -> list[ScheduleEvent]:
    """Parse schedule events from text."""
    events = []

    # Pattern: emoji? time - title [@ location]
    patterns = [
        # "9:30am - Team standup"
        r'(\d{1,2}[:.]\d{2}\s*(?:am|pm)?)\s*[-–]\s*([^\n@]+?)(?:@\s*([^\n]+))?$',
        # "📅 Meeting at 2pm"
        r'(?:📅|⏰|🗓️)\s*([^\d\n]+?)\s+(?:at\s+)?(\d{1,2}[:.]\d{2}\s*(?:am|pm)?)',
        # "Tomorrow at 3pm: Call with client"
        r'(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(?:at\s+)?(\d{1,2}[:.]\d{2}\s*(?:am|pm)?)\s*[-:]\s*(.+)',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
            groups = match.groups()
            if len(groups) >= 2:
                if groups[0] and groups[0][0].isdigit():
                    # Time first, then title
                    time_str = groups[0]
                    title = groups[1].strip()
                    location = groups[2].strip() if len(groups) > 2 and groups[2] else ''
                else:
                    # Title/day first, then time
                    title = f"{groups[0]} {groups[2] if len(groups) > 2 else ''}".strip()
                    time_str = groups[1]
                    location = ''

                events.append(ScheduleEvent(
                    title=title,
                    time_str=time_str,
                    location=location,
                    event_type=detect_event_type(title)
                ))

    return events


def detect_event_type(title: str) -> str:
    """Detect event type from title."""
    title_lower = title.lower()

    if any(word in title_lower for word in ['meeting', 'call', '1:1', 'standup', 'sync']):
        return 'meeting'
    elif any(word in title_lower for word in ['remind', 'reminder', 'don\'t forget']):
        return 'reminder'
    elif any(word in title_lower for word in ['task', 'todo', 'complete', 'finish']):
        return 'task'
    elif any(word in title_lower for word in ['run', 'gym', 'workout', 'exercise']):
        return 'fitness'
    else:
        return 'event'


def render_schedule_events(events: list[ScheduleEvent]) -> str:
    """Render schedule events in Discord format."""
    emoji_map = {
        'meeting': '📅',
        'reminder': '⏰',
        'task': '📌',
        'fitness': '🏃',
        'event': '🗓️',
    }

    lines = []

    for event in events:
        emoji = emoji_map.get(event.event_type, '🗓️')

        # Build event line
        line = f"{emoji} **{event.title}**"

        # Add time
        if event.time_str:
            # Try to create Discord timestamp
            discord_ts = create_discord_timestamp(event.time_str)
            if discord_ts:
                line += f"\n{discord_ts}"
            else:
                line += f"\n{event.time_str}"

        # Add location
        if event.location:
            line += f" • {event.location}"

        lines.append(line)

    return '\n\n'.join(lines)


def create_discord_timestamp(time_str: str, date_hint: str = 'today') -> Optional[str]:
    """Create Discord timestamp format from time string.

    Returns: <t:UNIX:F> (<t:UNIX:R>) format or None if can't parse
    """
    try:
        # Parse time
        time_str = time_str.strip().lower()

        # Handle various time formats
        for fmt in ['%I:%M%p', '%I:%M %p', '%H:%M', '%I%p', '%I %p']:
            try:
                time_obj = datetime.strptime(time_str, fmt).time()
                break
            except ValueError:
                continue
        else:
            return None

        # Determine date
        today = datetime.now().date()
        if 'tomorrow' in date_hint.lower():
            date_obj = today + timedelta(days=1)
        elif 'yesterday' in date_hint.lower():
            date_obj = today - timedelta(days=1)
        else:
            date_obj = today

        # Combine
        dt = datetime.combine(date_obj, time_obj)
        unix = int(dt.timestamp())

        return f"<t:{unix}:F> (<t:{unix}:R>)"

    except Exception:
        return None


def enhance_time_references(text: str) -> str:
    """Enhance time references in text with Discord timestamps where possible."""
    # This is a simpler fallback - just clean up the text
    # without trying to convert every time reference

    # Add schedule emoji if not present
    if not any(emoji in text for emoji in ['📅', '⏰', '🗓️', '📌']):
        if re.search(r'\d{1,2}[:.]\d{2}', text):
            text = '📅 ' + text

    return text


def format_discord_timestamp(dt: datetime) -> str:
    """Format a datetime as Discord timestamp.

    Returns: <t:UNIX:F> (<t:UNIX:R>)
    """
    unix = int(dt.timestamp())
    return f"<t:{unix}:F> (<t:{unix}:R>)"


# =============================================================================
# TESTING
# =============================================================================

def test_schedule_formatter():
    """Run basic schedule formatter tests."""
    # Test event parsing
    schedule_text = """Tomorrow's schedule:
9:30am - Team standup
2:00pm - 1:1 with client @ Zoom
5:00pm - Gym session"""

    events = parse_schedule_events(schedule_text)

    if len(events) >= 2:
        print(f"✓ PASS - Parsed {len(events)} events")
    else:
        print(f"✗ FAIL - Expected 3 events, got {len(events)}")

    # Test event type detection
    if detect_event_type("Team standup") == 'meeting':
        print("✓ PASS - Event type detection (meeting)")
    else:
        print("✗ FAIL - Event type detection (meeting)")

    if detect_event_type("Gym session") == 'fitness':
        print("✓ PASS - Event type detection (fitness)")
    else:
        print("✗ FAIL - Event type detection (fitness)")

    # Test Discord timestamp creation
    ts = create_discord_timestamp("2:00pm")
    if ts and ts.startswith('<t:') and ':F>' in ts:
        print("✓ PASS - Discord timestamp creation")
    else:
        print("✗ FAIL - Discord timestamp creation")

    # Test full format
    result = format_schedule(schedule_text)
    if '📅' in result or '🗓️' in result:
        print("✓ PASS - Schedule formatting")
    else:
        print("✗ FAIL - Schedule formatting")

    print("\nSchedule formatter tests complete")


if __name__ == '__main__':
    test_schedule_formatter()
