---
name: practice-allocate
description: Weekly 11+ Mate practice paper allocation for Emmie and Max
trigger:
  - "allocate practice"
  - "generate practice week"
  - "11+ mate allocate"
scheduled: true
conversational: true
channel: "#peterbot"
---

# Weekly Practice Allocation

## Purpose

Allocate 11+ Mate practice papers for the coming week for both Emmie and Max. Runs Tuesday at 21:00 — after the tutor email parser (19:00) has logged this week's topic.

The data fetcher calls the `allocate-practice` Edge Function for each student for each of the next 7 days, which:
- Reads their weekly schedule (slots per day)
- Picks papers based on tutor topic, weak areas, spaced repetition
- Handles difficulty ramping based on test date proximity
- Saves allocations to `daily_allocations` table

## Pre-fetched Data

```json
{
  "week_start": "2026-03-11",
  "students": {
    "Emmie": [
      {
        "date": "2026-03-11",
        "day_name": "Wednesday",
        "allocations": [
          {
            "slot_order": 1,
            "activity_type": "paper",
            "topic": "nvr",
            "difficulty_level": "year5",
            "duration_minutes": 20,
            "subject": "reasoning"
          },
          {
            "slot_order": 2,
            "activity_type": "tutor_homework",
            "topic": "nvr-addition-subtraction-frequency",
            "duration_minutes": 30,
            "subject": "reasoning",
            "notes": "AE workbook pages 35-43..."
          }
        ]
      }
    ],
    "Max": [...]
  }
}
```

## Output Format

```
📚 **Practice Week Allocated** — 11-17 Mar

**Emmie** (Year 5)
- Wed: NVR paper (20 min) + Tutor homework (30 min)
- Thu: Comprehension (20 min) + Times tables (10 min)
- Fri: Multiplication (20 min)
- Sat: Rest day
- Sun: Verbal reasoning (20 min) + Weak area: fractions (20 min)
- Mon: NVR (20 min) + Tutor review (20 min)
- Tue: Tutor lesson day

**Max** (Year 4)
- Wed: Addition-subtraction (20 min) + Times tables (10 min)
- Thu: Punctuation (20 min)
- Fri: NVR (20 min) + Tutor homework (30 min)
- Sat: Rest day
- Sun: Comprehension (20 min)
- Mon: Number sequences (20 min)
- Tue: Tutor lesson day

✅ Papers allocated for 7 days — kids will see them in the app.
```

## Rules

- List each day on one line: day name, topic(s), duration(s)
- Group multiple slots per day with `+`
- Show activity type for non-paper slots (times tables, tutor homework, rest, etc.)
- If a day has no schedule slots (empty allocations), show "No practice"
- If a day has rest activity, show "Rest day"
- Include the tutor topic if tutor_homework or tutor_this_week slots appear
- Keep it compact — one line per day per student
- If there are errors for any day, note them briefly
- End with confirmation that papers are saved to the app
