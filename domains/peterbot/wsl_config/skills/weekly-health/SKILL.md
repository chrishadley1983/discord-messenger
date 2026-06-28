---
name: weekly-health
description: Weekly health summary with trends, grades, and insights
trigger:
  - "weekly summary"
  - "weekly health"
  - "how was my week"
scheduled: true
conversational: true
channel: #food-log
---

# Weekly Health Summary

## Purpose

Comprehensive weekly health review every Sunday at 9am UK. Covers weight trend, nutrition averages, activity, sleep quality, and gives an overall "PT grade".

## Pre-fetched Data

```json
{
  "weight": {
    "start": 82.8,
    "end": 82.3,
    "change": -0.5,
    "min": 82.1,
    "max": 83.0,
    "avg": 82.5,
    "readings": 6
  },
  "nutrition": {
    "days_tracked": 7,
    "avg_calories": 2080,
    "avg_protein": 152,
    "avg_carbs": 245,
    "avg_fat": 68,
    "avg_water": 3200,
    "protein_days_hit": 5,
    "protein_target_used": 125,
    "incomplete_days": [],
    "incomplete_count": 0
  },
  "steps": {
    "total": 94500,
    "avg": 13500,
    "days": 7,
    "days_hit_goal": 4,
    "best_day": 18200,
    "goal": 15000
  },
  "sleep": {
    "avg_hours": 7.1,
    "avg_score": 78,
    "days": 6,
    "best_night": 8.2,
    "worst_night": 5.8
  },
  "heart_rate": {
    "avg": 59,
    "min": 54,
    "max": 65,
    "days": 7
  },
  "goals": {
    "target_weight_kg": 80,
    "goal_reason": "Japan trip",
    "days_remaining": 60
  },
  "targets": {
    "calories": 2100,
    "protein_g": 160,
    "steps": 15000
  },
  "week_ending": "2026-01-31"
}
```

## Output Format

```
📊 **Weekly Health Summary**
Week ending Sunday, 31 January

**Weight Trend** ⚖️
82.8kg → 82.3kg (−0.5kg) ✅
Range: 82.1 - 83.0kg | Avg: 82.5kg
Target: 80kg | 60 days remaining 🇯🇵

**Nutrition Averages** 🍽️
Calories: 2,080 / 2,100 (99%) ✅
Protein: 152g / 160g (95%) ✅ | Hit 5/7 days
Carbs: 245g | Fat: 68g | Water: 3,200ml
Days tracked: 7/7

**Activity** 🚶
Avg steps: 13,500 / 15,000 (90%)
Total: 94,500 | Best: 18,200
Hit goal: 4/7 days

**Sleep** 😴
Avg: 7.1h | Score: 78
Best: 8.2h | Worst: 5.8h

**Resting HR** ❤️
Avg: 59bpm | Range: 54-65bpm

---
**PT Grade: B+** 📋

[2-3 sentence summary: what went well, what to focus on next week, motivation tied to Japan goal]
```

## Grading Criteria

Calculate based on:
- **Weight (20pts)**: Lost >0.5kg = 20, lost any = 15, maintained = 10, gained = 5
- **Protein (25pts)**: Based on protein_days_hit / days_tracked ratio
- **Steps (25pts)**: Based on days_hit_goal / days ratio
- **Sleep (15pts)**: ≥7.5h = 15, ≥7h = 12, ≥6.5h = 8, else = 4
- **Heart Rate (15pts)**: ≤55 = 15, ≤60 = 12, ≤65 = 8, else = 4

Grade scale: A+ (≥90%), A (≥80%), B (≥70%), C (≥60%), D (≥50%), F (<50%)

## Rules

- Use actual numbers from the data - don't make up values
- **Nutrition averages already exclude partial-tracking days** — `days_tracked` is the count of *properly logged* days, and the averages are over those only. If `incomplete_count > 0`, append a brief note after the nutrition block listing the excluded day(s) from `incomplete_days`, e.g. "(Fri excluded — only 479 cal logged, looks like a missed tracking day)". Never average a partial day into the headline numbers.
- **Protein "hit" uses the live target** in `protein_target_used` (the programme's current floor, e.g. 125g), NOT a hardcoded 160g. Report `protein_days_hit / days_tracked`.
- If a section has no data (empty object), show "⚠️ No data this week"
- Compare everything to targets where available
- Celebrate wins explicitly
- Be specific about what to improve
- Reference Japan goal to maintain motivation
- Keep it comprehensive but scannable
- Grade should be fair but encouraging
- Use ✅ for metrics at 90%+ of target
