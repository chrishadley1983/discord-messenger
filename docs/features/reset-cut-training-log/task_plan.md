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

## Errors / lessons
(append as encountered — never retry the same failed approach)

- 5 Sep: Bash-tool heredocs fail on apostrophes in the body -> write scripts to scratchpad and run them.
- 5 Sep: Supabase MCP needs interactive OAuth; used HB repo supabase CLI (`db push --include-all --yes`) instead.
- 5 Sep: tests/accountability has 5 PRE-EXISTING failures (stale registry test expects agg in latest/sum_today; recent_progress shape; live ReadTimeout) - not from this change.
- 5 Sep (P2): a 60-day sync auto-created a cardio row for a 15 Aug hike -> guard: only activities on/after plan.started are auto-created; stray row deleted.
