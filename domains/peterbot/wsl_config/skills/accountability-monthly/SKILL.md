---
name: accountability-monthly
description: Monthly deep-dive accountability report with trend analysis
trigger: []
scheduled: true
conversational: false
channel: "#food-log+WhatsApp:chris"
---

# Monthly Accountability Report

## Purpose

First-of-month deep-dive reviewing the previous month's goal performance.
Goes deeper than the weekly — includes month-over-month comparison, trajectory projections,
and milestone celebrations.

## Pre-fetched Data

Data injected by the scheduler via `get_accountability_monthly_data()`:

```json
{
  "period": "month",
  "days": 30,
  "goals": [
    {
      "title": "Save £5k by June",
      "goal_type": "target",
      "computed": {
        "pct": 47,
        "on_track": 82,
        "trend": "↑"
      },
      "period_delta": 820,
      "newly_reached_milestones": [
        {"title": "First £2k saved", "target_value": 2000, "reached_at": "2026-03-15"}
      ]
    }
  ],
  "overall_score": 75.2,
  "grade": "B"
}
```

## Output Format

```
📊 **Monthly Accountability** — March 2026

🏃 **10k Steps Daily**
Hit 22/30 days (73%) | Avg: 10,800 | Best streak: 14 🔥
▓▓▓▓▓▓▓░░░ | Trend: ↑ vs Feb

💰 **Save £5k by June**
£2,340 / £5,000 (47%) | +£820 this month
▓▓▓▓▓░░░░░ | On-track: 82%
🏆 Milestone: First £2k saved!
📈 At this pace → £4,800 by June (£200 short)

⚖️ **Hit 80kg**
83.1 → 81.8kg (−1.3kg this month)
▓▓▓▓▓▓▓▓░░ | On-track: 108% ↑
📈 Projection: 80kg by mid-May

---
**March Grade: B (75%)**
✅ Weight loss ahead of schedule
✅ Steps improving week-over-week
⚠️ Savings pace needs +£80/week to stay on track
🎯 April focus: Consistency on water + maintain savings momentum
```

## Rules

- `NO_REPLY` if no active goals
- Show ALL active goals (no 5-goal limit — monthly is the deep dive)
- Include trajectory projection for target goals: "at this pace → X by deadline"
- Celebrate milestones reached this month with 🏆
- Month-over-month trend for each goal
- End with:
  - Monthly grade
  - 2-3 bullet wins (✅)
  - 1-2 bullet focus areas (⚠️)
  - 1 sentence "April focus" looking ahead
- Allowed to be longer than weekly (up to 1500 chars for WhatsApp, full length for Discord)
- Motivating but honest — don't sugarcoat if a goal is off-track
- Progress bars: ▓ filled, ░ empty, ~10 chars wide
