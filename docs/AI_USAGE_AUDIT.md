# Shared AI API-usage audit log

One Supabase table records **every raw Anthropic-API-key call across all of
Chris's projects**, so spend can be attributed per project/feature/model in one
place — and reconciled against Anthropic's own billing to expose gaps.

This is the **API-credit bucket** (pay-as-you-go `ANTHROPIC_API_KEY`), separate
from Peter's Max-subscription channels and the `claude -p` programmatic credit.

## Where it lives

Supabase project **`modjoikyuhqzouxvieua`** ("Inventory Management App") — the
project HB, Football and the Second Brain (discord-messenger) already share.

| Table | Purpose |
|-------|---------|
| `ai_api_usage` | one row per Anthropic call (project, feature, model, tokens, est. cost) |
| `anthropic_api_keys` | maps Anthropic `api_key_id` → project (trivial today: one shared key) |
| `ai_usage_reconciliation` | daily diff: Anthropic Admin truth vs sum of logged calls |

`ai_api_usage` columns: `project, feature, model, billing_source('api_key'|
'programmatic'|'subscription'), input_tokens, output_tokens,
cache_creation_input_tokens, cache_read_input_tokens, cost_usd (estimated),
request_ms, status, error, anthropic_message_id, request_id, metadata, created_at`.

## How each project writes (fire-and-forget, never blocks the request)

Two write paths, both POST to the same table:

1. **Host-project repos** (HB, Football) — already hold the
   `modjoikyuhqzouxvieua` **service-role** key. Insert via their existing
   `createServiceRoleClient()` / `createAdminClient()`.

2. **Everyone else** (family-meal-planner, finance-tracker, GainAI, Poker,
   instagram-automation, …) — use the **publishable key** (the table has an
   INSERT-only RLS policy for `anon`; it can write but not read). Set two env vars:

   ```
   AI_USAGE_SUPABASE_URL=https://modjoikyuhqzouxvieua.supabase.co
   AI_USAGE_SUPABASE_KEY=sb_publishable_ZfSKKyHywBhDtS4RLLUi5w_3Q_5Fu6v
   ```

   POST `{AI_USAGE_SUPABASE_URL}/rest/v1/ai_api_usage` with headers
   `apikey` + `Authorization: Bearer <key>` + `Content-Type: application/json` +
   `Prefer: return=minimal`, body = one row. (Publishable key is safe to ship; the
   INSERT-only policy means it cannot read or alter the audit data.)

The reference implementation is `domains/api_usage/audit_log.py` (Python). Each
TS/JS/Deno repo carries a ~25-line equivalent (`lib/ai-usage-audit.ts` etc.) —
captured at the project's existing Anthropic chokepoint, reading `response.usage`
+ `response.model`, tagging a `feature`, and inserting on a non-awaited promise
wrapped in try/catch (a logging failure must never break the user request).

### Feature labels (so spend is attributable)

`hadley-bricks`: `ebay_listing_generation`, `ebay_listing_improvement`,
`listing_assistant`, `purchase_evaluator_photo`, `school_newsletter`, … ·
`football-predictor`: `pundit:<key>` · `family-fuel`: `nutritionist_chat`,
`shopping_list_import`, `product_parse`, … · `finance-tracker`:
`pdf_vision_parse`, `ai_mapper`, `categoriser` · `gainai`: `report_generate` ·
`poker`: `<feature>` · `instagram-automation`: `caption_generate` ·
`discord-messenger`: `japan_scraper`.

## Reconciliation (exposing gaps)

`domains/api_usage/reconcile.py` pulls Anthropic's **Admin** usage_report
(`/v1/organizations/usage_report/messages`, grouped by model × api_key_id, daily)
and cost_report, sums `ai_api_usage` by day×model, and upserts
`ai_usage_reconciliation`.

- **Gap = Anthropic − logged** on the shared key → un-instrumented usage (a
  project/call-site not yet wired). Alerts #alerts when a day's keyed output-token
  gap > 5,000 and > 25%.
- Anthropic rows with **null `api_key_id`** = Workbench/Console (manual) usage,
  stored under `api_key_id='console'` — unattributable, expected, not a gap.
- With a **single shared key**, attribution is done in *our* table (the `project`
  column); Anthropic only confirms the aggregate. Split keys later only if a gap
  can't be pinned down.

**Requires `ANTHROPIC_ADMIN_KEY`** (an org-admin-only Admin API key, created in
Console → Settings → Admin keys — distinct from a normal API key).

**Individual / API-plan accounts (no admin key possible):** Anthropic's Admin API
is unavailable for individual accounts — there's no "Admin keys" menu and none can
be minted (would require converting to a Team org). Use the Console **cost CSV
export** instead (Usage → Export): it includes an `api_key` column, so cost is
attributable per project with no admin key. Reconcile with
`python -m domains.api_usage.reconcile_csv <export.csv> --store`, or
`POST /usage/reconcile/csv` (CSV as the request body). Same gap report
(`ai_usage_reconciliation`), account-tier-independent. See
`domains/api_usage/reconcile_csv.py`. Until it's set, reconcile logs a warning and
skips cleanly. Runs daily 07:30 UK (`domains/api_usage/schedules.py`), or:

```
python -m domains.api_usage.reconcile --days 3
```

## Endpoints (Hadley API :8100)

- `GET  /usage/audit?hours=24`       — logged spend by project/feature/model
- `GET  /usage/reconcile?days=7`     — latest reconciliation rows + gaps
- `POST /usage/reconcile/run?days=3` — run reconciliation now

## Per-project rollout status

| Project | Status |
|---------|--------|
| discord-messenger (host of reconcile job + endpoints) | ✅ implemented & verified |
| Hadley Bricks | wrap `lib/ai/claude-client.ts` (service-role) |
| Football | wrap `generateForPundit` (service-role) |
| family-meal-planner, finance-tracker, GainAI, Poker, instagram-automation | helper + publishable-key write |
| factorio/assistant, japan-family-guide | latent — instrument for completeness |

Each project ships a `scripts/validate-ai-audit.*` workflow (see per-project PRs)
that triggers a real production call and confirms the matching row in `ai_api_usage`.

## Human-gated steps

1. Create `ANTHROPIC_ADMIN_KEY` (org admin) → enables reconciliation.
2. Set `AI_USAGE_SUPABASE_URL` / `AI_USAGE_SUPABASE_KEY` on each non-host deploy.
3. Merge each project's PR and let it deploy (Vercel) / restart (local NSSM).
