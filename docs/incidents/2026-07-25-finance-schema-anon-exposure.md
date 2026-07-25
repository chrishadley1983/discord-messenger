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
