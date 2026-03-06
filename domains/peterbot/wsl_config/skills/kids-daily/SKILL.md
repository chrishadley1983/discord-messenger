---
name: kids-daily
description: Daily kids briefing — today's and tomorrow's activities, kit needed, school notices, spellings
trigger:
  - "kids today"
  - "what are the kids doing"
  - "kids schedule"
  - "kids tomorrow"
  - "what do the kids need"
  - "kids activities"
scheduled: true
conversational: true
channel: "#peterbot"
whatsapp: true
---

# Kids Daily Briefing

## Purpose

Morning briefing covering TODAY and TOMORROW for Max and Emmie. Combines calendar events, clubs/activities from Supabase, school notices, spellings, and kit reminders into one scannable message.

Runs daily at 07:25 UK (before the school-run traffic report at 08:10).

## Data Sources

### 1. Clubs & Activities (Supabase `evening_clubs` table)

This is the source of truth for recurring activities. Query all active clubs:

```bash
curl -s "${SUPABASE_URL}/rest/v1/evening_clubs?is_active=eq.true&select=child_name,club_name,pickup_time,pickup_location,notes,weekday,time_category" \
  -H "apikey: ${SUPABASE_KEY}" \
  -H "Authorization: Bearer ${SUPABASE_KEY}"
```

- `weekday`: 0=Monday, 1=Tuesday, ... 6=Sunday
- `time_category`: "morning" (during school) or "afternoon" (after school / evening)
- Filter by today's weekday and tomorrow's weekday

### 2. Uniform / PE Days

Hardcoded in `jobs/school_run.py`:
- **Max**: PE on Monday (0), Thursday (3)
- **Emmie**: PE on Wednesday (2), Thursday (3)

Include uniform info for today and tomorrow.

### 3. Calendar Events (Today + Tomorrow)

Fetch from Hadley API:

```bash
# Today's events
curl -s "http://172.19.64.1:8100/calendar/today"

# Tomorrow's events (use /calendar/range)
curl -s "http://172.19.64.1:8100/calendar/range?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD"
```

Filter calendar events for kids-related items. Keywords to match: "Max", "Emmie", "Swimming", "Piano", "Tutoring", "School", "Club", "Party", "Playdate", any child's friend name.

### 4. School Data

Search Second Brain for recent school notices:

```
mcp__second-brain__search_knowledge("Stocks Green school this week", limit=5)
```

Also check for any school events from the calendar (trips, non-uniform days, etc.).

### 5. Spellings

The school-run data fetcher already calculates the current spelling week. If pre-fetched data is available, use it. Otherwise note the spellings are in the weekly spellings post.

## Children

- **Max** (Year 2) — emoji: boy
- **Emmie** (Year 4) — emoji: girl

## Output Format

```
KIDS DAILY — {Day}, {Date}

TODAY
Max (Year 2): School → Swimming 4pm
Emmie (Year 4): School → Tutoring 4pm

Uniform: Max — PE kit (if PE day), Emmie — school uniform
Kit today: Swimming kit + towel (Max only — Emmie has tutoring)
Reminders: [any school notices relevant to today]

TOMORROW — {Day}
Max: School → Swimming 4pm
Emmie: School → Swimming 4pm

Pack tonight: Swimming kit + towel (both)
Uniform tomorrow: [PE kit if applicable]
Heads up: [anything special about tomorrow]
```

## Logic

### Determining today's activities

1. Check what day of week it is (Mon-Sun)
2. Query `evening_clubs` table for that weekday (both morning and afternoon categories)
3. Merge with any one-off calendar events for today (birthdays, trips, playdates)
4. For each child, build their day: "School -> [activity] [time]"
5. If no after-school activity: "School as normal -> pickup 15:15"

### Determining kit needed

1. Check today's clubs for any with notes mentioning kit
2. Check tomorrow's clubs for kit that needs packing tonight
3. If swimming is tomorrow, remind to pack tonight
4. Per-child if activities differ

### Weekend handling

- Saturday/Sunday: Only show non-school activities
- Don't show "School" prefix on weekends
- If no activities: "No activities today"

### School holidays / INSET days

- If detected (from school data), replace school activities with:
  "No school today — [holiday name / INSET day]"
- Still show any non-school activities

## Conversational Follow-ups

- "What kit does Max need tomorrow?" -> Check tomorrow's clubs
- "Does Emmie have tutoring this week?" -> Check evening_clubs table
- "When's the next school trip?" -> Search Second Brain
- "What are this week's spellings?" -> Fetch from school data

## Rules

- Keep it scannable — parents are busy in the morning
- Always show BOTH children
- Always show both TODAY and TOMORROW
- Highlight kit that needs packing TONIGHT (for tomorrow)
- If an activity is cancelled (from calendar or school notice), flag it clearly
- Discord uses **bold** (double asterisk)
- Posts to both Discord AND WhatsApp
