---
name: health-digest
description: Morning health digest with sleep, weight, steps, HR and comparison to yesterday
trigger:
  - "health digest"
  - "morning digest"
  - "how did i sleep"
  - "health summary"
scheduled: true
conversational: true
channel: #food-log
---

# Morning Health Digest

## Purpose

Daily morning digest at 8am UK. Shows overnight health data and compares to previous day. Motivates for the day ahead with goal progress.

## Pre-fetched Data

```json
{
  "sleep": {
    "duration_hours": 7.2,
    "deep_sleep_hours": 1.5,
    "rem_hours": 1.8,
    "score": 82,
    "previous": { "duration_hours": 6.8, "score": 75 }
  },
  "steps": {
    "yesterday": 14500,
    "target": 15000
  },
  "heart_rate": {
    "resting": 58,
    "previous_resting": 60
  },
  "weight": {
    "current_kg": 82.3,
    "previous_kg": 82.5,
    "trend": "down"
  },
  "nutrition": {
    "yesterday_calories": 2050,
    "yesterday_protein": 145,
    "target_calories": 2100,
    "target_protein": 160
  },
  "goal": {
    "target_weight_kg": 80,
    "deadline": "April 2026",
    "reason": "Family trip to Japan",
    "days_remaining": 85
  },
  "date": "2026-01-31"
}
```

## Output Format

```
🌅 **Morning Health Digest** - Friday, 31 January

**Sleep** 😴
7.2hrs (score: 82) ↑ vs 6.8hrs yesterday
Deep: 1.5hrs | REM: 1.8hrs

**Weight** ⚖️
82.3kg ↓ 0.2kg from yesterday
Target: 80kg (85 days to Japan 🇯🇵)

**Yesterday's Activity** 🚶
Steps: 14,500 / 15,000 (97%) ✅
Resting HR: 58bpm ↓ from 60

**Yesterday's Nutrition** 🍽️
Calories: 2,050 / 2,100 ✅
Protein: 145g / 160g (91%) ⚠️

---
[Personalized motivation - reference the goal, call out wins, note areas to focus]
```

## Comparison Indicators

- ↑ improved from yesterday
- ↓ decreased from yesterday
- → same as yesterday

## Rules

- Always compare to previous day where data available
- Highlight wins with ✅
- Flag misses with ⚠️ (not failures, just attention needed)
- Reference the Japan goal naturally
- Keep motivation to 2-3 sentences
- Pete the PT voice - supportive but direct
- If weight trending down, celebrate
- If protein was low, suggest focus for today
