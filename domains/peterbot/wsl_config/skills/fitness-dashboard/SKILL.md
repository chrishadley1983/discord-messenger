---
name: fitness-dashboard
description: Daily morning check-in for the post-Japan fat-loss programme. Shows trend weight, today's prescribed workout, calorie budget, and adherence flags.
trigger:
  - "fitness dashboard"
  - "fitness today"
  - "today's workout"
  - "am i on track"
  - "cut status"
  - "fat loss update"
scheduled: true
conversational: true
channel: "#food-log"
---

# Fitness Dashboard

## Purpose

The daily "am I on track" check-in for Chris's 13-week post-Japan cut.
Runs every morning at 06:45 UK (after the Withings weigh-in sync) and on-demand.

## Pre-fetched Data

Fetch via `GET http://172.19.64.1:8100/fitness/dashboard`.

The endpoint returns:

```json
{
  "programme": {...},
  "day_no": 14,
  "week_no": 2,
  "days_remaining": 77,
  "weight": {
    "latest_raw": 93.2,
    "trend_7d": 93.5,
    "trend_ema": 93.4,
    "slope_kg_per_week": -0.6,
    "stalled": false,
    "cumulative_loss_kg": 0.8,
    "progress_pct": 8.0,
    "message": "On track: -0.60 kg/wk over 13 days."
  },
  "nutrition": {
    "calories": 840,
    "protein_g": 62,
    "water_ml": 1200,
    "target_calories": 1950,
    "target_protein": 170
  },
  "steps": {
    "today": 4200,
    "target": 12000,
    "avg_7d": 11500
  },
  "today_workout": {
    "session_type": "push",
    "label": "Push (upper)",
    "duration_min": 20,
    "exercises": [
      {"exercise_slug": "push-up", "sets": 3, "reps": 11},
      {"exercise_slug": "pike-push-up", "sets": 3, "reps": 7},
      ...
    ],
    "is_rest": false
  },
  "mobility": {"morning": false, "evening": false},
  "strength_this_week": {"done": 2, "target": 5},
  "flags": ["Morning mobility not logged"]
}
```

## Output Format

```
🔥 **Fitness Dashboard** — Day 14 / 91 (Week 2)

**Weight** ⚖️
Trend: 93.5kg (raw: 93.2kg)
Change: −0.8kg from start ▓▓░░░░░░░░ 8%
Trajectory: −0.6 kg/wk ✅ (target −0.77)

**Today's Session** 💪 Push (upper) — 20 min
• Push-up: 3×11
• Pike push-up: 3×7
• Chair dip: 3×11
• Diamond push-up: 2×7
• Plank: 2×50s

**Targets Today**
Calories: 840 / 1,950 — 1,110 remaining
Protein: 62 / 170g — need 108g more
Steps: 4,200 / 12,000 ▓▓▓░░░░░░░ 35%

**Week 2 Progress**
Strength: 2 / 5 sessions
Mobility: morning ❌ | evening ❌

**Flags** 🚩
• Morning mobility not logged

---
[1-line motivational nudge tied to the Japan cut and where Chris is today]
```

## Rules

- **Weight display**: ALWAYS show the 7-day trend first, raw second. Day-to-day variance is noise.
- **Targets remaining**: Show what's left to hit, not what's already consumed — Chris responds to gaps better than totals.
- **Today's session**: Full exercise list with the week-adjusted reps/holds. Do NOT show generic defaults.
- **If it's a rest day**: Replace the session block with `🛌 **Rest day** — mobility optional`.
- **If stalled**: Lead with the stall flag, include the adjustment rec (−100 kcal, +2k steps).
- **If no programme active**: Output `No active fitness programme. Run \`/fitness/programme/start\` when you're ready.`
- Always reference Japan/the cut goal to maintain motivation.
- Progress bar: `▓▓▓▓░░░░░░` (10 chars, map pct to fill).
- Keep it compact — one screen of mobile Discord.
