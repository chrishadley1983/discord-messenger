# Reset Cut — Gym Training Log + Adaptive Plan

Started 5 Sep 2026. Chris has moved the Reset Cut from bodyweight-at-home to a
3-day gym split (upper / lower / full body) on pin-loaded Life Fitness machines
at TSC Tonbridge, plus cardio (5 easy + 1 hard stairmaster interval per week).

## Problem

- The existing workout log (`fitness_workout_sessions` / `_sets`) is bodyweight-only:
  reps + hold seconds, no load, no reps-in-reserve, no failure flag.
- The prescription is generated in Python by calendar week (`programme_generator`),
  never from what was actually lifted. Nothing adapts.
- Cardio has no home: Garmin sync is daily-aggregate only.
- The coach's plan text (Second Brain, `FITNESS.md`, programme notes) still says
  bodyweight + bands, 4x upper/lower, walking only.

## Outcome (agreed with Chris)

Three capture paths, all available:

1. **Peter in Discord** (primary) — free-text session log → parsed → POSTed → coach
   reacts in the same reply with next-session targets.
2. **Garmin activities** (cardio) — watch-recorded stairmaster/bike/walk sessions
   synced to a `garmin_activities` table and linked to cardio logs. *(Phase 2)*
3. **Fitbod CSV import** — optional batch backfill via emailed export. *(Phase 2)*

The programme is **data, not code**: an agreed plan (split, sessions, exercises,
targets, cardio protocol, progression rules, constraints) stored in
`fitness_training_plans`, versioned. It:

- is **best-practice based** — double progression for machines (hit the top of
  the rep range with ≥2 reps in reserve → one plate up; failed set → hold;
  failed twice running → drop ~10% and rebuild), cardio progression in Chris's
  stated order (peak to full 2 min → +30 s on other hard blocks → raise level),
  30–40 min sessions, ≥1 rest day between strength sessions, hip rule.
- **learns from how Chris progresses** — `GET /fitness/next-session` derives every
  exercise's target from logged history, not the calendar.
- **adapts when Chris does something different** — logging an exercise or
  session type that isn't in the plan adds it to the plan (new version, rationale
  recorded) instead of being dropped or scolded. Plan edits via Peter
  ("swap chest press for incline press") go through `PUT /fitness/plan`.

## Phase 1 (this build)

| # | Item | Verify |
|---|------|--------|
| F1 | Migration: `weight_kg`/`rir`/`failed`/`target_reps` on sets; `load_step_kg` on exercises; gym exercise seed; `fitness_cardio_sessions`; `fitness_training_plans` | `npm run db:push` from HB repo succeeds; REST returns new columns |
| F2 | `domains/fitness/training_plan.py` — default plan, rotation, double-progression, cardio progression, reconcile-from-log | `tests/fitness/test_training_plan.py` green |
| F3 | Service + routes: extended `POST /fitness/workout` (returns next-session + week summary), `POST /fitness/cardio`, `GET /fitness/workouts`, `GET /fitness/next-session`, `GET/PUT /fitness/plan`, `GET /fitness/training-summary`; `/fitness/today` plan-aware | curl each endpoint live |
| F4 | Advisor: cardio counts + stalled exercises in snapshot; rules `_rule_cardio_behind`, `_rule_load_stall`, `_rule_progression_win` | `tests/fitness/test_advisor_rules.py` green |
| F5 | Programme row → split `plan`, 3 strength/wk; accountability goal "3 strength sessions" + new "6 cardio sessions/wk" (`fitness_cardio_week` auto-source) | REST shows updated rows |
| F6 | Skills: `log-workout` (gym rewrite), `log-cardio` (new), `training-plan` (new); manifest | manifest.json valid, skills present in WSL symlink |
| F7 | Docs: `hadley_api/README.md`, `docs/playbooks/FITNESS.md`, Second Brain plan note superseding the bodyweight plan | files updated; brain search returns new plan |
| F8 | Backfill Session 1 (Sat 5 Sep upper + stairmaster) via the API; restart hadley_api + discord_bot; verify `/fitness/next-session?type=upper` gives the Session-2 targets Chris expects | curl output matches: pulldown +1 plate, chest press hold 25, row +1 plate, shoulder press hold 25 |

## Phase 2 (built 5 Sep 2026, same day)

| # | Item | Verify |
|---|------|--------|
| P1 | `garmin_activities` table + `source`/`external_id`/`garmin_activity_id` provenance columns (migration `20260905_fitness_phase2_garmin_fitbod.sql`) | db push ok; REST returns table |
| P2 | `domains/fitness/garmin_activities.py`: garth pull → upsert, link cardio (date + compatible modality, HR/calories copied), link strength, auto-create unlogged cardio (`source=garmin`, >= 15 min); hooked after the morning daily sync; `POST /fitness/garmin/sync`, `GET /fitness/garmin/activities`; `POST /fitness/cardio` links on log | live sync run; matching unit tests |
| P3 | `domains/fitness/fitbod_import.py` parser + `POST /fitness/import/fitbod` (dry-run, dedupe by content hash + same-day Peter logs, plan adapts); CSV/txt/json Discord attachments now saved to a local path; skill `fitbod-import` | parser unit tests; dry-run on a sample CSV |
| P4 | Dashboard Training tab: this week, next session (targets + action), next hard cardio blocks, per-exercise load charts, recent sessions, cardio log; plan-aware rationale text | `scripts/build_dashboard.py` renders `training` payload |
| P5 | Weekly review `training` block + `weekly-health` fetcher `training`; skills updated | `GET /fitness/weekly-review` shows block |

**Not done / later:** Garmin strength activities create nothing on their own (only link), because the watch has no loads; a Fitbod→Garmin round trip is not attempted. Fitbod email auto-ingest (watching Gmail for the export) is manual via the skill for now.

## Documentation updates (required by project plan rules)

- **API docs**: `hadley_api/README.md` Fitness section — new endpoints + tables.
- **Peter's knowledge**: `domains/peterbot/wsl_config/CLAUDE.md` already points at
  `FITNESS.md`; `FITNESS.md` gets the plan-driven training section.
- **Skills/playbooks**: `log-workout` rewrite, `log-cardio`, `training-plan` new.
