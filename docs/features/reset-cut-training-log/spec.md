# Reset Cut — Gym Training Log + Adaptive Plan

Started 5 Sep 2026. Chris has moved the Reset Cut from bodyweight-at-home to
the gym (pin-loaded Life Fitness machines + dumbbells) at TSC Tonbridge.
Phases 1–2 (5 Sep) were built for a 3-day any-days rotation (upper / lower /
full body) + 5 easy + 1 hard cardio. **Superseded on 7 Sep 2026 by the standing
week below (plan v6)** — see "Schedule revision (7 Sep 2026)".

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

## Schedule revision (7 Sep 2026) — standing week, plan v6

Chris's training schedule from w/c 7 Sep 2026 (4 lifting sessions, 1 hard cardio, easy
cardio otherwise). This is what the plan data, the default plan in `training_plan.py`,
the dashboard copy, the skills and `FITNESS.md` now describe.

| Day | Session | Page | Duration |
|---|---|---|---|
| Mon | Upper A — push (flat DB press, incline DB press, machine shoulder press, flye, incline curl) | `upper-a.html` | 40 min |
| Tue | Lower A (leg press, DB RDL, seated leg curl, DB split squat, hip abduction, calf raise) | `lower-a.html` | 45 min |
| Wed | Hard cardio — pyramid, 20 min, hard blocks L9, peak 90 s. **The stairmaster is just the example; any hard-cardio modality is interchangeable** | `stairmaster-pyramid.html` | 20 min |
| Thu | Upper B — pull (lat pulldown, seated row, light chest press, face pull, lateral raise, tricep pushdown) | `upper-b.html` | 45 min |
| Fri | Easy cardio, 30–40 min, RPE 3–4 | — | — |
| Sat | Full body, light (goblet squat, cable pull-through, single-arm row, light chest press, kneeling cable crunch) | `full-body.html` | 40 min |
| Sun | Rest or walk | — | — |

- Easy cardio (bike/walk, RPE 3–4, 10–20 min) optional after Mon/Tue/Thu/Sat. Daily steps
  8–10k count as easy cardio. No second hard session before week 6.
- Progression: double progression — hit the top of the rep range on all sets, then +1
  plate/increment. Weaker (left) side leads on unilateral work; stronger side matches reps.
  Log reps-in-reserve on the last set of each exercise.
- Pages: single-file HTML, no dependencies except Google Fonts, illustrations embedded as
  base64. Built in a claude.ai chat (`/mnt/user-data/outputs/…`); local copies in
  `~/Downloads/` (`upper-a.html`, `lower-a_2.html` = latest Lower A, `upper-b.html`).
  `full-body.html` and `stairmaster-pyramid.html` are not saved locally yet.

**How it is encoded (plan v6 / `DEFAULT_PLAN`):** `schedule` (7 entries Mon..Sun),
`schedule_from = 2026-09-07` (plan week 1 — gates "extend to 25–30 min from week 4" and
"no second hard session before week 6"), `weekly = {strength 4, cardio_easy 1, cardio_hard 1,
min_rest_days_between_strength 0}`, sessions `upper_a` / `lower_a` / `upper_b` / `full_body`
with per-session `duration_min` + `page`, `upper` + `upper_db` kept as `status: retired`,
`cardio.hard.modality_is_example = true` + `modalities`, `cardio.easy.steps_count_as_easy`.
`fitness_programmes.weekly_strength_sessions` 3 → 4; accountability goals "4 strength
sessions per week" and "2 cardio sessions per week (1 hard + 1 easy)".

**Alignment notes (flagged to Chris 7 Sep):**
1. *Mon → Tue back-to-back lifts* conflicted with the 5 Sep rule ">= 1 rest day between
   strength sessions". Resolved: gap rule relaxed to "not twice on one day; never two upper
   sessions back to back" — upper/lower alternation is standard practice.
2. *"Hit the top of the rep range on all sets, then +1"* is stricter than the implemented
   rule (all sets at **target** reps with >= 2 RIR, or all at the top of the range → up).
   The implemented rule was verified by Chris on 5 Sep (pulldown 3×10 @ 33 → "+1 plate").
   Code left as is; Chris to confirm which he wants.
3. *Easy-cardio target* dropped 5 → 1 (Friday). The optional post-lift sessions and 8–10k-step
   days are guidance, not a counted target. Steps target on the programme row stays 15k.
4. *Week numbering*: programme week (started 17 Aug) ≠ schedule week. w/c 7 Sep is programme
   week 4, which would have fired the "extend to 25–30 min" note against a 20-min schedule.
   Plan week (from `schedule_from`) now governs both week-gated cardio rules.
5. *Garmin auto-import* can only infer `hard` for stair-climbing; a hard bike/rower session
   must be logged via Peter or it counts as easy.
6. The pages' hand-set kg defaults do not always match `GET /fitness/next-session` (e.g. the
   page holds the incline curl at 6 kg after the failed left-arm set; the API says hold 8 kg,
   and it would move the flat press 12 → 14 kg because no RIR was logged). Productionised
   pages should read the API's targets (Phase 3 below).

## Phase 3 (built 7 Sep 2026) — session pages: reset function + persistence

Before: each session page (`upper-a.html` etc.) held `state[]` (per-exercise `ticks[]` and
`kg`) in memory only. **Reset ticks** cleared all ticks and weight inputs and re-rendered both
views. Nothing persisted across reloads; each page was independent. Play mode opened at the
first exercise with incomplete ticks.

Now: `domains/fitness/session_pages/` — four committed single-file pages (`pages/*.html`,
Google Fonts only, illustrations embedded as base64) sharing one runtime (`runtime.js`,
embedded between `/*RUNTIME-START*/…END*/` markers; `python -m domains.fitness.session_pages
--sync` re-embeds it, `test_session_pages` fails on drift). `dashboard_site.build_and_deploy`
bakes each page's `GET /fitness/next-session` targets into a `/*TARGETS-START*/…END*/` block
and ships the pages next to `index.html` on surge (`https://chris-reset-cut.surge.sh/upper-a.html`
etc.), mirrors them to `data/session-pages/` for `GET /fitness/session-pages/<name>` on the LAN,
and links them from the dashboard Training tab (Next card + "Session pages" card).

| # | Item | Built as | Verified |
|---|------|----------|----------|
| S1 | Reset is **per session**: clears ticks only, never the weights | `$("reset")` clears `state[].ticks` + `rc:<page>:ticks`; `kg` and `rc:<page>:kg` untouched | Playwright: reset → 0 ticks, kg still 17.5 |
| S2 | Weights **persist per exercise**; last-used is the next default | localStorage `rc:<page>:kg` keyed by exercise slug (entered kg) **over** build-time `TARGETS` from the API (`weight_kg` / `action` / `reason` rendered as a target line on each card) **over** the page's static suggestion | reload → kg prefilled; target lines show "Up 14 kg · …" from the live API |
| S3 | Ticks **auto-clear on next open** when stored date ≠ today | `rc:<page>:ticks = {date, ticks}`; restored only when `date === today` | Playwright with Date shifted +1 day → 0 ticks, kg kept |
| S4 | Reset does **not touch the play-mode cursor** | `playBtn` still `findIndex(first incomplete)` — unchanged line | exercise 1 fully ticked → play opens at "2 / n" |
| S5 | Hard-cardio page reset is separate (timer only) | **not in this repo** — `stairmaster-pyramid.html` was never saved locally; unchanged | n/a |
| S6 | Pages live in the repo and deploy with the dashboard; `sessions.*.page` names them | `session_pages/pages/`, `_deploy(extra_files)`, `GET /fitness/session-pages/{name}`, Training-tab links | local build lists 4 pages; tests |

Not done in Phase 3: the page does not POST the finished session to `/fitness/workout` — logging
still goes through Peter (`log-workout`). Targets refresh only when the dashboard rebuilds (daily
08:20, after every Peter log, or on Refresh).

**Decision (7 Sep, taken by Claude, for Chris to confirm):** the session pages are deployed
**without** the dashboard's passcode gate. They expose exercise names, sets/reps, kg targets,
the API's reason strings, the plan version, a build timestamp and the fixed gym days — no name,
weight, calories or anything from the encrypted dashboard payload. If parity is wanted, encrypt
only the `TARGETS` block with the existing PBKDF2/AES-GCM helper and cache the derived key in
localStorage (one prompt per phone); ticks/kg logic is unaffected.

**Pre-merge review (7 Sep, `review-2026-09-07.md`):** M1 next-session now follows the schedule
(a skipped day is not carried forward — matches the week view); M2 Fitbod imports map onto
active session types (`resolve_session_type`); M3 `/fitness/<name>.html` alias so the LAN
dashboard links work; m1 bad `schedule_from` ignored; m2 malformed `schedule` → rotation
fallback; m3 hard modality must be in `modalities`; m4 patching a retired session never
re-enters the rotation; m5 callers pass UK-time `today`; m8 short `duration_range_min` guarded;
n1 API strings escaped before innerHTML. Open follow-ups: m7 (dashboard build makes four extra
`next_session_bundle` calls), n6 (ticks keyed on calendar day, a session across midnight loses
them), n7 ("never two uppers back to back" is text only), n8 (Garmin hard-cardio inference).

## Documentation updates (required by project plan rules)

- **API docs**: `hadley_api/README.md` Fitness section — new endpoints + tables.
- **Peter's knowledge**: `domains/peterbot/wsl_config/CLAUDE.md` already points at
  `FITNESS.md`; `FITNESS.md` gets the plan-driven training section.
- **Skills/playbooks**: `log-workout` rewrite, `log-cardio`, `training-plan` new.
