# Fitness Playbook — Post-Japan Cut

READ THIS for any interaction about weight loss, the cut, gym / strength training, cardio,
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
- **Goal/phase (protein target + framing):** `GET /fitness/goal` · update with `PUT /fitness/goal`

Daily targets (calories, protein, steps) are **programme-specific** — read them
from the programme row, never guess. But note: `/fitness/dashboard` returns
**live** targets (recomputed from current weight) under `nutrition.target_calories`
and `live_targets`, plus a `goal` block (current phase + protein framing). Those
are the authoritative numbers for "what can I eat today" and how to frame protein
— not the static programme row, and never a hardcoded number.

## The 13-Week Cut — What Chris Is Doing

- **Start:** Post-Japan return date (parameter of `/fitness/programme/start`)
- **Height:** 178 cm (used for BMR — do not guess)
- **Target:** −10kg on a 7-day weight trend (not single reading)
- **Daily calories:** TDEE − 550 kcal (auto-computed from Mifflin-St Jeor + step activity)
- **Protein:** goal-phase driven — see **Goal Phases** below. Currently a flat
  **fat-loss floor** (weight loss leads); it auto-switches to the adaptive g/kg
  multiplier once Chris reaches a healthy BMI. Always read the live number from
  `nutrition.target_protein` / `GET /fitness/goal` — never hardcode it.
- **Steps:** 15k baseline (NEAT is the biggest fat-loss lever)
- **Training:** standing week from w/c 7 Sep 2026 — 4 lifts (Mon Upper A push · Tue Lower A · Thu Upper B pull · Sat full body light, 40–45 min) + 1 hard cardio (Wed) + easy cardio Fri — see **Training — the plan is DATA**
- **Mobility:** daily 10-min routine

### Activity Multipliers (recalibrated for walking-heavy lifestyles)

| Avg steps | Factor | Label |
|---|---|---|
| <5k | 1.2 | sedentary |
| 5-8k | 1.375 | light |
| 8-12k | 1.5 | moderate |
| 12-16k | 1.6 | active |
| 16k+ | 1.65 | very active |

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

## Goal Phases — Protein Target & Framing

The protein target AND all coaching framing come from the active programme's
`goal_config` (jsonb), never from hardcoded numbers. Read it via `GET /fitness/goal`
or the `goal` block on `/fitness/dashboard`:

- `current_phase` — stored phase (e.g. `fat_loss`).
- `effective_phase` — phase after the auto-switch (what's live right now).
- `phase` — `{label, focus, protein:{mode, g|g_per_kg}, protein_note, rule}`.
- `auto_switch` — e.g. `{metric: "bmi", below: 25.0, to_phase: "muscle_build"}`.

**Two phases today:**

| Phase | Protein | Framing |
|---|---|---|
| `fat_loss` (now) | **fixed 125 g** | Weight loss first; protein is a satiety/muscle *floor*, not a max |
| `muscle_build` | **adaptive** (programme's `protein_g_per_kg`, currently 2.0 g/kg) | Healthy weight reached — protect/build lean mass |

**Auto-switch:** when the 7-day-trend **BMI drops below 25** (~79 kg at 178 cm),
the effective phase flips `fat_loss → muscle_build` (forward-only). It's applied
live on every dashboard build and persisted (with a `phase_changed` note) the next
time recalibrate runs. **Calories are unaffected** — the deficit keeps running
toward target weight; only the protein target + framing change.

**Peter editing the goal (with Chris's approval):**
- Flip phase: `PUT /fitness/goal {"current_phase": "muscle_build"}`
- Retune the floor: `PUT /fitness/goal {"phases": {"fat_loss": {"protein": {"mode":"fixed","g":140}}}}`
- Change the switch: `PUT /fitness/goal {"auto_switch": {"metric":"bmi","below":24.0,"to_phase":"muscle_build"}}`

Never assert "180 g" or "protein protects muscle, non-negotiable" — that framing
is phase-specific and now lives in `goal.rule` / `goal.protein_note`.

**New programmes** (`POST /fitness/programme/start`) are seeded with this
fat-loss-first config automatically: the floor is ~1.4 g/kg of starting weight
(e.g. ~125 g at 90 kg), with the BMI-25 auto-switch to muscle-build. Tune it any
time via `PUT /fitness/goal`.

### Training — the plan is DATA (Sep 2026, gym version)

Since 5 Sep 2026 Chris trains at TSC Tonbridge (pin-loaded Life Fitness
machines + dumbbells). **From w/c 7 Sep 2026 it is a fixed standing week**
(plan v6; the 3-day any-days rotation of 5–6 Sep is superseded):

| Day | Session | Page | Duration |
|---|---|---|---|
| Mon | **Upper A — push** (`upper_a`): flat DB press, incline DB press, machine shoulder press, DB flye, incline DB curl | `upper-a.html` | 40 min |
| Tue | **Lower A** (`lower_a`): leg press, DB RDL, seated leg curl, DB split squat, hip abduction, leg-press calf raise | `lower-a.html` | 45 min |
| Wed | **Hard cardio** — 20-min pyramid, hard blocks L9, peak 90 s. The stairmaster is the worked example only; bike / rower / treadmill intervals are interchangeable | `stairmaster-pyramid.html` | 20 min |
| Thu | **Upper B — pull** (`upper_b`): lat pulldown, seated row, light chest press (2 sets, RPE 7), face pull, lateral raise, tricep pushdown | `upper-b.html` | 45 min |
| Fri | **Easy cardio** 30–40 min, RPE 3–4 | — | — |
| Sat | **Full body, light** (`full_body`): goblet squat, cable pull-through, single-arm row, light chest press, kneeling cable crunch | `full-body.html` | 40 min |
| Sun | Rest or walk | — | — |

- Easy cardio (bike/walk, RPE 3–4, 10–20 min) is **optional** after the Mon/Tue/Thu/Sat lifts.
  A day of **8–10k steps counts as easy cardio**. Only the Friday session is a target
  (`weekly.cardio_easy = 1`); extras are a bonus, never a nag.
- **No second hard cardio session before plan week 6** (w/c 12 Oct; plan week 1 = w/c 7 Sep,
  `schedule_from`). Plan-week numbering, not programme-week, gates the cardio extension too.
- Upper and lower sit on consecutive days by design (`min_rest_days_between_strength = 0`);
  never two upper sessions back to back.
- **Weaker (left) side leads** on unilateral work (split squat, incline curl, single-arm row);
  the stronger side matches its reps. **Log reps-in-reserve on the last set** of each exercise.
- Session types `upper` (machines, 5 Sep) and `upper_db` (dumbbells, 6 Sep) are **retired** —
  kept in the plan only so history resolves. Log Mon as `upper_a`, Thu as `upper_b`.
- **Session pages** (phone): `https://chris-reset-cut.surge.sh/upper-a.html` · `lower-a.html` ·
  `upper-b.html` · `full-body.html` (also `GET /fitness/session-pages/<name>` on the LAN, and
  linked from the dashboard Training tab). Each shows the API's next-session target per exercise
  (baked in at the last dashboard rebuild), keeps the weights he types on the phone, and clears
  the set ticks automatically on a new day. "Reset ticks" never touches weights. The pages do
  **not** log — he still tells Peter what he did (`log-workout`).

The programme row has `split = plan`; the actual plan lives in
`fitness_training_plans` and is versioned. **Never describe the old bodyweight
4x upper/lower plan — it is superseded.**

- **Read the plan:** `GET /fitness/plan` · **next session:** `GET /fitness/next-session`
  · **this week:** `GET /fitness/training-summary` · **history:** `GET /fitness/workouts`, `GET /fitness/cardio`
- **Log:** `POST /fitness/workout` (loads, reps, RIR, failed reps) and `POST /fitness/cardio` —
  skills `log-workout`, `log-cardio`. Off-plan exercises / session types are **added to the
  plan automatically** (new version, rationale recorded). Never scold a deviation.
- **Edit the plan:** `PUT /fitness/plan` with a `patch` + `rationale` — skill `training-plan`.

**Progression rules (the API applies them — read `action`/`reason`, never compute loads yourself):**
- Double progression: every set at/above target reps with >= 2 reps in reserve -> **one plate up**.
- A failed set -> **hold** the load, aim for clean sets. Failed two sessions running at the same load -> **~10% deload** and rebuild.
- Same top load for 3 sessions -> **stall** flag (advisor) -> change one lever (a rep per set, 3-s lowering, or a plate down and rebuild).
- Fixed days (see table above); `rest_gap_ok` is only false when he already lifted **today**.
  Rotation Upper A -> Lower A -> Upper B -> full body. Machine shoulder press comes after two
  dumbbell presses on Upper A — expect it pre-fatigued (no A/B order swap any more).
- Hard-cardio pyramid (stairmaster or any hard modality — `intensity: hard` is what counts):
  peak block to a full 120 s at the current level -> +30 s on the other hard blocks -> raise the
  level; plan week 4+ (w/c 28 Sep) extend to 25-30 min. **Hip rule:** sharp/pinching pain -> stop,
  switch to the bike; recurring -> physio screen (`pain_flag` on the cardio log).
- In a deficit, holding a load for a few sessions is normal. Say so.

**Garmin + Fitbod (Phase 2):** watch-recorded activities sync to `garmin_activities` every
morning and link to logged cardio/strength by date (HR + calories copied across); recorded
cardio nobody logged is auto-created (`source: garmin`) so it counts toward the easy
target — never double-log it. Garmin can only infer `hard` for stair-climbing; a hard bike /
rower session must be logged through Peter (`intensity: hard`) or it lands as easy. On demand: `POST /fitness/garmin/sync`. Fitbod exports (CSV
dropped in Discord or emailed) import via skill `fitbod-import` → `POST /fitness/import/fitbod`
(dry-run first). The dashboard Training tab shows this week, the next session with targets,
load progress per exercise, recent sessions and the cardio log.

Legacy splits (`5x_short`, `4x_upper_lower`) are still generated by `programme_generator.py` if a programme uses them.

## Weight Reading Rules

- **Trust the 7-day trend, not the daily scale.**
  Day-to-day weight varies 0.5–1.5kg from water/sodium/carbs. The endpoint
  returns both `latest_raw` and `trend_7d`. Always lead with trend.
- **Stall detection:** if slope > −0.1 kg/week over 10+ days, flag it. The
  `/fitness/dashboard` endpoint sets `weight.stalled=true` when this happens.
- **Stall protocol:** drop daily calories by 100, add 2k steps/day — but if
  the plan gap is >2 kg, the dashboard escalates to −200 kcal +3k steps plus a
  logging audit. Never drop below 1700 kcal without discussing it with Chris.
- **Do NOT panic over single readings.** A 1kg overnight jump is almost
  always water — don't tell Chris to "eat less tomorrow".

## Plan Maths — the Hard-Truth Rules (Aug 2026)

`/fitness/dashboard` returns a `plan` block — the single source of truth for
"am I on track". Every check-in surface (health digest, cut kickoff, dashboard
page, advisor) reads it; never recompute or soften it.

- `gap_vs_line_kg` — signed gap vs this week's linear target line (+ = behind)
- `required_kg_per_week` vs `weight.slope_kg_per_week` — needed from here vs actual
- `required_rate_unsafe` — true when the required rate exceeds 1% of body
  weight/week: the plan itself is broken; propose a re-baseline (new date or
  target), don't just cheer harder
- `projected_end_weight` / `projected_finish_date` — where the current rate lands
- `on_track` tiers: ahead / on_track / settling / behind / well_behind / off_track

**Tone rules:** when the tier is behind/well_behind/off_track, state the gap and
required-vs-actual numbers plainly — "a touch", "roughly", "drifting" are
banned. Honest ≠ harsh (Chris is tapering sertraline): no shame, no
catastrophising — the numbers are the problem, not his character. The advisor
also reports `unlogged_days_7d` (≥2 unlogged days in the last week = that IS the
story) and `weeks_since_diet_break` (plan prescribes one every 4–6 weeks).

**Auto-recalibrate:** Mondays 08:05 UK an infra job recalibrates targets from
trend weight AND syncs the accountability goal rows. Targets on the dashboard
are always the live ones.

## Dashboard Refresh (works from anywhere via Peter)

The public dashboard is https://chris-reset-cut.surge.sh (passcode-gated; auto
rebuilt daily at 08:20 UK). The page's own Refresh button also works from
anywhere: on the surge (https) page it POSTs sha256(passcode) to the
`dashboard-refresh` Supabase Edge Function (source: `supabase/functions/
dashboard-refresh/index.ts`), which queues a row in
`dashboard_refresh_requests`; a poller in `hadley_api/fitness_routes.py`
(every 20 s) verifies the hash against `DASHBOARD_PASSCODE` and runs the same
rebuild+redeploy, and the page reloads when it sees a new build (~2 min total).
Every `POST /fitness/workout`, `POST /fitness/cardio` and a real Fitbod import also
kicks a debounced rebuild+redeploy automatically (~90 s after the last log), so
the page catches up with the day's sessions without anyone asking.
When Chris asks Peter directly to "refresh the dashboard", run:

```
curl -s -X POST http://172.19.64.1:8100/fitness/dashboard/refresh
```

This pulls fresh Withings + Garmin data, rebuilds, and redeploys the surge
page (~1 min). Poll `GET /fitness/dashboard/refresh/status` until
`building=false`, then confirm with the new `generated_at`. Tell Chris the
surge page is updated — no LAN needed on his end.

## Calorie Budget Responses

When Chris asks "how much can I still eat?":
1. `GET /fitness/dashboard` — returns `nutrition.calories` (consumed) and
   `nutrition.target_calories` (programme target).
2. Remaining = target − consumed.
3. If he hasn't hit protein (`nutrition.protein_g < target_protein * 0.8`),
   prioritise protein in the remaining calories.

## Logging Workouts

**One training day = one session, always.** Each gym day is logged as its own
`fitness_workout_sessions` row with its own `session_type`; the plan carries one
session entry per distinct day-type (`upper` machines, `upper_db` dumbbells, `lower`,
`full_body`, ...). Never append a day's exercises onto another day's session type —
Chris wants to be able to rebuild a daily picture of exactly what was done on each
date (rule set 6 Sep 2026 after the dumbbell day was merged into machine upper).

Skill `log-workout` -> `POST /fitness/workout` with per-set `weight_kg`, `reps`, `rir`,
`failed`, `target_reps`. The response carries `plan_changes`, `next_time` (next-session
targets) and `week` — coach from those. Cardio: skill `log-cardio` -> `POST /fitness/cardio`
(returns `next_hard`). Never say "logged" without a 200.

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
