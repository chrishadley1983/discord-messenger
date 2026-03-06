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
1. **Next Week** — Scheduled Sunday 18:00. Planning view of the coming Mon–Sun.
2. **Last Week** — On demand only ("kids last week"). Review of what happened.

## Data Sources

### 1. Activity Config

Read `activities.json` from the `kids-daily` skill directory for recurring activities.

### 2. Calendar Events

Fetch from Hadley API for the relevant week:

```bash
# Next week (Monday to Sunday)
curl -s "http://172.19.64.1:8100/calendar/range?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD"

# Last week
curl -s "http://172.19.64.1:8100/calendar/range?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD"
```

Calculate the correct Monday–Sunday date range for next or last week.

### 3. School Data

Search Second Brain for school notices relevant to the period:

```
mcp__second-brain__search_knowledge("Stocks Green school next week", limit=5)
```

### 4. Spellings

For next week, show the upcoming spelling words. For last week, show what they were practising.

The current spelling week number is calculated by the school data fetcher. For next week, add 1. For last week, subtract 1.

## Determining Mode

- **Scheduled (Sunday 18:00)**: Always "Next Week"
- **Conversational**: Determine from trigger:
  - "next week", "this week", "coming week" → Next Week
  - "last week", "past week" → Last Week
  - Ambiguous → Ask: "Do you want next week's plan or last week's review?"

## Output Format — Next Week

```
📅 **Kids Next Week** — 10–16 Mar

👦 **MAX (Year 6)**
  Mon: School
  Tue: School → Swimming 4pm 🏊
  Wed: School → Afterschool Club 🏫 (pickup 4:30pm)
  Thu: School
  Fri: School → Swimming 4pm 🏊
  Sat: Piano 11am 🎹
  Sun: Piano 11am 🎹

👧 **EMMIE (Year 4)**
  Mon: School → Tutoring 4pm 📚
  Tue: School → Swimming 4pm 🏊
  Wed: School → Afterschool Club 🏫 (pickup 4:30pm)
  Thu: School
  Fri: School → Swimming 4pm 🏊
  Sat: Piano 11am 🎹
  Sun: Piano 11am 🎹, Tutoring 4pm 📚

📝 **Spellings** — Week 20
  👦 Max: [word list or phoneme]
  👧 Emmie: [word list or phoneme]

🎒 **Kit to prepare:**
  Mon night: Swimming kit (both) for Tuesday
  Thu night: Swimming kit (both) for Friday

⚠️ **Heads up:**
  - [Any school events, trips, non-uniform days, etc.]
  - [Any one-off calendar events — parties, playdates]
```

## Output Format — Last Week

```
📋 **Kids Last Week** — 3–9 Mar

👦 **MAX (Year 6)**
  Mon: School ✓
  Tue: School → Swimming ✓
  Wed: School → Afterschool Club ✓
  Thu: School ✓
  Fri: School → Swimming ✓
  Sat: Piano ✓
  Sun: Piano ✓

👧 **EMMIE (Year 4)**
  Mon: School → Tutoring ✓
  Tue: School → Swimming ✓
  Wed: School → Afterschool Club ✓
  Thu: School ✓
  Fri: School → Swimming ✓
  Sat: Piano ✓
  Sun: Piano ✓, Tutoring ✓

📝 **Spellings were:** Week 19 (phoneme "m") — [word list]

🏫 **School notices last week:**
  - [Any newsletters, announcements, event follow-ups]
```

## Logic

### Building the weekly grid

1. For each day (Mon–Sun), determine the date
2. Look up recurring activities from `activities.json` for that day of week
3. Merge any one-off calendar events (filter for kids-related — see kids-daily for keywords)
4. Build per-child per-day summary line
5. Weekdays: prefix with "School" (unless INSET/holiday)
6. Weekend: just show activities or "Free"

### Kit summary (Next Week only)

- Scan all days for activities with `kit` specified
- Show which night to pack for which day's activity
- E.g., "Mon night: Swimming kit for Tuesday"

### Heads up section

- Any one-off events from calendar (not recurring)
- School events from Second Brain
- Non-uniform days, trips, concerts, etc.

### Last Week — tick marks

- For "last week" mode, show ✓ after each activity
- If a school event happened, mention it
- Include any tutoring feedback if found in Second Brain

## Weekend handling

- Saturday + Sunday: show only non-school activities
- If nothing scheduled: "Free day"

## Rules

- Keep it structured and scannable
- Always show BOTH children with their year groups
- Spelling words only if available from school data
- For "next week", emphasise preparation (kit, heads up)
- For "last week", keep it brief — just confirmation + any notable events
- Posts to both Discord AND WhatsApp
