---
name: log-workout
description: Log a gym strength session (machines, loads, reps, reps-in-reserve, failures) from natural language and coach the next one
trigger:
  - "gym done"
  - "finished upper"
  - "finished lower"
  - "finished full body"
  - "done upper body"
  - "done lower body"
  - "session 2"
  - "training log"
  - "lat pulldown"
  - "chest press"
  - "seated row"
  - "leg press"
  - "finished workout"
  - "logged workout"
  - "just did my session"
scheduled: false
conversational: true
channel: null
---

# Log Workout (gym)

## Purpose

Chris trains a 3-day split (upper / lower / full body) on pin-loaded Life
Fitness machines at TSC Tonbridge, inside the Reset Cut deficit. He types what
he did — loads, sets × reps, how it felt — and you (1) log it exactly,
(2) let the plan adapt to anything off-plan, (3) coach the next session from
the response. The API does the progression maths; you parse and present.

Read `FITNESS.md` → "Gym training log + adaptive plan" for the rules.

## Workflow

1. **Detect the session type**: `upper` / `lower` / `full_body`. "Upper body",
   "push/pull day" → `upper`. "Legs" → `lower`. Anything else he names (e.g.
   "arms") → use that word as `session_type` (snake_case); the plan will add it.
   If genuinely unclear, ask ONE question before logging.

2. **Parse each exercise line** into sets. Chris's shorthand:
   - `Lat pulldown 33 kg, 3×10, a few reps in reserve` → 3 sets, reps 10, weight_kg 33, rir 3
   - `Chest press 25 kg, 3×10, failed rep 7 of set 3` → sets 1-2 reps 10, set 3 reps 6 **failed:true**, target_reps 10
   - `Shoulder press 25 kg, 3×10, failed on final rep` → set 3 reps 9 failed:true
   - "a few in reserve" → rir 3 · "a couple left" → rir 2 · "one left" → rir 1 · "to failure" → rir 0 · not stated → omit (null)
   - Always set `target_reps` to the prescribed reps (10 unless he says otherwise).
   - Slugs: `lat-pulldown`, `chest-press`, `seated-row`, `shoulder-press`, `leg-press`,
     `leg-extension`, `seated-leg-curl`, `hip-abduction`, `seated-calf-raise`, `pec-fly`,
     `rear-delt-fly`, `cable-face-pull`, `cable-curl`, `triceps-pushdown`, `lateral-raise`,
     `assisted-pull-up`, `cable-glute-kickback`, `cable-pallof-press`. Full list:
     `GET /fitness/exercises`. An unknown movement → invent a kebab-case slug and
     pass `exercise_name` + `category` (push/pull/legs/core) so it's auto-created.

3. **Parse session-level fields**: `rpe` if given, `duration_min`, `notes`
   (keep his own words — "limiter was quad endurance", "goes last so pre-fatigued").

4. **POST** (never say "logged" until you get a 200):
   ```
   curl -s -X POST http://172.19.64.1:8100/fitness/workout \
     -H "x-api-key: $HADLEY_AUTH_KEY" -H "Content-Type: application/json" \
     -d '{
       "session_type": "upper", "session_date": "2026-09-05", "duration_min": 40, "rpe": 7,
       "notes": "Session 1. Shoulder press last, pre-fatigued.",
       "sets": [
         {"exercise_slug": "lat-pulldown", "set_no": 1, "reps": 10, "weight_kg": 33, "rir": 3, "target_reps": 10},
         {"exercise_slug": "lat-pulldown", "set_no": 2, "reps": 10, "weight_kg": 33, "rir": 3, "target_reps": 10},
         {"exercise_slug": "lat-pulldown", "set_no": 3, "reps": 10, "weight_kg": 33, "rir": 3, "target_reps": 10},
         {"exercise_slug": "chest-press", "set_no": 3, "reps": 6, "weight_kg": 25, "rir": 0, "failed": true, "target_reps": 10}
       ]
     }'
   ```
   `session_date` only if he's logging a past day (default = today).

5. **Read the response** — it contains everything you need to coach:
   - `plan_changes` — what the plan adapted (new exercise / session type). Tell him.
   - `next_time.exercises[]` — per exercise: `action` (`increase` / `hold` / `deload` / `start`),
     `weight_kg` (null = "one plate up, stack increment unknown"), `reason`. And `order_variant` (A/B).
   - `week` — `strength.done/target`, `strength.next` (rotation), `cardio.easy_done/easy_target`,
     `cardio.hard_done/hard_target`, `progressions_this_week`, `stalled`.

6. **If he also describes cardio in the same message** (stairmaster, bike, walk),
   log it with the `log-cardio` skill in the same turn — don't ask.

## Output Format

```
✅ **Upper logged** — Sat 5 Sep · Session 1 · RPE 7

Lat pulldown 33 kg 3×10 (3 RIR) · Chest press 25 kg 10/10/6✗ · Seated row 30 kg 3×10 (3 RIR) · Shoulder press 25 kg 10/10/9✗

**Next upper (order B — shoulder press first):**
• Shoulder press — hold 25 kg, aim a clean 3×10
• Seated row — up one plate
• Chest press — hold 25 kg, aim a clean 3×10
• Lat pulldown — up one plate

**This week:** strength 1/3 (next: lower) · cardio 1/5 easy, 1/1 hard
🎉 PRs / plan: (only if `progressions_this_week` or `plan_changes` is non-empty)

[1 line of coaching — from `reason` fields, the rest-gap flag, or the deficit context. No softeners.]
```

## Rules

- **NEVER say "Logged" without a 200.** On error, show the error and offer to retry.
- **Log what he did, not what was planned.** Failed reps stay failed; reduced sets stay reduced.
- Coach from the API's `action`/`reason` — don't invent progression numbers. If `weight_kg`
  is null on an `increase`, say "one plate up" and ask him to tell you the new number next time.
- Off-plan is fine: the plan adapts. Never tell him he "should have" done the planned session.
- Hip: if he mentions sharp/pinching pain, echo the plan rule (stop, bike) and put it in `notes`.
- A/B order alternates automatically (`order_variant`); mention it so shoulder press isn't always last.
- Weekly accountability goal `fitness_strength_week` auto-updates after the POST.
