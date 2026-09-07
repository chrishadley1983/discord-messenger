# Task plan — Reset Cut training log (Phase 1)

Status legend: [ ] todo · [~] in progress · [x] done + verified

- [x] F1 migration (both repos) + db push
- [x] F2 training_plan.py + tests
- [x] F3 service + routes + /today plan-aware + dashboard call site
- [x] F4 advisor snapshot + rules + tests
- [x] F5 programme row + accountability goals + auto_source
- [x] F6 skills + manifest
- [x] F7 docs + Second Brain note
- [x] F8 backfill + restart + live verify

- [x] P1 migration (garmin_activities + provenance) pushed
- [x] P2 Garmin sync/link/auto-create + endpoints + morning hook (live: 2 Aug hikes synced)
- [x] P3 Fitbod parser + import endpoint + CSV attachments + skill
- [x] P4 dashboard Training tab (deployed 20:00)
- [x] P5 weekly review + weekly-health training block + skills

## Schedule revision — 7 Sep 2026 (standing week, plan v6)
- [x] R1 `training_plan.py`: DEFAULT_PLAN = standing week (schedule, schedule_from, upper_a/lower_a/upper_b/full_body, retired upper/upper_db, hard modality = example, plan_week gating); scheduled week view; per-session duration/page
- [x] R2 `fitness_routes.py` cardio shortcuts for any hard modality; dashboard/advisor copy
- [x] R3 tests rewritten for the standing week (legacy rotation mechanics kept under `_legacy_plan()`)
- [x] R4 docs: FITNESS.md, README, spec (schedule + Phase 3 session-page requirements), skills
- [x] R5 live (7 Sep 20:xx): hadley_api restarted, plan v6 saved, programme row 3→4 strength/wk, goals "4 strength sessions" + "2 cardio sessions (1 hard + 1 easy)", Second Brain note 0c7291bb, next-session = upper_a (flat DB 12→14, incline hold 10, shoulder hold 25, flye 6→8, curl hold 8), dashboard refresh kicked
- [x] Phase 3 (S1–S4, S6 in spec.md): `domains/fitness/session_pages/` (4 pages + runtime.js + build), targets baked at dashboard build, surge + LAN route, Training-tab links, `test_session_pages` (13) + Playwright behaviour check (20/20) — S5 (stairmaster page) not in repo
- [ ] Follow-up: save `stairmaster-pyramid.html` into `session_pages/pages/` (timer-only reset, leave as is); page → `POST /fitness/workout` on Done

## Errors / lessons
(append as encountered — never retry the same failed approach)

- 5 Sep: Bash-tool heredocs fail on apostrophes in the body -> write scripts to scratchpad and run them.
- 5 Sep: Supabase MCP needs interactive OAuth; used HB repo supabase CLI (`db push --include-all --yes`) instead.
- 5 Sep: tests/accountability has 5 PRE-EXISTING failures (stale registry test expects agg in latest/sum_today; recent_progress shape; live ReadTimeout) - not from this change.
- 5 Sep (P2): a 60-day sync auto-created a cardio row for a 15 Aug hike -> guard: only activities on/after plan.started are auto-created; stray row deleted.
