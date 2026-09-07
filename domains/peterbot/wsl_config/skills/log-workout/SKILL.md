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

Chris trains a fixed standing week (from w/c 7 Sep 2026) at TSC Tonbridge on
machines + dumbbells, inside the Reset Cut deficit: **Mon Upper A (push) ·
Tue Lower A · Thu Upper B (pull) · Sat full body (light)**, plus hard cardio
Wed and easy cardio Fri. He types what he did — loads, sets × reps, how it
felt — and you (1) log it exactly, (2) let the plan adapt to anything
off-plan, (3) coach the next session from the response. The API does the
progression maths; you parse and present.

Read `FITNESS.md` → "Training — the plan is DATA" for the rules and the full
exercise table.

## Workflow

1. **Detect the session type**: `upper_a` / `lower_a` / `upper_b` / `full_body`.
   "Upper A", "push day", Monday, flat/incline DB press + shoulder press + flye + curls → `upper_a`.
   "Upper B", "pull day", Thursday, pulldown + row + face pull + lateral raise + pushdown → `upper_b`.
   "Legs", "Lower A", Tuesday → `lower_a`. "Full body", Saturday → `full_body`.
   (`upper` and `upper_db` are the retired 5–6 Sep sessions — never log new sessions to them.)
   Anything else he names (e.g. "arms") → use that word as `session_type` (snake_case); the plan will add it.
   **Different days are always different sessions (Chris, 6 Sep 2026).** Never fold a
   day's exercises into an existing session type just because the body part matches — if
   the exercise set differs from the plan's session of that name (other equipment, other
   venue), give it its own `session_type` so the plan gets a separate session and the
   log keeps a clean per-day picture. Peter merging the Sunday dumbbell day into the
   Saturday machine `upper` produced an 8-exercise 40-min "upper" that had to be split.
   If genuinely unclear, ask ONE question before logging.

2. **Parse each exercise line** into sets. Chris's shorthand:
   - `Lat pulldown 33 kg, 3×10, a few reps in reserve` → 3 sets, reps 10, weight_kg 33, rir 3
   - `Chest press 25 kg, 3×10, failed rep 7 of set 3` → sets 1-2 reps 10, set 3 reps 6 **failed:true**, target_reps 10
   - `Shoulder press 25 kg, 3×10, failed on final rep` → set 3 reps 9 failed:true
   - "a few in reserve" → rir 3 · "a couple left" → rir 2 · "one left" → rir 1 · "to failure" → rir 0 · not stated → omit (null)
   - Always set `target_reps` to the prescribed reps (10 unless he says otherwise; incline DB press is 8,
     flye/leg curl/pushdown 12, face pull/abduction/calf raise 15 — read `GET /fitness/plan`).
   - RIR is logged on the **last set** of each exercise by design; put it on that set, leave the others null.
   - Unilateral work (split squat, incline curl, single-arm row): weaker **left** side leads, right matches.
     Log the reps the left side did; note a left-side failure in `notes`. Incline curl has a 4th left-only set.
   - Slugs — Upper A: `db-flat-bench-press`, `db-incline-press`, `shoulder-press`, `db-flye`, `db-incline-curl`.
     Lower A: `leg-press`, `db-romanian-deadlift`, `seated-leg-curl`, `db-split-squat`, `hip-abduction`,
     `leg-press-calf-raise`. Upper B: `lat-pulldown`, `seated-row`, `chest-press`, `cable-face-pull`,
     `lateral-raise`, `triceps-pushdown`. Full body: `goblet-squat`, `cable-pull-through`, `single-arm-db-row`,
     `chest-press`, `kneeling-cable-crunch`. Others: `leg-extension`, `seated-calf-raise`, `pec-fly`,
     `rear-delt-fly`, `cable-curl`, `assisted-pull-up`, `cable-glute-kickback`, `cable-pallof-press`. Full list:
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

**This week:** strength 1/4 (next: lower_a) · cardio 0/1 hard, 0/1 easy
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
- Exercise order is fixed per page (no A/B swap on the standing week; `order_variant` is null). Mon→Tue back-to-back lifts are by design — never flag them.
- Weekly accountability goal `fitness_strength_week` auto-updates after the POST.
