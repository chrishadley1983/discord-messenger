# AI-usage audit — deploy & prod-validation runbook

Companion to `docs/AI_USAGE_AUDIT.md`. Tracks what's live, what's left, and how
to validate each project in production.

## Live now (done)

- ✅ Shared schema in Supabase `modjoikyuhqzouxvieua`: `ai_api_usage`,
  `anthropic_api_keys`, `ai_usage_reconciliation` (RLS: service-role full,
  publishable insert-only — verified).
- ✅ discord-messenger code is live (HadleyAPI restarted via the dashboard).
  `GET /usage/audit` returns 200. Runs from its working tree on branch
  `feat/ai-usage-audit` (PR #10) — when merged, `git checkout main && git pull`
  on the box.
- ✅ Review PRs open: discord-messenger #10, Football #9, family-meal-planner #1,
  finance-tracker #13, GainAI #1, japan-family-guide #1.

## Remaining steps

### 1. Merge the 6 PRs → Vercel auto-deploys
Football, family-meal-planner, finance-tracker, GainAI deploy on merge to their
default branch. japan-family-guide is a local scraper (no deploy). DM is already
live locally.

### 2. Hadley Bricks — manual PR (not auto-opened: mid-feature branch w/ 246 dirty files)
HB is the live repo (hb-umd is just a feature copy). From
`hadley-bricks-inventory-management`, stage ONLY the instrumentation files onto
a branch of your choosing:

```bash
git checkout -b feat/ai-usage-audit            # or commit onto the current feature branch
git add apps/web/src/lib/ai/ai-usage-audit.ts \
        apps/web/src/lib/ai/claude-client.ts \
        apps/web/src/lib/ebay/listing-generation.service.ts \
        apps/web/src/lib/ebay/listing-quality-review.service.ts \
        apps/web/src/lib/listing-assistant/ai-service.ts \
        apps/web/src/lib/purchase-evaluator/photo-analysis.service.ts \
        apps/web/scripts/auto-fix-review-queue.ts \
        scripts/school/ai_usage_audit.py \
        scripts/school/newsletter_scraper.py \
        scripts/school/arbor_monitor.py \
        scripts/school/term_dates_poller.py \
        scripts/validate-ai-audit.mjs
git commit -m "feat(observability): log Anthropic API usage to shared ai_api_usage"
git push -u origin HEAD && gh pr create
```
Uses HB's existing service-role client — no new env vars. Deploys on merge.

### 3. instagram-automation edge function (Deno, not git-managed locally)
```bash
supabase functions deploy generate-instagram-posts
supabase secrets set AI_USAGE_SUPABASE_URL=https://modjoikyuhqzouxvieua.supabase.co
supabase secrets set AI_USAGE_SUPABASE_KEY=sb_publishable_ZfSKKyHywBhDtS4RLLUi5w_3Q_5Fu6v
```
(Defaults are baked in, so logging works even without the secrets; setting them
is hygiene.)

### 4. Poker & factorio (local, not git/Vercel)
Restart the local processes to pick up the working-tree changes. No deploy step.

### 5. (Optional) Turn on gap-detection — `ANTHROPIC_ADMIN_KEY`
Only needed for the reconciliation/gap report (logging works without it).
1. Console → Settings → **Admin keys** → create an org Admin API key.
2. Add `ANTHROPIC_ADMIN_KEY=<key>` to `discord-messenger/.env`.
3. Restart the bot to load the key + the `daily_ai_reconcile` schedule:
   `POST http://localhost:5000/api/restart/discord_bot` with `x-api-key: $HADLEY_AUTH_KEY`
   (the dashboard runs with service rights — no admin shell needed).
The reconcile job then runs daily 07:30 UK, or on demand:
`POST /usage/reconcile/run?days=3`.

## Validate in production

Each repo ships `scripts/validate-ai-audit.*` (triggers a real prod call, then
confirms the row in `ai_api_usage`). Reads need the **service-role** key
(publishable is insert-only):

```bash
export AI_USAGE_SERVICE_KEY=<modjoikyuhqzouxvieua service-role key>
node scripts/validate-ai-audit.mjs          # per TS/JS repo
python scraper/validate-ai-audit.py         # japan-family-guide
```

**Cross-project completeness meter** (run from discord-messenger; uses its own
`SUPABASE_SERVICE_ROLE_KEY`):
```bash
python scripts/validate_ai_audit_prod.py --hours 24
```
Lists which of the 10 projects have logged rows (live) vs silent. As each deploys
and takes traffic, more flip to live. With the admin key set, `GET /usage/reconcile`
shows the gap (Anthropic truth − logged); a persistent gap = something still
un-instrumented, and `console` rows = Workbench/manual usage (expected).
