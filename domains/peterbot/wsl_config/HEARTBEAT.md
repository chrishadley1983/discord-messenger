# Heartbeat

Checked on the heartbeat schedule. Peter processes health checks first, then works on one to-do item. If all clear and nothing to say: `NO_REPLY`.

Historical "Done" items live in `HEARTBEAT_ARCHIVE.md` — grep there when you need to recall what was fixed when.

---

## Critical Facts (Do NOT Forget)

**Chris's email address: chrishadley1983@gmail.com** — NEVER use chris@hadley.dev. Always verify before sending; always include the address when confirming delivery.

**G:\\ paths = Google Drive** — `G:\My Drive\...` is Chris's Google Drive on Windows (synced via Google Drive for Desktop). Not directly accessible from WSL.

---

## Health Checks

- [ ] Session responsive
- [ ] Last scheduled job succeeded (check scheduler status)

If all pass and no to-do action needed: `NO_REPLY`.

---

## To-Do List

Peter: Pick ONE item, action it, then mark done or update status. Chris can add items here for Peter to work on in the background.

### Pending

(Nothing pending)

### In Progress

(Nothing in progress)

### Monitoring

(Nothing being monitored)

### Awaiting Chris

- [ ] [ACTION] Log into Reddit in the new Chrome-SeedImport profile (one-time). The seed-import Chrome was moved off port 9222 (Chrome-Vinted, saturated by review-queue-processor) onto port 9223 with a fresh `Chrome-SeedImport` profile, so `incremental_seed` no longer collides with the busy Vinted browser. Verified: Playwright connects to 9223 in ~1s vs 180s timeout on 9222. The new profile has no Reddit session cookies yet, so the `reddit-saved` adapter will fail validation until Chris logs in once. Run this in PowerShell, sign into reddit.com, then close the window:
  ```
  & "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9223 --user-data-dir="$env:LOCALAPPDATA\Google\Chrome-SeedImport"
  ```
  Cookies persist in the profile dir; the next 1am seed run will pick them up automatically.

- [ ] [PROACTIVE] eBay dalt_785 cancellation AUTO-DECLINED — Deadline passed 6 Apr while Chris was in Japan. eBay auto-declined the buyer's cancellation request. Order 07-14458-28149 (Hero Factory Jet Rocka 44014, £67.99) still appears on pick list. Chris needs to decide: dispatch the item or contact buyer to arrange manual cancellation/refund.

- [ ] [PROACTIVE] eBay purchase payment due Sat 9 May — LEGO Heroica Caverns of Nathuz 3859 (£13.99 + £1.01 Buyer Protection). Seller may cancel if unpaid.

- [ ] [PROACTIVE] eBay case #5376785137 — DEADLINE PASSED 7 APR. Chris was in Japan and couldn't respond in time. Research done: item confirmed dispatched from GSP centre 6 Mar (eBay email proof). GSP seller protection applies — Chris not liable for international leg. Draft response posted to #peterbot. Chris should check case status when back — eBay may have auto-resolved or escalated.

### Done

Recent items archived to `HEARTBEAT_ARCHIVE.md`. Last cleanup: 2026-04-23.

---

## Instructions for Peter

1. **Each heartbeat:**
   - Run health checks silently
   - If any fail → post alert to #peterbot
   - If all pass → check to-do list

2. **To-do processing:** pick first pending item → move to "In Progress" → work → move to "Done" with today's date in archive → post brief summary to #peterbot.

3. **NO_REPLY when:** all health checks pass AND no to-do to process AND nothing noteworthy.

4. **Editing this file:** freely add/remove/modify to-do items. When marking "Done", append to `HEARTBEAT_ARCHIVE.md` rather than leaving here.
