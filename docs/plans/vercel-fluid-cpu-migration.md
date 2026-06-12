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

---

## 6. PLAN v2 (12 Jun 2026) — data-driven, replaces section 2's projections

**Method correction:** v1 attributed CPU by wall-time heuristic and never
enumerated route invokers. v2 is built from (a) the full GCP Cloud Scheduler
fleet listing (40 jobs) and (b) 30 days of real per-job durations from
job_execution_history.

### Targets (88% of measured wall time, 7 jobs)

| Job | GCP schedule | Wall hrs/30d | Action |
|---|---|---|---|
| amazon-pricing | */30 | 9.16 | migrate local |
| full-sync | 45 3,7,11,15,19,23 | 8.32 | migrate local (note: also question 6x/day — local already runs one at 09:35) |
| ebay-fp-cleanup | 0,15,30,45 4 * * * | 4.97 | migrate local |
| investment-sync | 0 7 | 1.73 | migrate local |
| cost-allocation | 15 21 | 1.72 | migrate local |
| ebay-pricing | 0 2 | 1.68 | migrate local |
| retirement-sync | 0 6 | 0.95 | migrate local |

**Deliberately NOT migrating:** ebay-auction-sniper (*/15, 2.37h wall but
3s/run; live-bid latency + reliability favours cloud — revisit only if
still over after phase 1) and all trivial pollers (amazon-two-phase 0.5s,
minifig pollers 0.2s etc. — micro-burn, migration risk exceeds benefit).

### Mechanism
Extend jobs/hb_crons.py CRON_SPECS with the 7 routes at identical UTC
schedules (tracked + embedded-failure detection + retry; catch-up for the
daily ones only — multi-daily self-heal on the next slot). GCP jobs are
**paused, not deleted** (gcloud scheduler jobs pause) = instant rollback.

### Sequencing — test-THEN-cutover per job (v1 lesson, the eBay case)
For each job, in order of burn: (1) invoke the route on localhost:3000 with
cron auth, (2) verify duration + a real effect in job_execution_history /
domain tables, (3) only then register locally + pause the GCP job, (4) next
scheduled local run verified green before starting the next job. Any local
failure (ebay-stock-sync-style) = leave that job on GCP, file the defect.

### Risks (v2)
| Risk | Mitigation |
|---|---|
| A route works on Vercel but not locally (proven class: ebay-stock-sync 'fetch failed') | per-job test-before-cutover gate; GCP job stays enabled until local proof |
| Local box outage hits 7 more business jobs | daily ones get catch-up replay; sub-daily self-heal; tracked alerts + dead-man already in place; bids (sniper) deliberately not moved |
| full-sync 6x/day x 166s on local hardware contends with 09:35 full-sync + Peter | jobs are sequential per schedule; box already runs heavier work; monitor first-week durations in job history |
| CPU-vs-wall ratio unknown — even 88% wall might not be 88% CPU | daily report projections give empirical burn within ~3 days of each phase |
| GCP pause forgotten → double runs if local also registered | pause in the SAME working session as local registration; routes idempotent |

### Open defects folded in
1. ebay-stock-sync local 'fetch failed' (Node/undici; Python fine) — diagnose
   via HadleyBricks NSSM logs; until fixed it alerts daily at 06:00.
2. delivery-report 18% failure rate, investment-retrain 100% (894s timeout)
   — pre-existing, surfaced by the duration analysis; triage separately.

### Workflow test spec (hand over at implementation)
Per migrated job: invoke → duration < route maxDuration*0.9 → effect row in
job_execution_history with items_failed=0 → embedded-failure counters zero
→ GCP job state=PAUSED → next-day local run green. Plus adversarial review
of the extended CRON_SPECS (schedule transcription errors UTC, overlap
windows, catch-up applicability flags) and a day-3 projection check
(<2%/day Fluid CPU).

---

## 7. Phase 2 cutover record (12 Jun 2026)

**Correction to v2 table:** amazon-pricing + ebay-pricing GCP jobs target a
Cloud Run service (pricing-sync-driver), NOT Vercel — their 10.8 wall-hrs
never burned Fluid CPU. True Vercel set = 5 jobs (~17.7 wall-hrs) + the
dead investment-retrain.

**Gates (production, per job):** full-sync ✅ 123s local (also: ALL 671
historical runs were GCP-fired — the believed daily local run used a
different route; and items_failed=1 is chronic on every run = sub-sync
defect, filed); ebay-fp-cleanup ✅ 150s; investment-sync ✅ 139s (caveat:
price-alerts has no dedup — re-runs re-send Discord alerts); cost-allocation
✅ 97s (idempotent, converges); retirement-sync ✅ on parity (Brick Tap
sheet 400 chronic everywhere, filed).

**Cutover:** 9 jobs registered locally (bot log 10:58), 6 GCP jobs PAUSED
(verified). investment-retrain backfill running locally (first possible
completion ever — needs ~15+ min vs Vercel's 300s cap). Review fixes
applied: catch-up dead zone, trailing-25h window, tracked retries, HB
readiness gate.

**delivery-report fix:** root cause was a Royal Mail uib-modal popup
(30 May–1 Jun) blocking the Export click — scraper now dismisses overlays;
Cloud Run image rebuilding via cloudbuild.

**Deletion:** one-shot evidence check 17 Jun 09:23 deletes the 6 paused GCP
jobs only if 5 clean days of local runs (session-bound scheduler — if it
never fires, jobs simply stay PAUSED; this doc records the obligation).

**Open defects (filed, not blocking):** ebay-stock-sync local 'fetch
failed' (Node); full-sync chronic items_failed=1 sub-sync; Brick Tap 400;
investment-sync price-alert dedup; cost-allocation items_failed hardcoded 0.
