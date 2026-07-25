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

- [ ] [FIX] `empty response` job failures are **REAL, not a logging artefact** — I got this wrong first time and corrected it 22 Jul 08:01. Original guess was that skills returning `NO_REPLY` were being miscounted. **Wrong:** `scheduler.py:887-901` explicitly records `NO_REPLY` as `success=True`. `empty response` (scheduler.py:963-976) only fires when the channel returns literally zero bytes, after an automatic retry, and it triggers a reactive channel restart. Evidence from `peter_dashboard/job_history.db` (`job_executions`): every such row has `length(output)=0` and durations cluster in two bands — **~6m40s** (≈400,000ms: commitment-nudge, morning-laughs, pl-results, kids-weekly) and **~22min** (≈1,320,000ms: heartbeat, balance-monitor, security-monitor, morning-quality-report). ~20 occurrences since 23 Jun, running about 2/day this week, hitting a different skill each time — so it's the channel/session, not any one skill. Cost angle: each occurrence burns 6-22 minutes of LLM time and produces nothing, which feeds straight into the jobs-channel spend in the cost digest. Next step: correlate the timestamps against channel `session_start` values and the `force_restart_channel` calls in the scheduler log to confirm whether the wedged-channel heal is firing and whether it's the cause or the cure. NOTE: `morning-quality-report`'s skill file already carries an 'Empty-Response Guard' section written for this, which only helps for skills that legitimately have nothing to say — it does not address heartbeat, which must always output. **Correlation attempted 22 Jul 20:01 — BLOCKED, and the blocker is itself the finding.** The scheduler's reactive `force_restart_channel` path (scheduler.py:846-855) writes `restarting wedged '<channel>'` via `logger.warning`, but that string appears **nowhere** in `logs/` — `discord_bot.log` has zero matches and the rotated `discord_bot-*.log` files are all 0 bytes. So there is no way to tell whether the self-heal is firing, succeeding, or making things worse. Second gap: `job_logs` in `peter_dashboard/job_history.db` is inconsistent with `job_executions` — commitment-nudge (21 Jul) and morning-laughs (20 Jul) have a matching `Job failed: empty response` ERROR line, but heartbeat (21 Jul 12:01) and pl-results (20 Jul 06:05) have only `Job started` and no failure line at all, despite both being recorded as errors in `job_executions`. **Proposed fix (needs Chris — bot core):** (1) make the scheduler actually persist its warnings to a file that survives rotation, and (2) write a `job_logs` row on the empty-response branch so the two stores agree. Until then this can't be diagnosed further from the data available.

### In Progress

(Nothing in progress)

### Monitoring

- [ ] Amazon Fulfilment Centre tour — **Mon 10 Aug 2026, 10:00 BST, Amazon LCY3, Dartford DA1 5PZ**. Chris + Abby + Max + Emmie. Requirements extracted from the confirmation email 21 Jul (full brief saved to Second Brain, tag `amazon-tour`). Key points: arrive **09:45** (15 min early); **photo ID for every guest over 18** and names must match sign-up; closed-toe/closed-heel sturdy shoes (no Crocs/sandals/flip-flops/heels), long trousers, nothing loose or dangling, long hair tied at or above shoulder; **no bags of any kind, no cameras, no food**; **all photography banned including phones**; clear plastic water bottles allowed; 1-2 km of walking plus at least one flight of stairs; **under-6s not permitted** and under-18s must be with a responsible adult holding government ID. Drive Tonbridge → LCY3 measured at **42 min / 41.1 km off-peak** — leave ~08:30 for a Monday-morning M25/Dartford run to land at 09:45. **Outstanding:** reminder not created — `/reminders` POST needs `user_id` and `channel_id` which Peter doesn't have; asked Chris 21 Jul. Also worth Chris confirming Max is 6+ (age gate) before the day.

### Awaiting Chris

- [ ] [OPTIONAL — bot core] Tidy up the school-holiday guard so it self-maintains. Done 24 Jul at skill-instruction level (see Done/archive), which needs the hardcoded Kent holiday table extended each year. Cleaner long-term fix: in `domains/peterbot/data_fetchers.py`, `get_school_data()` already holds authoritative `TERM_DATES_2025_26` — add an `is_school_holiday` flag (today not within any term range) and surface it in `get_school_run_data()` / `get_school_pickup_data()` return dicts, then the skills can key off that instead of a static list. Small change but it's bot core + needs a deploy, so leaving it for your say-so. Not urgent — the instruction-level guard covers the current summer holiday now.

- [x] ✅ [RESOLVED 25 Jul] **finance schema was readable with the public anon key — FIXED and verified.** Applied as two migrations: `revoke_anon_access_to_finance_schema` and `revoke_anon_execute_on_finance_manual_income`. Approach differs from the SQL drafted below: rather than rewriting policies on 3 tables, it revoked anon's table privileges across the whole schema, which closes all of them at once. Also revoked anon from `pg_default_acl` (it was `{anon=r/postgres}`, so **every new finance table was auto-granted SELECT to anon** — the hole would have reopened itself), and enabled RLS on the backup table. **Scope was much wider than first reported: 25 tables carried `ALL TO public USING (true)`, not 3** — including `budgets` (2,148 rows), `categories`, `import_sessions`, `subscriptions`, `planning_notes`, `ai_usage_tracking`. Note three policies are *named* as though service-role-only ("Service role full access on subscriptions", "Allow full access via service key") but were actually `TO public`. **Two corrections to the original finding:** (1) writes were already blocked — anon held SELECT only, so DELETE/PATCH returned 401; this was a confidentiality leak, not an integrity risk. (2) `truelayer_connections` / `enable_banking_sessions` / `monthly_reports` were confirmed safe (RLS on, zero policies, 0 rows via anon) — no bank credentials were ever exposed. Separately found and closed an RPC bypass: `finance.add_monthly_manual_income()` was SECURITY DEFINER with a NULL proacl, so anon could POST to it and write a transaction regardless of table grants (date-gated + idempotent, so low impact); its real caller is pg_cron job 7 as `postgres`, unaffected. **Verified after applying:** anon → 401 on all 12 tables tested and on the RPC; service_role reads unchanged (transactions still 3,683); financial-data MCP `get_net_worth` returns full data end-to-end. Remaining follow-ups: the 25 always-true policies still grant `authenticated` full access (latent, not active — finance-tracker queries via service_role and uses anon only for signIn/signOut), and 82 `rls_policy_always_true` warnings remain project-wide, so the HB inventory tables need the same review.

- [ ] ~~🔴 [APPROVAL — SECURITY]~~ (superseded by the resolved entry above; original text kept for the record) **finance schema on the HB Supabase is world-readable via the public anon key.** Found 21 Jul 22:00 by security-monitor, triggered by a Supabase advisor email. Verified live with read-only requests using only the anon key (public by design, and embedded in plaintext in Peterbot's own skill files): `finance.transactions` 200/**3,683 rows**, `finance.wealth_snapshots` 200/**813 rows back to 2019**, `finance.accounts` 200/14 rows, `finance._backup_global_money_tx_20260701` 200/34 rows. Real HSBC descriptions, amounts, dates, account names, net-worth history — no auth required. **Two faults, and Supabase's email only mentioned the smaller one:** (1) the backup table never had RLS enabled (linter ERROR); (2) `transactions`/`accounts`/`wealth_snapshots` have RLS on but a `FOR ALL TO public USING (true)` policy granting anon full SELECT/INSERT/UPDATE/DELETE — functionally worse, but only rated WARN so it wasn't in the email. Writes were NOT tested, only reads. Fix written at `generated/fix_finance_rls.sql` (enables RLS, replaces the three always-true policies with authenticated-only, revokes the anon grant, includes verify curls + rollback). **NOT APPLIED — needs Chris's approval, it's the live business DB.** `service_role` bypasses RLS so Hadley API / financial-data MCP are unaffected; anything reading finance via the ANON key will break by design — check the finance dashboard frontend authenticates as a real user first. Follow-up: 82 `rls_policy_always_true` warnings project-wide, so the HB inventory tables need the same review.

- [ ] [DECISION] 11+ Mate automation writes are DE-SCHEDULED by design (not a bug). Investigated 14 Jul via Supabase MCP: `practice-schedule-manage` (v13) now hard-rejects the service key — its `authenticate()` has an explicit guard: "Automated schedule-content generation (Second Brain / Peterbot tutor email parser) is DE-SCHEDULED as of Jul 2026: external automation may no longer write tutor topics or schedule slots. A formal schedule-agreement flow will replace it. Parent sessions only." So `tutor-email-parser`, `paper-builder` and `practice-allocate` can no longer write via `psk_11plusmate_tutor_2026` — this is intentional, not something to bypass. **Needs Chris's decision:** (a) retire/disable these 3 Peterbot schedules, (b) rework them to use a parent session_token if the new "schedule-agreement flow" exposes one, or (c) leave them logging to Second Brain only (topic still gets captured; allocation happens in-app). Do NOT attempt a workaround around the security control. **Update 21 Jul: all three jobs fired and all three failed tonight** — tutor-email-parser 19:06 (write skipped, parse still saved to Second Brain), paper-builder 19:30 (`401 Unauthorized`), practice-allocate 21:00 (14/14 calls `HTTP 400: Missing session_token or service key`). Term 6 ended 20 Jul; Year 5 Term 1 starts **Mon 7 Sep 4-5pm**, so option (a)/pausing until September now has a natural window — 7 more Tuesdays of noise otherwise. Note option (c) already works in practice: the tutor parse saved cleanly to Second Brain tonight without touching the endpoint.

- [ ] [ACTION] Log into Reddit in the new Chrome-SeedImport profile (one-time). The seed-import Chrome was moved off port 9222 (Chrome-Vinted, saturated by review-queue-processor) onto port 9223 with a fresh `Chrome-SeedImport` profile, so `incremental_seed` no longer collides with the busy Vinted browser. Verified: Playwright connects to 9223 in ~1s vs 180s timeout on 9222. The new profile has no Reddit session cookies yet, so the `reddit-saved` adapter will fail validation until Chris logs in once. Run this in PowerShell, sign into reddit.com, then close the window:
  ```
  & "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9223 --user-data-dir="$env:LOCALAPPDATA\Google\Chrome-SeedImport"
  ```
  Cookies persist in the profile dir; the next 1am seed run will pick them up automatically.

- [ ] [PROACTIVE] eBay dalt_785 cancellation AUTO-DECLINED — Deadline passed 6 Apr while Chris was in Japan. eBay auto-declined the buyer's cancellation request. Order 07-14458-28149 (Hero Factory Jet Rocka 44014, £67.99) still appears on pick list. Chris needs to decide: dispatch the item or contact buyer to arrange manual cancellation/refund.

- [ ] [PROACTIVE] eBay purchase payment due Sat 9 May — LEGO Heroica Caverns of Nathuz 3859 (£13.99 + £1.01 Buyer Protection). Seller may cancel if unpaid.

- [ ] [PROACTIVE] eBay case #5376785137 — DEADLINE PASSED 7 APR. Chris was in Japan and couldn't respond in time. Research done: item confirmed dispatched from GSP centre 6 Mar (eBay email proof). GSP seller protection applies — Chris not liable for international leg. Draft response posted to #peterbot. Chris should check case status when back — eBay may have auto-resolved or escalated.

- [ ] [ACTION] eBay buyer rys1_49 (Peter) messaged about LEGO Mindstorms 9719 (#178127891993) — requesting a photo of the RCX Brick. Buyer waiting for response. Chris needs to photograph the brick and reply via eBay messages.

- [ ] [PROACTIVE] eBay unpaid purchases (4 Jun) — Two items need payment:
  1. LEGO 40760 Fortnite Brickheadz Adventure Peely & Cuddle Team Leader — £10.80 (hadleybricks account)
  2. LEGO Fortnite Peely Sparkplug's Camp Wolf Supply Llama 77075 — £4.21
  Sellers may cancel if unpaid. Total: £15.01.

- [ ] [ACTION] eBay stock sync failing — reconnect eBay account. `hb_ebay_stock_sync` failed 2 of 3 runs in the last 24h with `eBay not connected` (userId 4b6e94b4… → "eBay not connected", 0 listings synced). The eBay OAuth token has dropped. Chris needs to reconnect the eBay account in the HB inventory dashboard (Settings → Connections → eBay) so stock sync resumes. First seen: 2026-07-01.

- [ ] [REOPENED 2026-07-22 22:01] HB amazon-pricing — **I marked this resolved too early. It failed again at 20:02 UTC**, same RPC statement timeout, 8.19s. Record since the fix: **8 successes then 1 failure** (vs 0/5 before), so the fix is genuinely working — it just hasn't bought enough headroom. Re-measured at 22:00: **2,978 ms warm**, and the reason it's still marginal is now clear. The candidate set grows through the day as snapshots age past `CURRENT_DATE` — 2,829 rows at 00:01, **6,619 rows at 22:00** — so the query gets steadily heavier and the late-evening runs are the ones that tip over 8s. Compounding it, `Heap Fetches` is now **7,043** (up from 6,824) because the visibility map is still stale: **no manual VACUUM has been run, last autovacuum was 17 Jul**, and `n_mod_since_analyze` is 21,118. Those heap fetches are ~30,000 of the query's 67,000 buffers. **`VACUUM public.amazon_arbitrage_pricing;` is now clearly the missing piece** — it takes no exclusive lock and changes no data. Still not run without your say-so. Original fix retained at `generated/fix_get_keepa_priority_asins.sql`. Verified 22 Jul 00:01: the live function now contains both `MATERIALIZED` and `LATERAL`, and the optional `idx_bl_pg_cache_set_fresh` index was created too. Runs since: 17:02 UTC ok (3m27s), 20:02 UTC ok (**34s** — back to the pre-13-Jul baseline). Backstory: not the 2 Jul issue; clean 8/8 daily 1–17 Jul, failures began 18 Jul after a ~4,300-row BL price-guide backfill on 13–15 Jul enlarged the intl-set-arb arm. Root cause was the `last_snapshot` correlated subquery in a non-materialised CTE expanding into six SubPlans. **CAVEAT — my '156 ms / 28x' headline was overstated.** Re-measured post-fix at 00:01 it runs **3,436 ms**, not 156 ms. The 156 ms reading was taken seconds after the baseline run with everything hot; since then the 17:02/20:02 pricing runs wrote ~1,000 rows into `amazon_arbitrage_pricing` and the visibility map went stale, so the index-only scan now does **6,824 heap fetches**. Last autovacuum was 17 Jul. The fix is still a genuine and necessary win, but 3.4s is uncomfortably close to the 8s ceiling. **Suggested follow-up: `VACUUM public.amazon_arbitrage_pricing;`** to restore the visibility map and real index-only scans — plain VACUUM takes no exclusive lock and changes no data. Not run — Chris's call. SQL kept at `generated/fix_get_keepa_priority_asins.sql`.

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
