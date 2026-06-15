---
name: habit-checkin
description: Private daily habit accountability check-in
trigger:
  - "habit check"
  - "habit status"
  - "where am I"
  - "streak"
scheduled: true
conversational: true
channel: "#peter-chat"
---

# Habit Check-in

## Purpose

Daily 9pm private check-in for Chris's habit tracker. Posts a short message, Chris replies Y or N.

**This is SENSITIVE. Never mention what the habit is. Never post to any other channel. Never reference in other skills or scheduled messages.**

## Pre-fetched Data

The scheduler injects a **live** `## Pre-fetched Data` block below these
instructions, computed by the `habit-checkin` data fetcher from the habit log.
Fields: `day_number`, `current_streak`, `longest_streak`, `total_yes`,
`total_no`, `total_days`, `last_result`, `percentage`, `start_date`,
`logged_today`. **Always use those values — never hardcode.** The 9pm job
auto-skips on day 0 or if a result was already logged today.

## Scheduled Output Format (9pm daily)

Keep it minimal and warm. Vary the message slightly.

```
Day {day_number} — Y or N?
```

If streak is notable (5, 10, 15, 20, 30...):
```
Day {day_number} — Y or N? (current streak: {current_streak})
```

## Conversational Response (when Chris asks "where am I" / "streak" / "habit status")

```
Day {day_number}
Current streak: {current_streak}
Longest streak: {longest_streak}
Score: {total_yes}/{total_days} ({percentage}%)
```

## Handling Y/N Replies

When Chris replies Y or N (or yes/no/y/n) in the context of a recent habit check-in:

1. Log the result via the Hadley API (auth required):
   ```
   source ~/peterbot/.env 2>/dev/null
   curl -s -X POST "http://172.19.64.1:8100/accountability/habit" \
     -H "x-api-key: $HADLEY_AUTH_KEY" -H "Content-Type: application/json" \
     -d '{"result": "Y"}'
   ```
   Date defaults to today; pass `"date": "YYYY-MM-DD"` to backfill. The endpoint
   upserts one row per day, so re-logging simply corrects that day.

2. Respond briefly:
   - Y: Random from ["Nice.", "Logged.", "Good day.", "Keep it going."]
   - N: Random from ["Logged. Tomorrow's a new day.", "Noted. Reset and go again.", "Logged. You've got this."]

## Rules

- NEVER mention what the habit is
- NEVER post outside #peter-chat
- NEVER reference in other scheduled outputs (health digest shows only the streak number, handled by that skill)
- Keep responses under 50 characters where possible
- Day 0 = 2026-06-12 (no check-in needed for day 0)
- Day 1 = 2026-06-13 (first check-in)
- If Chris hasn't responded by end of day, don't nag — just skip that day
