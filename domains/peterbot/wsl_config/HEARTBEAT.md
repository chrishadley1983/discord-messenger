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

- [ ] [VERIFY] Post-audit check — tomorrow morning (2026-04-21) after 08:00 UK, verify yesterday's audit fixes landed correctly. Check:
  1. **spapi-buybox-overlay** in `job_execution_history` for 2026-04-21: expect ~46 rows all `status=completed` with progressive `items_processed` (was: 1 stuck "timeout" row with items_processed=0). Query via `SERVICE_API_KEY` in `apps/web/.env.local`: `curl -s "http://localhost:3000/api/service/jobs/history?limit=50&job_name=spapi-buybox-overlay" -H "x-api-key: $KEY"`.
  2. **investment-sync** same query (`job_name=investment-sync`): expect `result_summary.asin_linkage.errors: 0`, `newly_linked > 0` (was: 7087 errors, 0 newly_linked).
  3. **inventory-bricklink-enrich** same query: expect 1+ rows to exist for today (was: NO rows ever recorded — instrumentation added).
  4. **ebay-promotions** same query: expect errors count to be low/zero (was: masking silent failures while eBay auth was broken).
  5. **HadleyAPI nightly hang** — check `C:\Users\Chris Hadley\claude-projects\discord-messenger\logs\watchdog.log` for any `2026-04-21 01:0` WARNING/RESTART entries. Expectation: ZERO (was: 7 consecutive nights of hangs 6-12 Apr).
  6. **incremental_seed** — check `~/AppData/Local/discord-assistant/logs/2026-04-21.log` for the 01:00 run; expect "0 adapters failed" and no "Cannot reach Gmail API" errors.
  7. **BigQuery spend tracking** — `curl http://localhost:8100/jobs/health` should show `source: bigquery` (was: `estimates` due to scope bug; fixed by changing scope from `bigquery.readonly` to `bigquery` in gcp_monitoring.py + GCP IAM grant).

  Post findings to #alerts. If anything is off, move the failing item to "Awaiting Chris" with details.

### In Progress

(Nothing in progress)

### Monitoring

- [ ] [FIX] Recurring channel crashes — ROOT CAUSE IDENTIFIED 2026-04-20: WSL cycling every ~30 min (5 reboots 04:31–06:09) killed tmux channel sessions; bot.py only launched channels once on `on_ready`, so they never recovered. Fix applied to `bot.py`: added `channel_watchdog` APScheduler job running `_launch_channel_sessions()` every 1 minute (idempotent — `tmux has-session` check). Requires `nssm restart DiscordBot` to activate. All 3 channels manually restarted and verified healthy at 06:29. Monitor for 24h — if still recurring, check WSL idle timeout (add `.wslconfig` with `vmIdleTimeout=-1`).

### Awaiting Chris

- [ ] [PROACTIVE] eBay dalt_785 cancellation AUTO-DECLINED — Deadline passed 6 Apr while Chris was in Japan. eBay auto-declined the buyer's cancellation request. Order 07-14458-28149 (Hero Factory Jet Rocka 44014, £67.99) still appears on pick list. Chris needs to decide: dispatch the item or contact buyer to arrange manual cancellation/refund.

- [ ] [PROACTIVE] eBay case #5376785137 — DEADLINE PASSED 7 APR. Chris was in Japan and couldn't respond in time. Research done: item confirmed dispatched from GSP centre 6 Mar (eBay email proof). GSP seller protection applies — Chris not liable for international leg. Draft response posted to #peterbot. Chris should check case status when back — eBay may have auto-resolved or escalated.

_(school_daily_sync, school_weekly_sync, Claude API balance check, 11+ Mate, and eBay API token items resolved 2026-04-20 during post-holiday audit — moved to Done below.)_

### Done

- [x] [FIX] Post-holiday P0/P1 audit — Completed 2026-04-20. Full health sweep across Discord-Messenger + Hadley Bricks + GCP + Vercel + third-party auth. Resolved: eBay token reconnect; Vercel deploy freeze (false alarm — Vercel in sync with main); Vercel usage scraper re-login + DOM selector fix; spapi-buybox-overlay state-machine bug (PR #336 merged); WSL Watchdog 3 stacked bugs (UTF-8 BOM + array -notmatch + quote tangle); 11+ Mate practice-schedule-manage 401 (+ tutor-email-parser + practice-allocate) via `ALTER ROLE authenticator SET pgrst.db_schemas`; incremental_seed Gmail via converting 19 `async def` → `def` for Hadley API /gmail/* handlers; Withings token reauth; investment-sync UPSERT→UPDATE bug (PR #337 merged); inventory-bricklink-enrich instrumentation added (PR #338 merged); google-cloud-bigquery installed into NSSM's Python 3.14.
- [x] [FIX] school_daily_sync recovered — Confirmed 2026-04-20 07:03 run: Gmail Parser OK, Arbor Scraper OK, Arbor Monitor OK. Was transient; self-resolved since 28 Mar.
- [x] [FIX] school_weekly_sync pymupdf — pymupdf 1.27.2.2 installed in Python 3.14; 0 failures in last 30 days.
- [x] [FIX] Claude API balance check — Console-scraper path working (anthropic_session.json refreshed 06:06 daily). OAuth 302 issue self-resolved; token currently valid.
- [x] [FIX] 11+ Mate Edge Functions — Fixed 2026-04-20. Root cause: `practice` schema not exposed in PostgREST despite UI showing it. Fix: `ALTER ROLE authenticator SET pgrst.db_schemas TO '... practice'` + `NOTIFY pgrst, 'reload config' + 'reload schema'`. Verified: get-tutor-topics returns 4 weeks of Emmie's tutor topics.
- [x] [FIX] eBay API token expired — Chris reconnected 2026-04-20. Verified via dry-run of ebay-listing-refresh: 5 eligible listings returned with real prices/ageDays/tier. Next 19:00 UK scheduled run will execute for real.
- [x] [PROACTIVE] eBay steptoe_and_hun_uk INR follow-up — Completed 2026-04-16. Self-resolved by Chris. Listing #177977239027 (Tipper Truck 6527, sold 7 Apr, order 25-14450-81119 to Stuart Reed, Stirchley B30 3BL). Buyer asked for tracking 15 Apr, Chris explained holiday mode and offered cancellation, buyer replied 21:22 UK: "No worries, in no rush. Enjoy your holiday 🙂". eBay dispatch deadline extended to 20 Apr (holiday-mode accommodated). Chris home 19 Apr → can dispatch Sun/Mon in time. No buyer action needed; just add to pick list on return.

- [x] [PROACTIVE] Tokyo arrival prep (14 Apr) — Completed 2026-04-13. Compiled Kyoto→Tokyo Shinkansen options (Nozomi every 10min, ~2h15m, ¥14,170/adult), Tokyo Station→Nezu transit (Chiyoda Line, 3 stops, 15-20min), local area guide (restaurants, konbini, supermarkets), and first-evening suggestions (Nezu Shrine azalea festival at peak bloom + Yanaka Ginza street food). Posted to #peterbot.
- [x] [PROACTIVE] eBay return 5316537953 COMPLETE — Completed 2026-04-12. Return delivered and refund of £30.48 issued to buyer lovefactorystore on 11 Apr (order 11-14437-26021, Timberland boot). eBay confirmed "This return is complete". No further action needed.
- [x] [PROACTIVE] LEGO reseller policy changes — deep-dive — Completed 2026-04-11. Researched LEGO Insiders T&C update effective 31-Mar-2026. Targets BrickLink "professional sellers" (legal entities) — blocks Insiders point earning/redeeming. Hadley Bricks direct exposure = low (primary sourcing is retail/Amazon/eBay, not BrickLink). Flagged risks: any BrickLink seller account linked to LEGO ID, and possible future broadening of enforcement. Posted to #peterbot.
- [x] [PROACTIVE] LEGO 2026 retirement × Hadley Bricks inventory cross-reference — Completed 2026-04-11. Queried brickset_sets (121 sets retiring 31-Jul-2026) × inventory_items. Found 10 lines we already stock (22-set 501st Battle Pack is the big one), 8 proven-seller restock candidates, and 6 gap opportunities led by 21350 Jaws (+41%) and 77092 Deku Tree (+29%). Posted to #peterbot.
- [x] [PROACTIVE] eBay return tracking (lovefactorystore) — Completed 2026-04-07. Return 5316537953 auto-approved 6 Apr. Buyer asked to send back Timberland boot (order 11-14437-26021). Status: awaiting buyer dispatch — no tracking yet. Chris must refund within 2 days of delivery. No action needed until item arrives back.
- [x] [PROACTIVE] Kyoto itinerary prep (10-14 Apr) — Completed 2026-04-05. Compiled 4-night day-by-day plan for Shimogyō-ku base: Fri arrival (Gion/Pontocho), Sat Arashiyama, Sun southern Higashiyama (Fushimi Inari early + Kiyomizu-dera), Mon northern (Kinkaku-ji/Ryoan-ji/Nijo), Tue Nishiki Market before check-out. Kid-friendly pacing + dinner picks near Airbnb. Posted to #peterbot.
- [x] [PROACTIVE] Osaka Aquarium Kaiyukan visit prep — Completed 2026-04-05. Compiled transit (Shinsaibashi → Honmachi → Osakako, ~20 min, ¥240), Tempozan Harbour Village nearby spots (Legoland Discovery, Ferris wheel, Marketplace food court), and visit tips (start top floor, whale sharks, 2-2.5 hrs). Posted to #peterbot.
- [x] [PROACTIVE] LEGO July 2026 retirement hunt list — Completed 2026-04-05. Compiled top resale targets across Icons, Star Wars, Technic, Harry Potter. 130+ sets retiring 31 Jul 2026 per Stonewars. Posted to #peterbot.
- [x] [PROACTIVE] Osaka arrival prep — Completed 2026-04-05. Compiled Shinkansen details (Tokyo 10:09 → Shin-Osaka 12:36, Nozomi 355, Car 8, Green), Airbnb check-in (16:00 Mon 6 Apr at 505 Shinsaibashi, hosts Yoko & Nobu), dinner picks near Dotonbori, and must-do list. Posted to #peterbot.
- [x] [PROACTIVE] eBay cancellation research (dalt_785) — Completed 2026-04-04. Order 07-14458-28149 (Hero Factory Jet Rocka 44014, £67.99+£3.75 postage). Buyer requested cancellation 8 mins after purchase, item not dispatched. Recommendation posted: approve cancellation. Moved to Awaiting Chris.
- [x] [PROACTIVE] Q1 2026 Hadley Bricks business review — Completed 2026-03-31. Pulled P&L and platform revenue for Jan-Mar 2026. Gross revenue £22,202 (Amazon £18,006 / eBay £4,195), net revenue £17,489 after fees/refunds. Amazon dominates at 82%. Costs data appears to be in pence — flagged for Chris. Posted to #peterbot.
- [x] [PROACTIVE] LEGO retail sale stock opportunities — Completed 2026-03-30. Researched current UK LEGO sales across major retailers. Key findings: Amazon Big Spring Sale (ends 31 Mar), LEGO.com spring sale 20-40% off 70+ sets (until 5 Apr), Very up to 70% off LEGO clearance, Bargain Max clearance live, Smyths clearance on discontinued lines. Top resale picks: retiring sets on discount (Icons, Technic F1, Star Wars). Posted to #peterbot.
- [x] [PROACTIVE] Japan final countdown check — Completed 2026-03-30. Verified host communications active (all 4 hosts messaged 25-26 Mar), Kyoto paid (26 Mar), key bookings confirmed. Flagged 3 action items due before departure. Posted to #peterbot.
- [x] [PROACTIVE] Vercel Hobby plan approaching limits — Completed 2026-03-30. Analysed usage trend across 3 billing cycles. Two critical metrics: Deployments at 183/day (limit 100) driven by frequent PR merges, and Function Duration at 76.7% (up from 22.8% in 12 days) driven by sync/enrichment API routes. Recommendations posted to #peterbot.
- [x] [PROACTIVE] Japan trip pre-departure checklist — Completed 2026-03-27. Reviewed full itinerary, all bookings, and compiled 7-day-out action list. 2 pending restaurant bookings flagged, 3 host check-in forms needed. Posted to #peterbot.
- [x] [PROACTIVE] Research LEGO Creator 3-in-1 sets retiring July 2026 — Completed 2026-03-27. Compiled full list of 9 Creator 3-in-1 sets retiring 31 Jul 2026 with RRP, market data, and sourcing recommendations. Posted to #peterbot.
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
