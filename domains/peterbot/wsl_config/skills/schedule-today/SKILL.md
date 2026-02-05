# Schedule Today

## Purpose
Show today's calendar events and agenda.

## Triggers
- "what's on today", "my schedule", "today's calendar"
- "what do I have today", "any meetings today"
- "what's my day look like"

## Schedule
- 08:00 UK daily (part of morning-briefing)

## Data Source
Hadley API: `curl http://172.19.64.1:8100/calendar/today`

## Pre-fetcher
`get_schedule_today_data()` - fetches:
- All events for today (midnight to midnight, UK time)
- Event details: title, time, location, attendees, description snippet

## Output Format

**If events exist:**
```
📅 **Today's Schedule** ({day}, {date})

• **09:00-09:30** Team standup
  📍 Zoom

• **11:00-12:00** Client call - Acme Corp
  📍 Meet • 👥 john@acme.com, sarah@company.com

• **14:00-15:30** Sprint planning
  📍 Office - Room 2B

{count} events today
```

**If calendar is clear:**
```
📅 No meetings today - calendar is clear!
```

## Guidelines
- **Never show raw JSON** - only present the formatted human-readable output
- Sort chronologically
- Show location if present (📍)
- Show attendees for meetings with others (👥) - max 3, then "+N more"
- Use 24h time format
- For all-day events, show "All day" instead of time
- Highlight current/next event if within 30 minutes
- For scheduled morning run, include brief weather note if available

## Conversational
Yes - follow-ups:
- "What's the client call about?"
- "Who's in the sprint planning?"
- "What time does {event} start?"
- "Am I free at 3pm?"
