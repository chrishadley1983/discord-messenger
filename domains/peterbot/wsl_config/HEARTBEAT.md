# Heartbeat

This file is checked every 30 minutes. Peter processes health checks first, then works on one to-do item.

---

## Critical Facts (Do NOT Forget)

**Chris's email address: chrishadley1983@gmail.com**
- NEVER use chris@hadley.dev (I made that up and it was wrong)
- Always verify email before sending
- Always include the email address when confirming delivery to Chris

**G: drive = Google Drive**
- G:\ paths point to Chris's Google Drive (synced via Google Drive for Desktop on Windows)
- Example: `G:\My Drive\AI Work\Screenshots\` is a valid Google Drive location
- These paths are accessible from Windows, not WSL directly

---

## Health Checks

Run these checks and alert #peterbot if any fail:

- [ ] Session responsive (can execute commands)
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

### Awaiting Chris

- [ ] [FIX] school_weekly_sync failing — pymupdf missing. Error: `ModuleNotFoundError: No module named 'fitz'`. Need to add `pymupdf` to Discord-Messenger/requirements.txt and run `pip install pymupdf`. Peter confirmed: scripts are in hadley-bricks repo at `scripts/school/`, but they run via bot.py using sys.executable, so the package must be in the bot's Python environment.
- [ ] [FIX] Claude API balance check broken — Session expired, needs `anthropic_auth.py` re-run. Noticed in 07:03 balance check: "Session expired - run anthropic_auth.py". **Peter cannot action** — requires Chris to run the auth script on his machine.

### Done

- [x] [PROACTIVE] Add parents evening slots to calendar — Completed 2026-03-19. Extracted from Gmail booking confirmations (13 Mar). Added two events to Google Calendar for 1 Apr 2026: 17:20 Emily Scott & Clair Thornton, 17:30 Chloe Adams & Coralie Tringham. Reminders set for 1 day and 1 hour before.
- [x] [PROACTIVE] Verify flat white recipe — Completed 2026-03-16. Confirmed flat white recipe EXISTS in nutrition favourites: "90ml semi-skimmed milk, 50ml espresso" (44 cal, 3.2g protein). Also correctly embedded in "usual breakfast" favourite. Not in Second Brain separately, but not needed there — nutrition system has it.
- [x] [SKILL] Recipe skill: add save-by-position handling — Completed 2026-03-15. Updated `recipe-discovery` and `daily-recipes` skills with explicit "save N" position-based save instructions. Skills now document how to match numbers to recipe positions and save by URL.
- [x] [FIX] school_weekly_sync location clarified — Resolved 2026-03-14. Scripts live in hadley-bricks repo at `scripts/school/`, NOT peterbot. Job is registered in `bot.py` via APScheduler (not SCHEDULE.md). CLAUDE.md updated with infrastructure jobs section.
- [x] [PROACTIVE] Research GCP BigQuery cost optimization — Completed 2026-03-13. Found root cause: free tier is 1 TB queries + 10 GB storage/month. Costs likely from SELECT * queries, unpartitioned tables, or query volume exceeding 1 TB. Recommendations posted to #peterbot.
- [x] [PROACTIVE] Create "usual breakfast" nutrition preset — Already exists! Verified 2026-03-09. Favourite found with full macros: 410 cal, 16.3g P, 42.5g C, 16.5g F.
- [x] [FIX] whatsapp-health job failing — Fixed 2026-03-06. Renamed skill from `whatsapp-health` to `whatsapp-keepalive` to match folder name. Updated SCHEDULE.md accordingly.

_Japan guides cleared 2026-03-03 — emailed guides were tangential to website work._

_Archived 28 items from Jan 31 – Feb 6 (2026-02-22 cleanup). See git history for details._

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
