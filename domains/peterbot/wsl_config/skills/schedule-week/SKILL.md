# Schedule Week

## Purpose
Show this week's calendar overview and upcoming events.

## Triggers
- "this week", "week ahead", "upcoming schedule"
- "what's on this week", "my week"
- "next few days", "coming up"

## Schedule
- 18:00 Sun UK (weekly preview)

## Data Source
Hadley API: `curl http://172.19.64.1:8100/calendar/week`

## Pre-fetcher
`get_schedule_week_data()` - fetches:
- All events for next 7 days
- Grouped by day
- Event details: title, time, location

## Output Format

```
📅 **Week Ahead**

**Monday 3rd**
• 09:00 Team standup
• 14:00-16:00 Workshop

**Tuesday 4th**
• 10:00 1:1 with Sarah
• 15:30 Client demo

**Wednesday 5th**
• No meetings ✓

**Thursday 6th**
• 09:00 Team standup
• 11:00 Interview - Jane Doe
• 13:00 Lunch with Mike

**Friday 7th**
• 09:00 Team standup
• 16:00 Week retro

---
{total} events across {days_with_events} days
```

## Guidelines
- **Never show raw JSON** - only present the formatted human-readable output
- Group by day with clear headers
- Show "No meetings ✓" for clear days
- Abbreviate recurring events (don't repeat full details)
- For multi-day events, show on first day with "(until {end_day})"
- Max 5 events per day in summary, then "+N more"
- Weekend events only if they exist

## Conversational
Yes - follow-ups:
- "What's on Wednesday?"
- "When's my next free afternoon?"
- "Any client meetings this week?"
- "Show me Thursday in detail"
