# Life Admin Agent — Test Plan

Generated: 2026-03-28

## Scope

Tests covering the full Life Admin Agent feature:
- Supabase tables (3 tables, RLS, indexes)
- Hadley API routes (12 endpoints in `peter_routes/life_admin.py`)
- Data fetchers (4 functions in `data_fetchers.py`)
- Skills (5 SKILL.md files)
- Schedule integration (3 cron entries)
- Documentation updates

---

## 0. Known Bugs (Found During Analysis)

These MUST be fixed before test execution:

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| BUG-1 | CRITICAL | **Table name mismatch**: API references `life_admin_scan_history` but migration created `life_admin_email_scans` | `life_admin.py:38` |
| BUG-2 | CRITICAL | **Column `title` doesn't exist**: API models use `title` but DB column is `name` | `life_admin.py:55,71` |
| BUG-3 | CRITICAL | **Column `cost_gbp` doesn't exist**: API uses `cost_gbp` but DB column is `amount` | `life_admin.py:63,79` |
| BUG-4 | CRITICAL | **Column `reference` doesn't exist**: API uses `reference` but DB column is `reference_number` | `life_admin.py:62,78` |
| BUG-5 | HIGH | **Column `owner` doesn't exist in DB**: API models include `owner` field but DB has no such column | `life_admin.py:60,76` |
| BUG-6 | MEDIUM | **Missing DB columns in API**: `subcategory`, `description`, `renewal_date`, `auto_renews`, `alert_priority`, `currency`, `gmail_query`, `last_email_id` not exposed in Pydantic models | `life_admin.py:54-82` |
| BUG-7 | MEDIUM | **Alert priority not in API**: DB has `alert_priority` column for delivery routing (critical→WhatsApp, low→dashboard only) but API models don't include it — alerts endpoint can't group by priority | `life_admin.py:311-398` |

---

## 1. Database Layer (CRITICAL)

| # | Test | Method | Expected | Priority |
|---|------|--------|----------|----------|
| DB-1 | Tables exist | `SELECT * FROM information_schema.tables WHERE table_name LIKE 'life_admin%'` | 3 tables returned | CRITICAL |
| DB-2 | Obligations columns match spec | `SELECT column_name FROM information_schema.columns WHERE table_name='life_admin_obligations'` | All 22 columns present | CRITICAL |
| DB-3 | Alert history FK constraint | Insert alert_history with non-existent obligation_id | FK violation error | HIGH |
| DB-4 | Alert history unique constraint | Insert same obligation_id + alert_tier twice | Unique violation on second insert | HIGH |
| DB-5 | RLS enabled | `SELECT relrowsecurity FROM pg_class WHERE relname='life_admin_obligations'` | true | HIGH |
| DB-6 | Service role can CRUD | INSERT/SELECT/UPDATE/DELETE as service_role | All succeed | CRITICAL |
| DB-7 | Anon can only read | INSERT as anon role | Permission denied | HIGH |
| DB-8 | Active due_date index works | EXPLAIN query with `status='active'` and `due_date` filter | Index scan used | MEDIUM |
| DB-9 | Cascade delete | Delete obligation → alert_history rows deleted too | Cascade works | HIGH |
| DB-10 | Default values | Insert minimal row (name, category) | `status='active'`, `alert_lead_days='{90,30,14,7,3}'`, `currency='GBP'` | MEDIUM |

---

## 2. API Routes — CRUD (CRITICAL)

| # | Test | Method | Expected | Priority |
|---|------|--------|----------|----------|
| API-1 | List obligations (empty) | `GET /life-admin/obligations` | `[]` (empty array, 200) | CRITICAL |
| API-2 | Create obligation | `POST /life-admin/obligations` with auth + valid body | 201, returns created row with UUID | CRITICAL |
| API-3 | Create without auth | `POST /life-admin/obligations` without x-api-key | 401/403 | CRITICAL |
| API-4 | Get single obligation | `GET /life-admin/obligations/{id}` | Returns matching row | CRITICAL |
| API-5 | Get non-existent | `GET /life-admin/obligations/{random-uuid}` | 404 | HIGH |
| API-6 | List with status filter | `GET /life-admin/obligations?status=active` | Only active rows | HIGH |
| API-7 | List with category filter | `GET /life-admin/obligations?category=vehicle` | Only vehicle rows | HIGH |
| API-8 | Update obligation | `PATCH /life-admin/obligations/{id}` with auth | Updated fields returned, updated_at set | CRITICAL |
| API-9 | Update with empty body | `PATCH /life-admin/obligations/{id}` with `{}` | 400 "No fields to update" | MEDIUM |
| API-10 | Delete obligation | `DELETE /life-admin/obligations/{id}` with auth | 200, {status: "deleted"} | CRITICAL |
| API-11 | Delete without auth | `DELETE /life-admin/obligations/{id}` without key | 401/403 | HIGH |

---

## 3. API Routes — Actions (CRITICAL)

| # | Test | Method | Expected | Priority |
|---|------|--------|----------|----------|
| ACT-1 | Action non-recurring | `POST /obligations/{id}/action` on one-off obligation | status='actioned', last_actioned_date=today, no next occurrence | CRITICAL |
| ACT-2 | Action recurring (12mo) | `POST /obligations/{id}/action` on annual obligation (due 2026-05-15) | Original actioned + new obligation with due_date=2027-05-15 | CRITICAL |
| ACT-3 | Action recurring (3mo) | `POST /obligations/{id}/action` on quarterly (due 2026-04-30) | New obligation due 2026-07-30 | HIGH |
| ACT-4 | New occurrence copies fields | Action recurring obligation | New row has same title, category, provider, reference, alert_lead_days | HIGH |
| ACT-5 | Snooze obligation | `POST /obligations/{id}/snooze` with `{"until": "2026-04-15"}` | status='snoozed', snoozed_until='2026-04-15' | CRITICAL |
| ACT-6 | Snooze without auth | `POST /obligations/{id}/snooze` without key | 401/403 | HIGH |

---

## 4. API Routes — Alerts & Dashboard (HIGH)

| # | Test | Method | Expected | Priority |
|---|------|--------|----------|----------|
| ALT-1 | Alerts with no obligations | `GET /life-admin/alerts` | `{tiers: {}, total_alerts: 0}` | HIGH |
| ALT-2 | Overdue obligation detected | Create obligation with due_date in past, GET /alerts | Appears in `tiers.overdue` | CRITICAL |
| ALT-3 | 30-day alert tier | Create obligation due in 25 days with alert_lead_days=[30,7], GET /alerts | Appears in `tiers.30d` | HIGH |
| ALT-4 | Already-sent tier suppressed | Record alert for tier "30d", then GET /alerts | Same obligation NOT in `tiers.30d` | HIGH |
| ALT-5 | Snoozed obligation hidden | Snooze obligation until future, GET /alerts | Not in any tier | HIGH |
| ALT-6 | Expired snooze visible | Snooze obligation until yesterday, GET /alerts | Appears in appropriate tier | MEDIUM |
| ALT-7 | Dashboard grouping | Create mixed obligations, GET /dashboard | Correct grouping: overdue/due_this_week/due_this_month/all_clear | HIGH |
| ALT-8 | Dashboard counts | GET /dashboard | counts dict matches group lengths | MEDIUM |
| ALT-9 | Record alert | `POST /alerts/record` with obligation_id + tier | 201, row created in alert_history | HIGH |
| ALT-10 | Duplicate alert rejected | POST same obligation_id + tier twice | Second returns 409 (unique constraint) | MEDIUM |

---

## 5. API Routes — Email Scans (MEDIUM)

| # | Test | Method | Expected | Priority |
|---|------|--------|----------|----------|
| SCN-1 | Record scan | `POST /life-admin/scans` with auth | 201, scan recorded | MEDIUM |
| SCN-2 | List scans | `GET /life-admin/scans` | Returns array, ordered by scanned_at desc | MEDIUM |
| SCN-3 | Scan limit param | `GET /life-admin/scans?limit=3` | Max 3 results | LOW |

---

## 6. Data Fetchers (HIGH)

| # | Test | Method | Expected | Priority |
|---|------|--------|----------|----------|
| DF-1 | Scan fetcher registered | Check `SKILL_DATA_FETCHERS["life-admin-scan"]` | Points to `get_life_admin_scan_data` | CRITICAL |
| DF-2 | Email scan fetcher registered | Check `SKILL_DATA_FETCHERS["life-admin-email-scan"]` | Points to `get_life_admin_email_scan_data` | CRITICAL |
| DF-3 | Compare fetcher registered | Check `SKILL_DATA_FETCHERS["life-admin-compare"]` | Points to `get_life_admin_compare_data` | HIGH |
| DF-4 | Dashboard fetcher registered | Check `SKILL_DATA_FETCHERS["life-admin-dashboard"]` | Points to `get_life_admin_dashboard_data` | HIGH |
| DF-5 | Scan data structure | Call `get_life_admin_scan_data()` | Returns dict with `alerts`, `summary`, `date` keys | HIGH |
| DF-6 | Email scan data structure | Call `get_life_admin_email_scan_data()` | Returns dict with `email_results`, `existing_obligations`, `scan_timestamp` | HIGH |
| DF-7 | Fetcher handles API down | Mock Hadley API returning 500 | Returns `{"error": "..."}`, doesn't crash | MEDIUM |

---

## 7. Skills (MEDIUM)

| # | Test | Method | Expected | Priority |
|---|------|--------|----------|----------|
| SKL-1 | life-admin-scan exists | `cat skills/life-admin-scan/SKILL.md` | Valid YAML frontmatter + content | CRITICAL |
| SKL-2 | life-admin-email-scan exists | `cat skills/life-admin-email-scan/SKILL.md` | Valid YAML frontmatter + content | CRITICAL |
| SKL-3 | life-admin exists | `cat skills/life-admin/SKILL.md` | Valid YAML frontmatter, conversational=true | CRITICAL |
| SKL-4 | life-admin-compare exists | `cat skills/life-admin-compare/SKILL.md` | Valid YAML frontmatter, conversational=true | HIGH |
| SKL-5 | life-admin-dashboard exists | `cat skills/life-admin-dashboard/SKILL.md` | Valid YAML frontmatter, scheduled+conversational | HIGH |
| SKL-6 | Frontmatter valid YAML | Parse all 5 SKILL.md frontmatters | All parse without errors | HIGH |
| SKL-7 | API base URL correct | Grep all skills for API URL | All reference `http://172.19.64.1:8100` | MEDIUM |

---

## 8. Schedule Integration (HIGH)

| # | Test | Method | Expected | Priority |
|---|------|--------|----------|----------|
| SCH-1 | life-admin-scan in schedule | Grep SCHEDULE.md | `life-admin-scan | 08:30 UK | #alerts+WhatsApp:chris` | HIGH |
| SCH-2 | life-admin-email-scan in schedule | Grep SCHEDULE.md | `life-admin-email-scan | 03:30 UK | #peter-heartbeat!quiet` | HIGH |
| SCH-3 | life-admin-dashboard in schedule | Grep SCHEDULE.md | `life-admin-dashboard | Sunday 09:15 UK | #peterbot` | HIGH |

---

## 9. Documentation (LOW)

| # | Test | Method | Expected | Priority |
|---|------|--------|----------|----------|
| DOC-1 | README has life-admin section | Grep hadley_api/README.md | Life Admin section with endpoint table | LOW |
| DOC-2 | CLAUDE.md has life-admin reference | Grep wsl_config/CLAUDE.md | Life Admin bullet point | LOW |

---

## 10. Integration Tests (HIGH)

| # | Test | Method | Expected | Priority |
|---|------|--------|----------|----------|
| INT-1 | Full lifecycle | Create → List → Update → Action → Verify next occurrence → Delete | All operations succeed, data consistent | CRITICAL |
| INT-2 | Alert lifecycle | Create overdue obligation → GET /alerts → Record alert → GET /alerts again | First call shows alert, second suppresses it | HIGH |
| INT-3 | Dashboard reflects changes | Create obligations in various states → GET /dashboard | All groups populated correctly | HIGH |
| INT-4 | Peter_routes auto-discovery | Restart Hadley API → GET /life-admin/obligations | Routes loaded automatically | HIGH |

---

## Test Execution Order

1. Fix BUG-1 through BUG-7 first
2. DB tests (DB-1 to DB-10)
3. API CRUD (API-1 to API-11)
4. API Actions (ACT-1 to ACT-6)
5. API Alerts + Dashboard (ALT-1 to ALT-10)
6. Integration tests (INT-1 to INT-4)
7. Data fetchers (DF-1 to DF-7)
8. Skills + Schedule + Docs (SK, SCH, DOC)
