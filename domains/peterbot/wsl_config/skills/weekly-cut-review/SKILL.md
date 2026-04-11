---
name: weekly-cut-review
description: Sunday review of the fat-loss programme — adherence, trend, next week's adjustment
trigger:
  - "weekly cut review"
  - "cut review"
  - "weekly fitness review"
  - "how's my cut going"
scheduled: true
conversational: true
channel: "#food-log"
---

# Weekly Cut Review

## Purpose

The Sunday 09:00 review for the 13-week post-Japan programme. Replaces the
generic `weekly-health` skill while the programme is active. Key difference:
this one is **programme-aware** — tracks progress vs the 10kg target, detects
trend stalls, and prescribes next week's adjustment.

## Pre-fetched Data

```
GET http://172.19.64.1:8100/fitness/weekly-review
```

Returns:

```json
{
  "programme": {"id": "...", "name": "...", "start_weight_kg": 94.3, "target_weight_kg": 84.3, "daily_calorie_target": 1950, "daily_protein_g": 170, "duration_weeks": 13},
  "week_no": 2,
  "week_start": "2026-05-04",
  "week_end": "2026-05-10",
  "weight": {
    "trend_7d": 93.4,
    "change_vs_last_week_kg": -0.7,
    "cumulative_loss_kg": 0.9,
    "slope_kg_per_week": -0.65,
    "stalled": false
  },
  "nutrition": {
    "tracked_days": 7,
    "days_under_cal_target": 6,
    "days_hit_protein": 5,
    "avg_calories": 1920,
    "avg_protein_g": 162
  },
  "steps": {"days_hit_target": 5, "avg": 12800},
  "strength": {"sessions_done": 5, "target": 5},
  "mobility": {"days_hit": 6, "target": 7},
  "adjustment": {
    "next_calorie_target": 1950,
    "next_steps_target": 12000,
    "note": "Continue current plan",
    "recalibrate_recommended": false
  },
  "live_targets": {
    "bmr": 1838, "activity_factor": 1.6, "tdee": 2941,
    "target_calories": 2391, "target_protein_g": 155,
    "weight_used_kg": 93.4
  },
  "target_drift": {
    "stored_calories": 2407, "live_calories": 2391, "calorie_delta": -16,
    "stored_protein_g": 155, "live_protein_g": 155, "protein_delta": 0,
    "drifted": false
  }
}
```

## Output Format

```
📋 **Weekly Cut Review** — Week 2 of 13
Sunday 10 May 2026

**Weight** ⚖️
Trend: 93.4kg (−0.7kg this week)
Cumulative loss: −0.9kg of 10.0kg ▓░░░░░░░░░ 9%
Trajectory: −0.65 kg/wk ✅ (target −0.77)

**Adherence** 📊
Calories: 6/7 days ✅ (avg 1,920 / 1,950)
Protein: 5/7 days (avg 162 / 170g)
Steps: 5/7 days (avg 12,800 / 12,000) ✅
Strength: 5/5 sessions ✅✅✅✅✅
Mobility: 6/7 days

---
**PT Grade: A−** 📋

[2-3 sentences: what went well, what to sharpen next week, explicit motivation tied to target weight + weeks remaining]

**Next Week**
Calories: 1,950 | Protein: 170g | Steps: 12k
[Any adjustment if stalled]
```

## Grading Criteria

Total 100 points:
- **Weight trend (30pts)**: Lost ≥0.7kg = 30, ≥0.5 = 25, ≥0.3 = 18, lost any = 12, maintained = 6, gained = 0
- **Strength (25pts)**: `sessions_done / target * 25`
- **Protein (20pts)**: `days_hit_protein / 7 * 20`
- **Calories (15pts)**: `days_under_cal_target / 7 * 15`
- **Mobility (10pts)**: `days_hit / 7 * 10`

Grade scale: A+ (≥95), A (≥85), A− (≥80), B+ (≥75), B (≥70), C (≥60), D (≥50), F (<50).

## Rules

- **Reference the programme targets** from the payload, not static numbers.
- **Prefer `live_targets` over `programme.daily_calorie_target`** — the live
  values are recomputed from the current trend weight, so they're always
  correct even as BMR drops with weight loss.
- **If stalled**: lead with `🚨 STALL DETECTED` and explain the adjustment.
- **If `adjustment.recalibrate_recommended` is true** (weight has drifted
  enough that stored targets are stale), automatically POST to
  `/fitness/programme/recalibrate` before generating the review, and mention
  the recalibration in the report (e.g. "Recalibrated targets: now 2,320 kcal
  / 150g protein based on your 89.2kg trend weight").
- **Always show weeks remaining + projected end weight** based on current slope:
  projected = trend_7d + slope_kg_per_week * weeks_remaining
- After generating, auto-POST to `/fitness/weekly-checkin` to persist the snapshot.
- Save the final review text to Second Brain with tags `fitness,cut,week-<N>`.
- If no active programme, fall back to the generic `weekly-health` skill.
- Encouraging but honest — don't sugarcoat a stalled week.
