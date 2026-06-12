# Vercel Fluid CPU — Analysis & Migration Plan

**Date:** 12 Jun 2026 · **Status:** PLANNED (awaiting go) · **Owner:** Chris + Claude

## 1. Analysis — where last cycle's compute went

Cycle 13 May–12 Jun: **Fluid Active CPU 6h41m hadley-bricks + 35m football-predictor**
vs 4h free allowance (exhausted ~6 Jun → functions throttled → Resend daily
reports stopped). Per-project numbers scraped from the dashboard 12 Jun.

| Consumer | Est. share | Evidence |
|---|---|---|
| `ebay-stock-sync` Vercel cron (06:00 daily, maxDuration 300s) | ~35–40% | 300s-class function, daily; 2 crons ≈ 10 min/day wall time vs 13.4 min/day total burn |
| `bricqer-batch-sync` Vercel cron (06:30 daily, maxDuration 300s) | ~35–40% | as above |
| Peter skills `hb-add-inventory` + `hb-email-purchases` → `https://hadley-bricks-inventory-management.vercel.app` | ~10–20% | SKILL.md base URLs; scheduled + conversational use |
| keepa webhook + page/API traffic + weekly `scanner-image-cleanup` | remainder | 37K invocations/month total |
| football-predictor (all of it) | 35m24s | player traffic; NOT the problem |

**Non-findings (checked, innocent):** the daily 09:35 full-sync calls
`localhost:3000` (the vercel.app string at data_fetchers.py:2768 is only for
clickable pick-list links); football-predictor chat polls Supabase directly.

## 2. Proposed changes

### C1 — Repoint Peter's HB skills to the local production box (config-only)
`hb-add-inventory/SKILL.md` + `hb-email-purchases/SKILL.md`: base URL
`https://hadley-bricks-inventory-management.vercel.app` → Hadley API HB proxy
`http://172.19.64.1:8100/hb` (which injects the API key and forwards to
localhost:3000). Channel sessions pick the change up on restart.

### C2 — Move the 3 Vercel crons to local scheduling
1. Add an infra registration in DM `bot.py` (or extend `jobs/`) scheduling:
   - 06:00 daily → `POST http://localhost:3000/api/cron/ebay-stock-sync`
   - 06:30 daily → `POST http://localhost:3000/api/cron/bricqer-batch-sync`
   - Sun 03:00 → `POST http://localhost:3000/api/cron/scanner-image-cleanup`
   using the `verifyCronAuth` header (`CRON_SECRET` from HB apps/web/.env.local).
   Wrap with `_tracked_job` so failures alert #alerts.
2. Remove the `crons` block from HB `vercel.json` (same commit).
3. Routes themselves are UNCHANGED — same code, same DB, different invoker.

### C3 — Keep on Vercel (deliberately)
keepa webhook (external service needs a public URL), public pick-list pages,
football-predictor untouched, and the deployment itself as remote fallback.

**Projected effect:** HB Vercel CPU drops ~90% (to webhook + page traffic);
next-cycle Fluid CPU comfortably inside the free 4h. No plan upgrade needed.

## 3. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Local box down at 06:00/06:30 (yesterday's overnight reset!) → syncs missed | MED | `_tracked_job` failure → #alerts; APScheduler `coalesce` runs missed jobs on bot start; accept up-to-a-morning delay (same data re-syncs) |
| `CRON_SECRET` mismatch → silent 401s | MED | Test plan T2 verifies a real authenticated call before cutover; tracked-job alerts catch later drift |
| Double-execution during transition window (both Vercel + local cron live) | LOW | Sync routes are idempotent upserts; sequence: add local first, observe one clean day, then remove vercel.json crons |
| Local NSSM `next start` lacks env that Vercel had (API keys for eBay/Bricqer) | LOW | Same `.env.local` already serves the heavier full-sync locally; T3 confirms per-route |
| Peter skills break via proxy (route not in HB proxy allowlist w/ validateAuth) | MED | T4 exercises each skill endpoint through the proxy; add `validateAuth()` to any route that lacks it |
| 300s-route runtime on local hardware differs (timeouts) | LOW | Local box already runs full-sync (heavier); monitor first week durations |
| Rollback | — | Re-add crons to vercel.json + revert SKILL.md URLs; both are 2-line git reverts |

## 4. Testing plan (hand to a Workflow at implementation)

Run as a workflow with one agent per test area + an adversarial reviewer.
Implementation is NOT done until all T-checks pass.

- **T1 cron-auth preflight (before any cutover):** read `verifyCronAuth` and
  confirm the header/secret name; locate `CRON_SECRET` in HB env (never print).
- **T2 local invocation:** call each of the 3 routes on `localhost:3000` with
  cron auth. Expect 200 + route-specific success JSON; record durations.
  FAIL if any 401/5xx or duration > 280s.
- **T3 effect verification:** after T2, confirm observable side-effects:
  ebay-stock-sync → `job_execution_history` row (HB Supabase) + stock numbers
  updated; bricqer-batch-sync → its sync table/timestamps advanced;
  cleanup → storage object count not increased. FAIL on "200 but no effect"
  (the silent-failure class — compare before/after rows, don't trust status).
- **T4 skill proxy paths:** for each endpoint named in the two SKILL.md files,
  GET/POST via `http://localhost:8100/hb/<path>` and confirm parity with the
  old Vercel response shape. Verify both SKILL.md files contain no
  `vercel.app` references afterwards; regenerate the skill manifest.
- **T5 scheduler registration:** restart bot; verify the 3 new jobs appear in
  the bot log + `job_history.db` after first run; verify Vercel deployments
  page shows NO cron invocations the following day (scrape or API).
- **T6 monitoring:** induce a failure (wrong secret in a test call) and
  confirm #alerts fires via tracked-job path. Confirm the 07:00 vercel-usage
  report next morning shows Fluid CPU trending at <0.5%/day.
- **T7 adversarial review:** reviewer attacks the new scheduling code for:
  timezone of cron triggers (Europe/London vs the times eBay/Bricqer expect),
  overlap with the 09:35 full-sync (double work?), missing `max_instances=1`,
  and what happens when localhost:3000 is mid-build/crash-looping
  (HadleyBricks NSSM restart scenario — yesterday's `.next` incident).

**Cutover sequence:** C1 anytime → C2 step 1 + observe 24h (T2-T6) →
C2 step 2 (remove Vercel crons) → T5 next-day verification → close.

---

## 5. Post-implementation findings (12 Jun 2026, production validation workflow)

**Validation outcome:** bricqer-batch-sync ✅ (71 batches, verified in history),
scanner-image-cleanup ✅, skills-via-proxy ✅ (incl. POST body forwarding read
in proxy code), registration + induced-401 ✅, vercel.json cron-free on
origin/main ✅ (PR #435).

**Hardenings added from findings:** embedded-failure detection (a 200
`{success:true}` carrying usersFailed/failures/errors counters now raises),
startup catch-up replay (MemoryJobStore can't replay missed slots across
restarts — a boot-time check re-runs any UTC slot missed today), retry-once
15 min after a failure.

**KNOWN ISSUE — ebay-stock-sync fails locally:** persistent `fetch failed`
inside EbayStockService.triggerImport when run on the local box (worked from
Vercel at 06:04). Python reaches api.ebay.com/apiz.ebay.com fine from the
same box → Node/undici-specific (IPv6? specific feed host?). NOT data-loss:
the 09:35 local full-sync covers eBay daily via a working path. The 06:00
job will alert until fixed; diagnose from the HadleyBricks NSSM server logs.

**MAJOR DISCOVERY — GCP Cloud Scheduler estate:** 37+ ENABLED jobs in GCP
project gen-lang-client-0823893317 (europe-west2) target
hadley-bricks-…vercel.app/api/cron/* — full-sync 6x daily (300s-class),
amazon-two-phase-sync every 10 min, ebay-auction-sniper every 15 min,
multiple 30-min/hourly pollers. This is the MAJORITY of the Fluid CPU burn;
the original attribution (~75% to the 3 vercel.json crons) was wrong, and
the fleet has grown since the Mar 2026 jobs audit (27 → 37+). The "~90%
drop" projection will NOT materialise from this migration alone.
**DECISION NEEDED (Chris):** migrate the GCP fleet to local scheduling
(big move — business-critical frequencies incl. the auction sniper), or
trim/slow the worst offenders (full-sync 6x daily?), or accept Vercel Pro.
Tomorrow's daily report projections give the empirical burn rate either way.
