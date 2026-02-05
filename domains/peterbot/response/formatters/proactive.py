"""Proactive Message Formatters - For Peter-initiated messages.

Formats morning briefings, reminders, and alerts with distinct styling.
Based on RESPONSE.md Section 11.
"""

from datetime import datetime
from typing import Optional, Any


def format_morning_briefing(data: dict) -> str:
    """Format morning briefing for Discord.

    Expected data structure:
    {
        'weather': {'temp': 8, 'condition': 'partly cloudy', 'running_note': 'Good running conditions.'},
        'calendar': {'summary': '2 meetings today: standup at 9:30, 1:1 at 14:00'},
        'ebay': {'summary': '3 items sold overnight (£47.50 total)'},
        'reminders': ['Max\\'s PE kit needs washing'],
        'timestamp': '06:45'
    }

    Output format (Section 11.1):
    ☀️ **Morning, Chris**

    **Weather** — 8°C, partly cloudy. Good running conditions.
    **Calendar** — 2 meetings today: standup at 9:30, 1:1 with client at 14:00
    **eBay** — 3 items sold overnight (£47.50 total)
    **Reminders** — Max's PE kit needs washing

    -# 06:45 • Proactive briefing
    """
    lines = ["☀️ **Morning, Chris**", ""]

    # Weather
    weather = data.get('weather', {})
    if weather:
        temp = weather.get('temp', '?')
        condition = weather.get('condition', 'Unknown')
        note = weather.get('running_note', '')
        weather_line = f"**Weather** — {temp}°C, {condition}."
        if note:
            weather_line += f" {note}"
        lines.append(weather_line)

    # Calendar
    calendar = data.get('calendar', {})
    if calendar:
        summary = calendar.get('summary', 'No events')
        lines.append(f"**Calendar** — {summary}")

    # eBay
    ebay = data.get('ebay', {})
    if ebay:
        summary = ebay.get('summary', 'No activity')
        lines.append(f"**eBay** — {summary}")

    # Reminders
    reminders = data.get('reminders', [])
    if reminders:
        reminder_text = reminders[0] if len(reminders) == 1 else f"{len(reminders)} items"
        lines.append(f"**Reminders** — {reminder_text}")
    else:
        lines.append("**Reminders** — None for today")

    # Timestamp footer
    timestamp = data.get('timestamp', datetime.now().strftime('%H:%M'))
    lines.extend(["", f"-# {timestamp} • Proactive briefing"])

    return '\n'.join(lines)


def format_reminder(task: str, scheduled_time: Optional[str] = None) -> str:
    """Format reminder notification for Discord.

    Output format (Section 11.2):
    ⏰ **Reminder**
    Put the bins out — collection tomorrow morning.

    -# Scheduled reminder
    """
    lines = [
        "⏰ **Reminder**",
        task,
        "",
        "-# Scheduled reminder"
    ]

    if scheduled_time:
        lines[-1] = f"-# Scheduled for {scheduled_time}"

    return '\n'.join(lines)


def format_alert(
    alert_type: str,
    message: str,
    actionable: bool = True,
    context: Optional[str] = None
) -> dict:
    """Format alert notification for Discord.

    Returns dict with 'content' and 'reactions' to add.

    Output format (Section 11.3):
    🔔 **eBay Alert**
    Someone made an offer on LEGO 42115 Lamborghini — £180 (asking £210).
    BrickLink average is £195.

    React ✅ to accept, ❌ to decline, or reply with a counter.

    -# Automatic offer notification
    """
    # Emoji map for alert types
    emoji_map = {
        'ebay': '🔔',
        'price': '💰',
        'stock': '📦',
        'error': '⚠️',
        'warning': '⚠️',
        'info': 'ℹ️',
        'success': '✅',
    }

    emoji = emoji_map.get(alert_type.lower(), '🔔')
    title = alert_type.replace('_', ' ').title()

    lines = [
        f"{emoji} **{title} Alert**",
        message,
    ]

    if context:
        lines.append(context)

    if actionable:
        lines.extend([
            "",
            "React ✅ to accept, ❌ to decline, or reply with a counter."
        ])

    lines.extend(["", f"-# Automatic {alert_type.lower()} notification"])

    return {
        'content': '\n'.join(lines),
        'reactions': ['✅', '❌'] if actionable else []
    }


def format_heartbeat(status: dict) -> str:
    """Format heartbeat status message.

    For periodic health check outputs.
    """
    lines = ["💓 **Heartbeat**"]

    if status.get('memory_ok'):
        lines.append("✅ Memory service healthy")
    else:
        lines.append("⚠️ Memory service issue")

    if status.get('api_ok'):
        lines.append("✅ Hadley API healthy")
    else:
        lines.append("⚠️ Hadley API issue")

    if status.get('pending_tasks'):
        lines.append(f"📋 {status['pending_tasks']} pending tasks")

    lines.extend(["", f"-# {datetime.now().strftime('%H:%M')} • Heartbeat"])

    return '\n'.join(lines)


# =============================================================================
# TESTING
# =============================================================================

def test_proactive_formatters():
    """Run basic proactive formatter tests."""
    # Test morning briefing
    briefing_data = {
        'weather': {'temp': 8, 'condition': 'partly cloudy', 'running_note': 'Good running conditions.'},
        'calendar': {'summary': '2 meetings today'},
        'ebay': {'summary': '3 items sold (£47.50)'},
        'reminders': ["PE kit"],
        'timestamp': '06:45'
    }

    result = format_morning_briefing(briefing_data)

    if '☀️' in result and 'Morning, Chris' in result and '06:45' in result:
        print("✓ PASS - Morning briefing format")
    else:
        print("✗ FAIL - Morning briefing format")
        print(f"  Result: {result[:100]}")

    # Test reminder
    result = format_reminder("Put the bins out")

    if '⏰' in result and 'Reminder' in result and 'bins' in result:
        print("✓ PASS - Reminder format")
    else:
        print("✗ FAIL - Reminder format")

    # Test alert
    result = format_alert(
        'ebay',
        'Someone made an offer on LEGO 42115 — £180',
        actionable=True
    )

    if '🔔' in result['content'] and '✅' in result['reactions']:
        print("✓ PASS - Alert format")
    else:
        print("✗ FAIL - Alert format")

    print("\nProactive formatter tests complete")


if __name__ == '__main__':
    test_proactive_formatters()
