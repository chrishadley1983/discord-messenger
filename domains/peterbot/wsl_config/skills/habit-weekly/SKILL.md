---
name: habit-weekly
description: Private weekly habit accountability summary
trigger:
  - "habit week"
  - "weekly habit"
scheduled: true
conversational: false
channel: "#peter-chat"
---

# Habit Weekly Review

## Purpose

Sunday 8pm weekly review of habit progress. Brief, supportive, private.

**This is SENSITIVE. Never mention what the habit is. Never post to any other channel.**

## Pre-fetched Data

The scheduler injects a **live** `## Pre-fetched Data` block below, computed by
the `habit-weekly` data fetcher from the habit log. Fields: `day_number`,
`current_streak`, `longest_streak`, `total_yes`, `total_no`, `total_days`,
`week_results` (last 7 days oldest→newest, each `"Y"`/`"N"`/`null`),
`week_number`, `percentage`, `start_date`. **Always use those values — never
hardcode.**

## Output Format

```
**Week {week_number} done.**

{visual_streak}
{total_yes}/{total_days} this week | Streak: {current_streak}

{one_line_message}
```

Where `visual_streak` shows the week as: `Y Y N Y Y Y Y` (spaced, bold the Y's)

One-line messages:
- Perfect week: "Flawless. Keep building."
- 1 miss: "One slip, strong recovery."
- 2+ misses: "Rough week. New week starts now."
- Improving vs last week: "Better than last week."

## Rules

- NEVER mention what the habit is
- NEVER post outside #peter-chat
- Keep the whole message under 200 characters
- Supportive but not preachy
