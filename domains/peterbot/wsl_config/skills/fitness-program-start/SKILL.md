---
name: fitness-program-start
description: One-shot init of the 13-week fat-loss programme (TDEE, goals, workout plan)
trigger:
  - "start fitness programme"
  - "start the cut"
  - "kick off fitness programme"
  - "begin fat loss"
  - "start fat loss programme"
scheduled: false
conversational: true
channel: null
---

# Fitness Programme Start

## Purpose

One-shot initializer for Chris's post-Japan fat-loss programme. Run ONCE when
he's back from Japan and ready to commit. Archives any old weight-loss goals,
computes TDEE from current weight + step average, creates a fresh programme
and 6 accountability goals.

## Workflow

1. **Get Chris's current weight**:
   - Either from his message ("I'm 94.3kg this morning")
   - Or from Withings: `GET http://172.19.64.1:8100/fitness/trend?days=2` → use `latest_raw`
   - If weight is >7 days old, ask Chris to weigh in first.

2. **Get the start date**:
   - Today, or what Chris specified ("start it Monday 5th May")
   - Default: next Monday if today is Thursday or later

3. **Confirm before execution**:
   ```
   About to start:
   • 13-week programme: <start_date> → <end_date>
   • Current weight: 94.3kg → target 84.3kg (−10kg)
   • Training: 5x/week 20-min bodyweight (Mon-Fri)
   • I'll archive any existing 'lose weight' goals
   
   Confirm? (yes/no)
   ```

4. **Call the initializer**:
   ```
   POST http://172.19.64.1:8100/fitness/programme/start
   {
     "start_date": "2026-05-05",
     "current_weight_kg": 94.3,
     "target_loss_kg": 10,
     "duration_weeks": 13
   }
   ```

5. **Celebrate the launch** with the full programme breakdown.

## Output Format (after successful init)

```
🚀 **Post-Japan Cut — LAUNCHED**

**Programme**: 13 weeks, 5 May → 3 Aug 2026
**Start**: 94.3kg → **Target**: 84.3kg (−10kg)

**Your numbers** (Mifflin-St Jeor + Garmin activity)
• BMR: 1,845 kcal
• TDEE: 2,500 kcal (activity factor 1.55 from 10k avg steps)
• Daily target: **1,950 kcal** (−550 deficit → ~0.65 kg/wk loss)
• Protein: **170g/day** (1.8g/kg to preserve muscle in the cut)
• Steps: **12,000/day**

**Training split** (20 min, Mon-Fri)
• Mon — Push (upper)
• Tue — Legs A (quads)
• Wed — Pull + core
• Thu — Legs B (posterior)
• Fri — Full body conditioning
• Sat — Mobility + long walk
• Sun — Rest

**Accountability goals created**:
1. Lose 10kg by 3 Aug
2. Daily calories ≤ 1,950
3. Protein ≥ 170g daily
4. 12k steps daily
5. 5 strength sessions/week
6. Daily mobility routine

I'll run the fitness dashboard every morning at 06:45 and a full review
every Sunday at 09:00. Log workouts with "done push" / "done legs", log
mobility with "done morning stretch".

Let's go. 💪
```

## Rules

- **NEVER run the init without explicit yes/confirm** — this archives historical goals.
- If the API returns an error, report the full error text and do NOT pretend success.
- After success, generate a Second Brain note with tags `fitness,programme-start,cut-<start_date>`.
- If Chris already has an active programme, ask if he wants to abandon it first — never silently overwrite.
- Record the calculation details (BMR, activity factor) so Chris can sanity-check them.
