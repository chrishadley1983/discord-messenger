---
name: kids-weekly
description: Weekly kids summary — next week's plan (Sunday) or last week's review (on demand)
trigger:
  - "kids next week"
  - "kids this week"
  - "kids last week"
  - "what are the kids doing next week"
  - "weekly kids"
  - "kids week"
scheduled: true
conversational: true
channel: "#peterbot"
whatsapp: true
---

# Kids Weekly Summary

## Purpose

Two modes:
1. **Next Week** — Scheduled Sunday 18:10. Planning view of the coming Mon-Sun.
2. **Last Week** — On demand only ("kids last week"). Review of what happened.

## Data Sources

### 1. Clubs & Activities (Supabase `evening_clubs` table)

Source of truth for recurring activities. Query all active clubs:

```bash
curl -s "${SUPABASE_URL}/rest/v1/evening_clubs?is_active=eq.true&select=child_name,club_name,pickup_time,pickup_location,notes,weekday,time_category" \
  -H "apikey: ${SUPABASE_KEY}" \
  -H "Authorization: Bearer ${SUPABASE_KEY}"
```

- `weekday`: 0=Monday, 1=Tuesday, ... 6=Sunday
- `time_category`: "morning" (during school) or "afternoon" (after school / evening)

### 2. Uniform / PE Days

Hardcoded in `jobs/school_run.py`:
- **Max**: PE on Monday (0), Thursday (3)
- **Emmie**: PE on Wednesday (2), Thursday (3)

### 3. Calendar Events

Fetch from Hadley API for the relevant week:

```bash
# Next week (Monday to Sunday)
curl -s "http://172.19.64.1:8100/calendar/range?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD"

# Last week
curl -s "http://172.19.64.1:8100/calendar/range?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD"
```

Calculate the correct Monday-Sunday date range for next or last week.

### 4. School Data

Search Second Brain for school notices relevant to the period:

```
mcp__second-brain__search_knowledge("Stocks Green school next week", limit=5)
```

### 5. Spellings

For next week, show the upcoming spelling words. For last week, show what they were practising.

The current spelling week number is calculated by the school data fetcher. For next week, add 1. For last week, subtract 1.

## Children

- **Max** (Year 2) — emoji: boy
- **Emmie** (Year 4) — emoji: girl

## Determining Mode

- **Scheduled (Sunday 18:10)**: Always "Next Week"
- **Conversational**: Determine from trigger:
  - "next week", "this week", "coming week" -> Next Week
  - "last week", "past week" -> Last Week
  - Ambiguous -> Ask: "Do you want next week's plan or last week's review?"

## Output Format — Next Week

```
KIDS NEXT WEEK — 10-16 Mar

MAX (Year 2)
  Mon: School (PE kit)
  Tue: School -> Swimming 4pm
  Wed: School -> Afterschool Club (pickup 4:30pm)
  Thu: School (PE kit)
  Fri: School -> Swimming 4pm
  Sat: Piano 11am
  Sun: Piano 11am

EMMIE (Year 4)
  Mon: School -> Tutoring 4pm
  Tue: School -> Choir 12-1pm, Swimming 4pm
  Wed: School (PE kit) -> Afterschool Club (pickup 4:30pm)
  Thu: School (PE kit)
  Fri: School -> Swimming 4pm
  Sat: Piano 11am
  Sun: Piano 11am, Tutoring 4pm

Spellings — Week 20
  Max: [word list or phoneme]
  Emmie: [word list or phoneme]

Kit to prepare:
  Mon night: Swimming kit (both) for Tuesday
  Thu night: Swimming kit (both) for Friday

Heads up:
  - [Any school events, trips, non-uniform days, etc.]
  - [Any one-off calendar events — parties, playdates]
```

## Output Format — Last Week

```
KIDS LAST WEEK — 3-9 Mar

MAX (Year 2)
  Mon: School
  Tue: School -> Swimming
  Wed: School -> Afterschool Club
  Thu: School
  Fri: School -> Swimming
  Sat: Piano
  Sun: Piano

EMMIE (Year 4)
  Mon: School -> Tutoring
  Tue: School -> Choir, Swimming
  Wed: School -> Afterschool Club
  Thu: School
  Fri: School -> Swimming
  Sat: Piano
  Sun: Piano, Tutoring

Spellings were: Week 19 (phoneme "m") — [word list]

School notices last week:
  - [Any newsletters, announcements, event follow-ups]
```

## Logic

### Building the weekly grid

1. For each day (Mon-Sun), determine the date
2. Query `evening_clubs` for all active clubs, group by weekday
3. Merge any one-off calendar events (filter for kids-related)
4. Build per-child per-day summary line
5. Weekdays: prefix with "School" (unless INSET/holiday), include PE kit note on PE days
6. Weekend: just show activities or "Free"

### Kit summary (Next Week only)

- Scan all days for activities that need kit (swimming kit, etc.)
- Show which night to pack for which day's activity
- E.g., "Mon night: Swimming kit for Tuesday"

### Heads up section

- Any one-off events from calendar (not recurring)
- School events from Second Brain
- Non-uniform days, trips, concerts, etc.

### Last Week — tick marks

- For "last week" mode, show activities without times (briefer)
- If a school event happened, mention it
- Include any tutoring feedback if found in Second Brain

## Weekend handling

- Saturday + Sunday: show only non-school activities
- If nothing scheduled: "Free day"

## Rules

- Keep it structured and scannable
- Always show BOTH children with their year groups
- Spelling words only if available from school data
- For "next week", emphasise preparation (kit, heads up, PE days)
- For "last week", keep it brief — just confirmation + any notable events
- Posts to both Discord AND WhatsApp
