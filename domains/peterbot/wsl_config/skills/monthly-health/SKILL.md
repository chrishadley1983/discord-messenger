---
name: monthly-health
description: Monthly health summary with long-term trends
trigger:
  - "monthly summary"
  - "monthly health"
  - "how was my month"
scheduled: true
conversational: true
channel: #food-log
---

# Monthly Health Summary

## Purpose

Monthly health review on the 1st of each month at 9am UK. Focuses on long-term trends and progress toward the Japan goal.

## Pre-fetched Data

```json
{
  "weight": {
    "start": 84.2,
    "end": 82.3,
    "change": -1.9,
    "min": 82.1,
    "max": 84.5,
    "avg": 83.2,
    "readings": 25
  },
  "nutrition": {
    "days_tracked": 28,
    "avg_calories": 2050,
    "avg_protein": 148,
    "avg_carbs": 240,
    "avg_fat": 65,
    "avg_water": 3100,
    "protein_days_hit": 20,
    "tracking_rate": 93
  },
  "steps": {
    "total": 420000,
    "avg": 14000,
    "days": 30,
    "days_hit_goal": 18,
    "best_day": 22000,
    "worst_day": 5000,
    "goal": 15000
  },
  "sleep": {
    "avg_hours": 7.2,
    "avg_score": 76,
    "days": 28,
    "best_night": 9.1,
    "worst_night": 4.5,
    "nights_7plus": 20
  },
  "goals": {
    "target_weight_kg": 80,
    "goal_reason": "Japan trip",
    "days_remaining": 60
  },
  "previous_month": {
    "avg_weight": 84.5,
    "avg_steps": 12500
  },
  "targets": {
    "calories": 2100,
    "protein_g": 160,
    "steps": 15000
  },
  "month_ending": "2026-01-31"
}
```

## Output Format

```
📅 **Monthly Health Summary**
January 2026

**Weight Progress** ⚖️
84.2kg → 82.3kg (−1.9kg) ✅
Range: 82.1 - 84.5kg | Avg: 83.2kg
vs last month: −1.3kg avg

**Nutrition** 🍽️
2,050 cal/day | 148g protein
Tracking: 28/30 days (93%)
Protein target: 20/28 days

**Activity** 🚶
420,000 total steps (14,000/day)
Goal hit: 18/30 days (60%)
vs last month: +1,500 steps/day

**Sleep** 😴
7.2h avg | Score: 76
7h+ nights: 20/28

**Progress to Goal** 🎯
Current: 82.3kg → Target: 80kg
Remaining: 2.3kg in 60 days
Required pace: ~0.27kg/week

---
**January Grade: A** 🏆

[3-4 sentence summary: celebrate wins, month-over-month comparison, what to focus on next month, Japan countdown motivation]
```

## Grading Criteria

Monthly grade based on:
- **A**: Weight down ≥1kg, tracking ≥90%, steps improving
- **B**: Weight down, decent tracking
- **C**: Weight stable, mixed tracking
- **D**: Weight up or poor tracking

## Rules

- Focus on the big picture - monthly trend matters more than daily fluctuations
- Month-over-month comparison is key (use previous_month data)
- Calculate if on track to hit Japan goal (days_remaining / kg to lose)
- Be celebratory if progress is good
- Be encouraging but realistic if behind
- Japan trip is the emotional anchor - countdown creates urgency
- Use actual data from pre-fetch - don't make up numbers
- If a section has no data (empty object), show "⚠️ No data"
