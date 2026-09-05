# finance schema readable with the public anon key

**Date:** 2026-07-25 (found 2026-07-21 by security-monitor)
**Severity:** High — confidentiality. No integrity impact.
**Status:** Resolved.

## What was wrong

The `finance` schema on the Inventory Management App project
(`modjoikyuhqzouxvieua`) was readable by anyone holding the public anon key.
Anon keys are public by design — they are embedded in client bundles and in
Peterbot's own skill files — so RLS and table grants are the only thing
protecting the data. Both were misconfigured.

Two independent defects:

1. `finance._backup_global_money_tx_20260701` had RLS disabled entirely. This
   was the only one Supabase's advisor email mentioned, because the linter
   only raises ERROR on RLS-off.
2. 25 tables had RLS enabled but carried an `ALL TO public USING (true)`
   policy, combined with a table-level `SELECT` grant to `anon`. The linter
   rates this WARN (`rls_policy_always_true`), so it never appeared in the
   email despite exposing far more data.

A third route existed via RPC: `finance.add_monthly_manual_income()` is
`SECURITY DEFINER` with a NULL `proacl`, so `EXECUTE` defaulted to `PUBLIC`.
Anon could POST to `/rest/v1/rpc/add_monthly_manual_income` and write a row
into `finance.transactions` regardless of table grants.

Finally, `pg_default_acl` for the schema was `{anon=r/postgres}` — every new
table created in `finance` was automatically granted SELECT to anon, so any
table-by-table fix would have silently reopened.

## Exposed

Confirmed by live read with the anon key: `transactions` (3,683 rows, real
HSBC descriptions/amounts/dates), `wealth_snapshots` (813, back to 2019),
`budgets` (2,148), `categories` (40), `import_sessions` (38), `subscriptions`
(36), `planning_notes` (20), `ai_usage_tracking` (7), `accounts` (14),
`_backup_global_money_tx_20260701` (34), `fire_inputs` (1).

## Not exposed

`truelayer_connections`, `enable_banking_sessions` and `monthly_reports` have
RLS enabled with zero policies — deny-all. All returned 0 rows via anon. No
bank connection credentials were reachable.

## Corrections to the original finding

- The first write-up said anon had "full SELECT/INSERT/UPDATE/DELETE" but
  noted writes were untested. Writes were in fact already blocked: anon held
  only `SELECT`, so DELETE and PATCH returned 401. This was a confidentiality
  leak, not an integrity or destruction risk.
- The scope was 25 tables with permissive policies, not 3.
- Three policies are *named* as if they were service-role-only — "Service role
  full access on subscriptions", "Service role full access on
  subscription_price_history", "Allow full access via service key" — but all
  three are `TO public USING (true)`. The names are misleading.

## Fix

Two migrations. The approach deliberately differs from the drafted fix, which
rewrote policies on three tables: revoking anon's privileges closes all 26 at
once and touches nothing else, because `service_role` and `authenticated` hold
their own explicit grants.

    -- revoke_anon_access_to_finance_schema
    ALTER DEFAULT PRIVILEGES IN SCHEMA finance REVOKE SELECT ON TABLES FROM anon;
    REVOKE ALL ON ALL TABLES IN SCHEMA finance FROM anon;
    ALTER TABLE finance._backup_global_money_tx_20260701 ENABLE ROW LEVEL SECURITY;

    -- revoke_anon_execute_on_finance_manual_income
    REVOKE EXECUTE ON FUNCTION finance.add_monthly_manual_income() FROM PUBLIC;
    REVOKE EXECUTE ON FUNCTION finance.add_monthly_manual_income() FROM anon;

## Why nothing broke

Every consumer was checked before applying:

- `financial_data` MCP, `hadley_api/finance_routes.py` and
  `peter_dashboard/api/subscriptions.py` all use `API_KEY`, and both
  `SUPABASE_SERVICE_ROLE_KEY` and `SUPABASE_KEY` in `.env` are service_role
  keys. (The comment in `mcp_servers/financial_data/config.py` calling
  `SUPABASE_KEY` the anon key is wrong.)
- finance-tracker (the deployed frontend) queries through `supabaseAdmin`
  (service_role) in server-side API routes. Its browser anon client is used in
  exactly two places — `signInWithPassword` and `signOut`. Auth endpoints are
  unaffected by table grants.
- The two hardcoded anon keys in `data_fetchers.py` invoke Edge Functions for
  the 11+ tutor app, not finance tables.
- The HB inventory app does not touch the finance schema.
- `add_monthly_manual_income()`'s real caller is pg_cron job 7
  (`0 6 28-31 * *`) running as `postgres`, the function owner.

## Verification after applying

- anon → HTTP 401 on all 12 tables tested, and on the RPC.
- service_role reads unchanged: transactions still 3,683, budgets 2,148.
- financial-data MCP `get_net_worth` returns the full breakdown end-to-end.
- Supabase advisor no longer reports `rls_disabled_in_public` for the backup
  table; it now shows as `rls_enabled_no_policy` (INFO), the intended state.

## Rollback

    GRANT SELECT ON ALL TABLES IN SCHEMA finance TO anon;
    ALTER DEFAULT PRIVILEGES IN SCHEMA finance GRANT SELECT ON TABLES TO anon;

## Follow-ups

- The 25 always-true policies still grant `authenticated` full read/write.
  Latent rather than active — finance-tracker's data path is service_role —
  but worth tightening to authenticated-only-where-needed.
- 82 `rls_policy_always_true` warnings remain project-wide; the HB inventory
  tables need the same review.
- 3 ERROR-level `security_definer_view` advisories exist in the `public`
  schema (`honours_with_tournament`, `tournament_leaderboard`,
  `keepa_refresh_candidates`) — unrelated to finance, not addressed here.
- `_backup_global_money_tx_20260701` is dated 20260701 and holds 34 rows. If it
  was a one-off migration backup, consider dropping it.

---

# Part 2 — the same schema was read/write for every logged-in user

**Same day, found while triaging the "remaining follow-ups" above.**

Part 1 closed anon. That left the 25 `ALL TO public USING (true)` policies in
place, which I initially recorded as "latent, not active" on the assumption
that `authenticated` was effectively just Chris. That assumption was wrong.

## Why it was not latent

`auth.users` holds **68 users, 58 of whom signed up in June 2026** — all
confirmed, all having signed in, from aol/hotmail/yahoo/icloud/sky/talktalk
addresses. The football prediction game shares this Supabase project, so
`authenticated` meant roughly 58 external people, not one.

`public` in a POLICY means every role, so those policies covered
`authenticated`, which held `DELETE, INSERT, REFERENCES, SELECT, TRIGGER,
TRUNCATE, UPDATE` on every finance table. Strictly worse than the anon leak in
Part 1, where anon held `SELECT` only.

## Demonstrated, not inferred

A throwaway user was created via the Admin API with `email_confirm: true`, then
signed in through the ordinary anon-key password flow — exactly what any app
user does. Its JWT carried `"role": "authenticated"`.

With that token and `Accept-Profile: finance`:

    finance.transactions       HTTP 206  rows=0-0/3683
    finance.wealth_snapshots   HTTP 206  rows=0-0/813
    finance.accounts           HTTP 206  rows=0-0/14
    finance.budgets            HTTP 206  rows=0-0/2148

    DELETE finance.transactions      -> HTTP 204
    PATCH  finance.transactions      -> HTTP 204
    DELETE finance.wealth_snapshots  -> HTTP 204

`204` means authorized and executed. The filters used the nil UUID so they
matched zero rows; the transaction count was 3,683 before and after. The user
was deleted after verification (`auth.users` back to 68, 0 probe users left).

## Fix

Migration `lock_finance_schema_to_service_role`:

- Dropped every policy in the schema, dynamically rather than by name — three
  were misleadingly named ("Service role full access on subscriptions",
  "Allow full access via service key") despite being `TO public`.
- Enabled RLS on any table lacking it, so "no policies" means deny-all.
- Revoked `authenticated`'s table privileges and removed it from
  `pg_default_acl` (it was `authenticated=arwdDxtm`, so new tables would have
  re-granted automatically).

finance is now reachable only by `service_role`, which has BYPASSRLS. Three
tables in this schema already ran this way, which is why it was known-safe.

## Verification

- The *same* JWT that read 3,683 rows: **403** on all six tables tested, and
  403 on DELETE and PATCH.
- service_role unchanged: transactions 3,683, budgets 2,148, subscriptions 36,
  truelayer_connections 1; PATCH still returns 204.
- financial-data MCP `get_net_worth` and `get_budget_status` both return full
  data end-to-end (the latter reads budgets + transactions + categories).
- Final state: 0 policies, 0 anon/authenticated grants, 0 tables without RLS.

## Rollback

    GRANT ALL ON ALL TABLES IN SCHEMA finance TO authenticated;
    ALTER DEFAULT PRIVILEGES IN SCHEMA finance GRANT ALL ON TABLES TO authenticated;
    -- then per table: CREATE POLICY allow_all_<t> ON finance.<t>
    --   FOR ALL TO public USING (true) WITH CHECK (true);

## Lesson

Judging `authenticated` as low-risk requires knowing who can become
authenticated. On a shared Supabase project, a consumer app's signup flow
silently widens every `TO public` policy in every other schema. Check
`auth.users` before calling that class of finding latent.

## Still open

46 tables outside finance remain anon-readable (`public` 31, `japan` 12,
`practice` 3) — including `price_snapshots` (2.7M rows of Keepa/BL pricing),
`energy_live` (62,701 rows of minute-resolution demand, an occupancy signal),
`japan_bookings`, and `practice.papers`. Unlike finance, these have **real anon
consumers** — the IHD dashboard reads `energy_daily_summary` with
`SUPABASE_ANON_KEY` in `ihd/ihd-app/src/app/api/energy/route.ts` — so they need
per-table triage, not a blanket revoke.
