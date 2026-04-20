# Fitness Playbook — Post-Japan Cut

READ THIS for any interaction about weight loss, the cut, bodyweight training,
mobility, or the fat-loss programme. For running-specific topics (VDOT, pace,
race prep), read `TRAINING.md` instead. They coexist.

## Data Sources — ALWAYS FETCH, NEVER HARDCODE

- Active programme: `GET /fitness/programme`
- Today's prescription + workout: `GET /fitness/today`
- Full daily status: `GET /fitness/dashboard`
- Weight trend (smoothed): `GET /fitness/trend?days=30`
- Weekly review bundle: `GET /fitness/weekly-review`
- Exercise library: `GET /fitness/exercises`
- **Recalibrate targets:** `POST /fitness/programme/recalibrate`

Daily targets (calories, protein, steps) are **programme-specific** — read them
from the programme row, never guess. But note: `/fitness/dashboard` returns
**live** targets (recomputed from current weight) under `nutrition.target_calories`
and `live_targets`. Those are the authoritative numbers for "what can I eat
today", not the static programme row.

## The 13-Week Cut — What Chris Is Doing

- **Start:** Post-Japan return date (parameter of `/fitness/programme/start`)
- **Height:** 178 cm (used for BMR — do not guess)
- **Target:** −10kg on a 7-day weight trend (not single reading)
- **Daily calories:** TDEE − 550 kcal (auto-computed from Mifflin-St Jeor + step activity)
- **Protein:** 1.67 g per kg bodyweight (rounded to 5g) — research floor is
  1.6 g/kg; 1.67 balances muscle-retention with Chris's real-world struggle
  to hit very high protein
- **Steps:** 15k baseline (NEAT is the biggest fat-loss lever)
- **Training:** 5x/week, 20-min bodyweight sessions
- **Mobility:** daily 10-min routine

### Activity Multipliers (recalibrated for walking-heavy lifestyles)

| Avg steps | Factor | Label |
|---|---|---|
| <5k | 1.2 | sedentary |
| 5-8k | 1.375 | light |
| 8-12k | 1.5 | moderate |
| 12-16k | 1.6 | active |
| 16k+ | 1.75 | very active |

These are lower than textbook Mifflin multipliers (1.55/1.725/1.9) because
those buckets assume manual-labour jobs or 6-7 days of hard training. For a
walking-driven active day the bottom-up MET calc (BMR + walking METs + TEF +
other NEAT) clusters around 1.6 for 15k steps.

## Weight-Adaptive Targets — KEY RULE

**BMR drops as weight drops.** Every 1kg lost shaves ~10 kcal off BMR, which
at the 1.6 activity multiplier is ~16 kcal off TDEE. Over 5kg that's 80 kcal
— enough to turn a working deficit into a stall.

The system handles this automatically:
1. `/fitness/dashboard` always recomputes `target_calories` and `target_protein`
   from the **latest trend weight** (not the programme start weight). The
   response also returns `target_drift` showing how far the stored programme
   targets have drifted from the live values.
2. When drift exceeds 80 kcal / 10g protein, the dashboard raises a flag:
   `TARGETS DRIFTED — run /fitness/programme/recalibrate`.
3. `/fitness/weekly-review` checks drift every Sunday and sets
   `adjustment.recalibrate_recommended = true` when appropriate.
4. `POST /fitness/programme/recalibrate` (no body required — uses latest
   trend weight + 7-day step avg) updates the stored programme row with the
   new TDEE / calorie / protein targets.

**When Peter should trigger recalibrate:**
- User-facing: whenever the dashboard `flags` array contains "TARGETS DRIFTED".
- Automatic: weekly-cut-review skill should call it when
  `adjustment.recalibrate_recommended` is true.
- Manual: after any big weight move (+/- 3kg in one week).

**Never** recalibrate based on a single scale reading — always use the 7-day
trend. That's what `/fitness/programme/recalibrate` does by default.

### Training Split (5x_short)
| Day | Session | Focus |
|---|---|---|
| Mon | Push (upper) | chest/shoulders/tris |
| Tue | Legs A | quads |
| Wed | Pull + core | back/rear delts/abs |
| Thu | Legs B | posterior chain |
| Fri | Full body | conditioning |
| Sat | Mobility + walk | active recovery (15k+ steps) |
| Sun | Rest | full rest |

Progression: +1 rep/set/week (or +5s hold/week), capped at 2x base volume.

## Weight Reading Rules

- **Trust the 7-day trend, not the daily scale.**
  Day-to-day weight varies 0.5–1.5kg from water/sodium/carbs. The endpoint
  returns both `latest_raw` and `trend_7d`. Always lead with trend.
- **Stall detection:** if slope > −0.1 kg/week over 10+ days, flag it. The
  `/fitness/dashboard` endpoint sets `weight.stalled=true` when this happens.
- **Stall protocol:** drop daily calories by 100, add 2k steps/day. Never
  drop below 1700 kcal without discussing it with Chris.
- **Do NOT panic over single readings.** A 1kg overnight jump is almost
  always water — don't tell Chris to "eat less tomorrow".

## Calorie Budget Responses

When Chris asks "how much can I still eat?":
1. `GET /fitness/dashboard` — returns `nutrition.calories` (consumed) and
   `nutrition.target_calories` (programme target).
2. Remaining = target − consumed.
3. If he hasn't hit protein (`nutrition.protein_g < target_protein * 0.8`),
   prioritise protein in the remaining calories.

## Logging Workouts

Chris logs conversationally: "done push workout", "finished legs b, RPE 8".
See the `log-workout` skill. The flow:
1. Detect session type
2. Fetch today's prescription via `/fitness/today` for defaults
3. POST to `/fitness/workout` with the sets
4. Confirm with current week's strength count

**Never** say "Logged" without a real POST + 200 response.

## Logging Mobility

Morning or evening slot. Each slot logs separately; the daily habit ticks as
soon as *any* slot is logged. See `log-mobility` skill.

## Weekly Review (Sunday)

`weekly-cut-review` runs Sunday 09:00. It:
1. Pulls `/fitness/weekly-review`
2. Generates a PT-grade breakdown (weight 30pts, strength 25pts, protein 20pts, calories 15pts, mobility 10pts)
3. POSTs to `/fitness/weekly-checkin` to persist the snapshot
4. Saves the report text to Second Brain with tag `fitness,cut,week-<N>`

**While the programme is active, weekly-cut-review REPLACES weekly-health as
the primary Sunday report.** The generic weekly-health still runs (not
suspended) — the cut review is just more programme-aware.

## How Peter Should Respond

### Good
- "Your trend is 93.4kg, down 0.9kg from start. On track for −0.65 kg/wk."
- "You have 930 kcal left today. Prioritise protein — you're at 85g, need 85g more."
- "Today's push session: 3×11 push-ups, 3×7 pike push-ups, 3×11 chair dips..."
- "STALL: 10 days of flat trend. Recommend dropping to 1850 kcal and pushing steps to 14k."

### Bad
- "You're at 94.1kg today, up 0.8kg — what did you eat yesterday?"
  (Single reading panic — show the trend instead.)
- "I think you should aim for 2000 kcal." (Hardcoded — read from programme.)
- "Do some push-ups and squats today." (Generic — read today's prescription.)

## Accountability Goals Auto-Created by This Programme

When `/fitness/programme/start` runs, it creates 6 goals:
1. `Lose Xkg (post-Japan cut)` — auto-source `weight`
2. `Daily calories ≤ N` — auto-source `nutrition_calories`
3. `Protein ≥ Ng daily` — auto-source `nutrition_protein`
4. `15k steps daily` — auto-source `garmin_steps`
5. `5 strength sessions per week` — auto-source `fitness_strength_week`
6. `Daily mobility routine` — auto-source `fitness_mobility_today`

The last two use the new `count_week` and `exists_today` aggregations in
`domains/accountability/auto_sources.py`.

## Debugging

| Symptom | Likely cause | Check |
|---|---|---|
| Dashboard shows no programme | Not yet started | `GET /fitness/programme` returns null |
| Trend stuck at same value | Weight not syncing | Withings sync job, `weight_readings` table |
| Calories not updating | Nutrition logs missing | `GET /nutrition/today` |
| Strength goal not ticking | `count_week` not wired | `auto_sources.py` registry |
| "Unknown exercise slug" | Seed migration not run | `SELECT count(*) FROM fitness_exercises;` |
