---
name: health-digest
model: claude-sonnet-4-6
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

Daily morning digest at 07:55 UK. Shows overnight health data and compares to previous day. Motivates for the day ahead with goal progress.

Since the 2026-06 morning consolidation this message ALSO carries the daily cut check-in (the old 06:45 fitness-dashboard post). Fetch `GET http://172.19.64.1:8100/fitness/dashboard` and append a compact section:

```
🎯 **Cut** — Day {day_no}/W{week_no}
Trend {trend_7d}kg ({slope_kg_per_week:+}kg/wk) · {cumulative_loss_kg}kg down
Today: {workout one-liner} · Budget: {calorie_budget} kcal
{one-line adherence flag only if something needs attention}
```

The standalone fitness-dashboard skill remains for on-demand "cut status" questions and the Wednesday evening nudge.

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
    "target_protein": 120
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
Protein: 145g / 120g ✅

**Today's Training** 🏋️
Lower A (glutes/posterior) — 30 min · glute bridge, Bulgarian split squat, single-leg RDL

---
[Personalized motivation - reference the goal, call out wins, note areas to focus]
```

## Today's Training (fetch)

Fetch `GET http://172.19.64.1:8100/fitness/today` and add the one-line **Today's Training** block before the motivation divider:
- **Training day** → 🏋️ **{workout.label}** — {duration_min} min · first 3 exercises (humanised, e.g. "glute bridge, Bulgarian split squat, single-leg RDL")
- **Mobility/recovery day** → 🚶 Walk + 10-min hip mobility
- **Rest day** → 😴 Rest day (mobility only if tight)

Only include if an active programme exists (the endpoint returns a `workout`). Skip the block silently otherwise. Keep it to one line.

## Comparison Indicators

- ↑ improved from yesterday
- ↓ decreased from yesterday
- → same as yesterday

## Advisor Warnings

The pre-fetched data includes an `advisor` field from the fitness advisor engine.
If `advisor.advice` contains items, include the top 1-3 most important ones
(severity order: warning > caution > info) in an **Advisor** section after the
standard digest. Format:

```
**Coach Notes** 🏋️
⚠️ [headline] — [action]
⚡ [headline] — [action]
✅ [headline]
```

Use ⚠️ for warning/caution, ⚡ for info, ✅ for positive. Keep each to one line.
If Chris says "less alerts" or "too many", only show warning-severity items.

## Habit Streak

Append a single-line habit streak counter at the very end of the digest, after the motivation line. This is a private tracker — do NOT elaborate or mention what it tracks.

**How to get the data:** Query Supabase (project: family-meal-planner / pocptwknyxyrtmnfnrph):
```sql
SELECT 
  COUNT(*) FILTER (WHERE result = 'Y') as total_yes,
  COUNT(*) as total_days,
  (SELECT COUNT(*) FROM (
    SELECT log_date, result,
      ROW_NUMBER() OVER (ORDER BY log_date DESC) - 
      ROW_NUMBER() OVER (PARTITION BY result ORDER BY log_date DESC) as grp
    FROM habit_log
  ) s WHERE result = 'Y' AND grp = (
    SELECT MIN(grp) FROM (
      SELECT result,
        ROW_NUMBER() OVER (ORDER BY log_date DESC) - 
        ROW_NUMBER() OVER (PARTITION BY result ORDER BY log_date DESC) as grp
      FROM habit_log
    ) s2 WHERE result = 'Y'
  )) as current_streak
FROM habit_log;
```

Or simply: count consecutive Y's from the most recent entry backwards.

**Format:** `🔥 {current_streak}` — just the emoji and number, nothing else. Appears as the last line.

If no habit data exists yet (day 0 or no entries), show `🔥 0`.

## Rules

- Always compare to previous day where data available
- Highlight wins with ✅
- Flag misses with ⚠️ (not failures, just attention needed)
- Reference the Japan goal naturally
- Keep motivation to 2-3 sentences
- Pete the PT voice - supportive but direct
- If weight trending down, celebrate
- If protein was low, suggest focus for today
- Frame protein by the current goal phase (fat-loss = a *floor*, weight loss
  leads; muscle-build = the adaptive target). Read the target from the payload —
  never hardcode a protein number or a "protects muscle" line.
- The habit streak line is PRIVATE — never explain what it means
