---
name: accountability-weekly
description: Weekly accountability report across all active goals
trigger: []
scheduled: true
conversational: false
channel: "WhatsApp:chris"
---

# Weekly Accountability Report

## Purpose

Sunday evening summary of how Chris tracked against all active goals this week.
Combines auto-sourced data (steps, calories, water, weight) with manually logged progress.

## Pre-fetched Data

Data injected by the scheduler via `get_accountability_weekly_data()`:

```json
{
  "period": "week",
  "days": 7,
  "goals": [
    {
      "id": "uuid",
      "title": "10k Steps Daily",
      "goal_type": "habit",
      "category": "fitness",
      "metric": "steps",
      "current_value": 11200,
      "target_value": 10000,
      "direction": "up",
      "computed": {
        "pct": 112,
        "trend": "↑",
        "current_streak": 14,
        "best_streak": 21,
        "hit_rate_7": {"hits": 5, "total": 7, "days": 7}
      },
      "period_delta": 2400,
      "newly_reached_milestones": []
    }
  ],
  "count": 3,
  "overall_score": 78.5,
  "grade": "B+"
}
```

## Output Format

```
📊 **Weekly Accountability** — w/e Sun 30 March

🏃 **10k Steps Daily** (Fitness)
Hit 5/7 days | Avg: 11,200 | Streak: 14 🔥
▓▓▓▓▓▓▓▓░░

⚖️ **Hit 80kg** (Health)
82.1 → 81.8kg (−0.3kg this week) ↓ target
▓▓▓▓▓▓▓▓░░ | 62 days left | On-track: 94%

💧 **2L Water Daily** (Health)
Hit 4/7 days | Avg: 1,800ml
▓▓▓▓▓▓░░░░

---
**Overall: B+ (78%)** | ✅ Steps streak strong | ⚠️ Water needs work
```

## Rules

- `NO_REPLY` if no active goals
- Max 5 goals — if more, show top 5 by priority (lowest on-track first) and mention "and X more"
- Keep under 800 chars for WhatsApp readability
- Use the goal's metric for formatting
- Show trend arrows (↑↓→) for week-over-week changes
- Streak badges: 🔥 for 7+, 🔥🔥 for 30+, 🔥🔥🔥 for 100+
- On-track percentage only for target goals with deadlines
- Hit rate (X/7 days) for habit goals
- End with 1-line actionable insight: what's going well + what needs attention
- Warm, motivating tone — celebrate wins, gentle on misses
- Progress bars: ▓ filled, ░ empty, ~10 chars wide
