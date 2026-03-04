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

### Awaiting Chris

- [ ] [FIX] Claude API balance check broken — Session expired, needs `anthropic_auth.py` re-run. Noticed in 07:03 balance check: "Session expired - run anthropic_auth.py". **Peter cannot action** — requires Chris to run the auth script on his machine.

### Done

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
