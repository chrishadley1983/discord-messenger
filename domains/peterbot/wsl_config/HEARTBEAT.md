# Heartbeat

This file is checked every 30 minutes. Peter processes health checks first, then works on one to-do item.

---

## Health Checks

Run these checks and alert #peterbot if any fail:

- [ ] Session responsive (can execute commands)
- [ ] Memory endpoint OK (http://localhost:37777/health returns 200)
- [ ] Last scheduled job succeeded (check scheduler status)

If all checks pass and no to-do items need action: respond with `NO_REPLY`

---

## To-Do List

Peter: Pick ONE item, action it, then mark done or update status.
Chris can add items here for Peter to work on in the background.

### Pending

(Nothing pending)

### In Progress

(Nothing in progress)

### Done

- [x] [RESEARCH] Clawdbot/Openclaw use cases - Compiled 50 use cases across 9 categories (email, calendar, developer, files, research, finance, smart home, health, social media). Full doc at docs/OPENCLAW_USE_CASES_REPORT.md. Emailed to Chris. (2026-02-05)

- [x] [BUILD] Daily recipe recommendations skill - Created `skills/daily-recipes/SKILL.md` with full spec: searches Reddit, X, YouTube, web for 5 high-protein recipes matching nutrition targets. Shows macros, prep time, direct links. Added to manifest.json. **Needs Chris to add to SCHEDULE.md** for 06:30 daily runs. (2026-02-04)

- [x] [RESEARCH] Peterbot functionality improvements - Researched 10 improvements (5 practical: proactive briefings, family calendar, expense tracking, health coaching, second brain; 5 blue sky: voice interface, computer use, predictive optimization, multi-agent team, life documentation). Full doc at docs/PETERBOT_IMPROVEMENTS.md. Emailed to Chris. (2026-02-04)

- [x] [INTEGRATION] HB inventory write endpoint auth - RESOLVED via `POST /hb/batch-import`. This single endpoint creates BOTH purchase and inventory records in one call, bypassing the need for separate inventory POST. The `hb-add-purchase` skill now uses batch-import successfully. Direct inventory updates (storage location, platform changes) still need Chris to add `/hb/inventory-update` endpoint. (2026-02-04)

- [x] [INTEGRATION] Google Calendar write/update endpoint - RESOLVED. Chris added PUT endpoint with color and transparency params. Validated and updated all school entries: 8 holidays + 10 inset days set to Grape color and Free (transparent). Calendar dates were already correct after earlier validation. (2026-02-04)

- [x] [DESIGN] Flight tracker process - Created `docs/FLIGHT_TRACKER_SPEC.md` with full system design: Skyscanner API via RapidAPI (free tier), Supabase storage for watches + price history, 3-phase rollout (search → track → alerts), Google Flights filter parity, alert format. Ready for Chris to implement Phase 1 endpoints. (2026-02-03)

- [x] [INTEGRATION] Water delete endpoint - IMPLEMENTED by Chris. New endpoints: `GET /nutrition/water/entries` (list with IDs), `DELETE /nutrition/water?entry_id=<uuid>`. Negative workaround still works as fallback. (2026-02-03)
- [x] [RESEARCH] Japan advance booking guide - Created comprehensive `docs/JAPAN_ADVANCE_BOOKING_GUIDE.md` covering theme parks, museums, restaurants, cultural experiences, and transport across Tokyo/Osaka/Kyoto. Includes booking timeframes, difficulty ratings, tips, and platform recommendations. (2026-02-03)
- [x] [FEATURE] Reminders API spec - Created `docs/REMINDERS_API_SPEC.md` with POST/GET/DELETE endpoints, request/response formats, DB schema, time parsing guidance. Ready for Chris to implement in Hadley API. (2026-02-02)
- [x] [MONITOR] Memory worker queue - Worker healthy, uptime 2.7hrs since restart. 1,731 observations in DB, 13 active sessions. Backlog cleared. (2026-02-02)
- [x] [FIX] Food-log URL-encoded fragments leaking - Parser wasn't catching %XX percent encoding (like %20, %26). Added new patterns: `url_encoded` for %XX, `query_fragment` for &param=%encoded, `curl_url_fragment` for wrapped curl URLs. (2026-02-02)
- [x] [DOC] Nutrition goals PATCH parameters undocumented - Peter tried `protein_g_target` but correct param is `protein_target_g`. Added full parameter list to CLAUDE.md: calories_target, protein_target_g, carbs_target_g, fat_target_g, water_target_ml, steps_target, target_weight_kg, deadline, goal_reason. (2026-02-02)
- [x] [FIX] Screen capture extracting tool UI - Fixed regex to filter out tool call UI (● Bash, ⎿ JSON fragments). Weather responses now clean. (2026-02-02)

- [x] [FIX] Peterbot observations not being captured - Root cause: `capture_message_pair()` in memory.py was missing `project` field in payload. Added `"project": PROJECT_ID` to fix. Observations will now be tagged with "peterbot" project. (2026-02-02)
- [x] [IDEAS] Japan travel research - Best time: Spring (cherry blossoms, late March-early May) or Fall (Sept-Nov). Avoid Golden Week. JR Pass not automatic anymore - calculate per itinerary, regional passes often better value. Book 12 months ahead. Complete Visit Japan Web before arrival. New 2026: PokePark Kanto (Feb), Disney/Universal expansions. Tokyo needs 3-4 days. Avoid rush hour trains with kids. (2026-02-01)
- [x] [INTERVIEW] Structured 50-question interview with Chris - COMPLETE. Key profile: Dover origin, Reading uni, 20y Accenture, now Hadley Bricks in Tonbridge. Spurs fan, cricket lover. 88kg→77kg goal, evening snacker, struggles to switch off. Retire at 50 target. Japan trip planned. Wants me focused on: research, ideas, small time-saving tools. (2026-02-01)
- [x] [TODAY] Spurs vs Man City - Match ended 2-2. Solanke brace (53', 70' scorpion kick) cancelled out Cherki (11') and Semenyo (44'). Discussed with Chris during the match. (2026-02-01)
- [x] [SKILL] Spurs match-day automation - Created `skills/spurs-match/SKILL.md` for live score updates and updated morning-briefing to include Spurs fixture check on match days. Added to manifest.json. Note: Automated 15-min updates during matches would require SCHEDULE.md entry (ask Chris). (2026-02-01)

- [x] [INTEGRATION] Asked Chris about Gmail read endpoint for Hadley API (2026-02-01)
- [x] [QUESTION] Asked Chris about football_scores.py removal - awaiting response (2026-02-01)
- [x] [IDEAS] Trip-prep skill created - combines calendar lookup, directions, and EV status for trip readiness checks. SKILL.md written, added to manifest. Triggers: "trip prep", "am I ready for [place]", "trip to [place]" (2026-02-01)
- [x] [FIX] EV battery_level - Investigated. Ohme charger has no car API connection. API now returns `battery_level: null` with `battery_level_estimated` from extrapolation. The earlier 2.0 value was likely buggy data. Current response is correct - shows estimated 24% with clear "EXTRAPOLATION" source label. No Peterbot changes needed; Hadley API is handling it properly. (2026-02-01)
- [x] [MEMORY] Peterbot skills live in `skills/` folder, not `.claude/skills/` (2026-01-31)
- [x] Find Chris 5 good restaurants in Canterbury (2026-01-31)
- [x] [FIX] Synced 8 new skills to manifest.json: drive-search, email-search, email-summary, find-free-time, notion-ideas, notion-todos, schedule-today, schedule-week (2026-01-31)
- [x] [SKILL] keybindings-help - Not a Peterbot skill, it's a built-in Claude Code feature. No manifest entry needed. (2026-01-31)

---

## Instructions for Peter

1. **On each heartbeat (every 30m):**
   - Run health checks silently
   - If any fail → post alert to #peterbot
   - If all pass → check to-do list

2. **To-do processing:**
   - Pick the first pending item
   - Move it to "In Progress"
   - Work on it (search, create files, etc.)
   - When done, move to "Done" with today's date
   - Post brief summary to #peterbot

3. **NO_REPLY cases:**
   - All health checks pass AND
   - No to-do items to process AND
   - Nothing noteworthy to report

4. **Editing this file:**
   - You can freely add/remove/modify to-do items
   - Keep health checks as-is unless instructed otherwise
   - Update status by moving items between sections
