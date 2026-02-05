# Hadley Bricks API Integration Consolidation Plan

## Problem Statement

There are TWO different authentication systems in use between Discord-Messenger (Hadley API) and Hadley Bricks:

1. **`validateAuth()`** - Simple key comparison
   - Compares `x-api-key` header against `INTERNAL_API_KEY` env var
   - Returns `SERVICE_USER_ID` on match
   - Used by: `/api/inventory`, `/api/purchases`, `/api/brickset/*`

2. **`withServiceAuth()`** - Strict service key validation
   - Requires `hb_sk_*` key format prefix
   - Validates against `service_api_keys` database table
   - Used by: `/api/service/*` endpoints

**Current Key Status:**
- Discord-Messenger `.env`: `HADLEY_BRICKS_API_KEY=08215bd643f242cc980d542d6453434dbdd01ca4d2464505b0e14d7713b9f8ce`
- HB local `.env.local`: `INTERNAL_API_KEY=08215bd643f242cc980d542d6453434dbdd01ca4d2464505b0e14d7713b9f8ce` (**MATCHED**)
- HB Vercel deployment: `INTERNAL_API_KEY=???` (**UNKNOWN - likely different!**)

**Root Cause:** The production Vercel deployment has its own environment variables which are NOT synced with the local `.env.local` file. The Vercel `INTERNAL_API_KEY` needs to be updated in the Vercel dashboard.

---

## Decision: Standardize on `validateAuth()`

**Rationale:**
- Simpler implementation (no database lookup required)
- Already used by most endpoints we need
- No special key format requirement
- Easier to maintain and debug

**Action:** All HB API calls will use regular endpoints (`/api/*`) with `x-api-key` header, NOT service endpoints (`/api/service/*`).

---

## Single Key Value

**Chosen Key:** Use the Discord-Messenger key as the source of truth:
```
08215bd643f242cc980d542d6453434dbdd01ca4d2464505b0e14d7713b9f8ce
```

This key must be set in BOTH:
1. `Discord-Messenger/.env` as `HADLEY_BRICKS_API_KEY`
2. `hadley-bricks-inventory-management/apps/web/.env.local` as `INTERNAL_API_KEY`

---

## All Integration Points

### Hadley API Endpoints (hadley_api/main.py)

| Endpoint | Method | HB Target | Auth Type |
|----------|--------|-----------|-----------|
| `/hb/inventory-status` | GET | `/api/inventory/status` | validateAuth |
| `/hb/dashboard` | GET | `/api/dashboard/kpi` | validateAuth |
| `/hb/orders` | GET | `/api/orders/pending` | validateAuth |
| `/hb/task-complete` | POST | `/api/tasks/{id}/complete` | validateAuth |
| `/hb/tasks` | GET | `/api/tasks` | validateAuth |
| `/hb/full-sync-print` | POST | `/api/inventory/sync` | validateAuth |
| `/hb/daily-activity` | GET | `/api/analytics/daily-activity` | validateAuth |
| `/hb/pnl` | GET | `/api/analytics/pnl` | validateAuth |
| `/hb/platform-performance` | GET | `/api/analytics/platform-performance` | validateAuth |
| `/hb/purchase-analysis` | GET | `/api/analytics/purchase-analysis` | validateAuth |
| `/hb/arbitrage-opportunities` | GET | `/api/arbitrage/opportunities` | validateAuth |
| `/hb/sets/{set_number}` | GET | `/api/brickset/sets/{set_number}` | validateAuth |
| `/hb/stock-check` | GET | `/api/brickset/stock-check` | validateAuth |
| `/hb/lookup-asin` | GET | `/api/brickset/lookup` | validateAuth |
| `/hb/competitive-pricing` | GET | `/api/amazon/competitive-pricing` | validateAuth |
| `/hb/inventory-aging` | GET | `/api/inventory/aging` | validateAuth |
| `/hb/pick-list` | GET | `/api/orders/pick-list` | validateAuth |
| `/hb/upcoming-pickups` | GET | `/api/pickups/upcoming` | validateAuth |
| `/hb/schedule-pickup` | POST | `/api/pickups/schedule` | validateAuth |
| `/hb/purchases` | POST | `/api/purchases` | validateAuth |
| `/hb/inventory` | POST | `/api/inventory` | validateAuth |
| `/hb/batch-import` | POST | `/api/email-purchases/batch-import` | validateAuth |

### Peter Skills Using HB

| Skill | Endpoints Used |
|-------|----------------|
| hb-add-inventory | `/hb/lookup-asin`, `/hb/competitive-pricing`, `/hb/inventory` |
| hb-add-purchase | `/hb/lookup-asin`, `/hb/competitive-pricing`, `/hb/batch-import` |
| hb-arbitrage | `/hb/arbitrage-opportunities` |
| hb-daily-activity | `/hb/daily-activity` |
| hb-dashboard | `/hb/dashboard` |
| hb-email-purchases | `/hb/batch-import` |
| hb-eval-purchase | `/hb/lookup-asin`, `/hb/competitive-pricing` |
| hb-inventory-aging | `/hb/inventory-aging` |
| hb-inventory-status | `/hb/inventory-status` |
| hb-orders | `/hb/orders` |
| hb-pick-list | `/hb/pick-list` |
| hb-platform-performance | `/hb/platform-performance` |
| hb-pnl | `/hb/pnl` |
| hb-purchase-analysis | `/hb/purchase-analysis` |
| hb-schedule-pickup | `/hb/schedule-pickup` |
| hb-set-lookup | `/hb/sets/{set_number}` |
| hb-stock-check | `/hb/stock-check` |
| hb-task-complete | `/hb/task-complete` |
| hb-tasks | `/hb/tasks` |
| hb-upcoming-pickups | `/hb/upcoming-pickups` |

### Scheduled Jobs

| Job | Endpoint | Schedule |
|-----|----------|----------|
| hb-email-purchases | `/hb/batch-import` | Daily 07:00 |
| hb-full-sync-print | `/hb/full-sync-print` | On-demand |

---

## Files to Modify

### 1. Vercel Environment Variables (CRITICAL - MUST DO FIRST)

**Location:** Vercel Dashboard → hadley-bricks-inventory-management → Settings → Environment Variables

**Required changes:**
```
INTERNAL_API_KEY=08215bd643f242cc980d542d6453434dbdd01ca4d2464505b0e14d7713b9f8ce
SERVICE_USER_ID=4b6e94b4-661c-4462-9d14-b21df7d51e5b
```

**After updating:** Redeploy the project to pick up the new environment variables.

### 2. HB Local Environment (Already Correct)

**File:** `hadley-bricks-inventory-management/apps/web/.env.local`

This file already has the correct key:
```env
INTERNAL_API_KEY=08215bd643f242cc980d542d6453434dbdd01ca4d2464505b0e14d7713b9f8ce
SERVICE_USER_ID=4b6e94b4-661c-4462-9d14-b21df7d51e5b
```

### 2. New Batch-Import Endpoint (CREATED)

**File:** `apps/web/src/app/api/purchases/batch-import/route.ts`

This endpoint was CREATED as part of this consolidation. It provides the same functionality as
`/api/service/purchases/batch-import` but uses `validateAuth` (simple key) instead of `withServiceAuth` (hb_sk_* format).

### 3. Hadley API Update (DONE)

**File:** `hadley_api/main.py`

Changed `/hb/batch-import` to use the new regular endpoint:
```python
# Before (used service endpoint with hb_sk_* key requirement)
return await _hb_service_post("/api/service/purchases/batch-import", data)

# After (uses regular endpoint with simple key)
return await _hb_proxy_post("/api/purchases/batch-import", data)
```

### 4. Verify All HB Endpoints Use validateAuth

**Files to check:**
- `apps/web/src/app/api/inventory/route.ts` ✅ (already updated)
- `apps/web/src/app/api/purchases/route.ts` ✅ (already has validateAuth)
- `apps/web/src/app/api/purchases/batch-import/route.ts` ✅ (newly created with validateAuth)
- `apps/web/src/app/api/brickset/*/route.ts` - verify validateAuth
- `apps/web/src/app/api/reports/*/route.ts` - verify validateAuth
- `apps/web/src/app/api/orders/route.ts` ✅ (already has validateAuth)

---

## Integration Test Plan

### Test Infrastructure

Create test script: `scripts/test_hb_integration.py`

### Test Categories

#### A. Authentication Tests

| Test | Command | Expected |
|------|---------|----------|
| A1. Valid key | `curl -H "x-api-key: $KEY" $URL/hb/dashboard` | 200 OK |
| A2. Invalid key | `curl -H "x-api-key: wrong" $URL/hb/dashboard` | 401 Unauthorized |
| A3. No key | `curl $URL/hb/dashboard` | 401 Unauthorized |

#### B. GET Endpoint Tests

| Test | Endpoint | Expected |
|------|----------|----------|
| B1 | `/hb/dashboard` | JSON with KPIs |
| B2 | `/hb/inventory-status` | JSON with status counts |
| B3 | `/hb/orders` | JSON array of orders |
| B4 | `/hb/tasks` | JSON array of tasks |
| B5 | `/hb/daily-activity` | JSON with activity data |
| B6 | `/hb/pnl` | JSON with P&L data |
| B7 | `/hb/platform-performance` | JSON with platform stats |
| B8 | `/hb/purchase-analysis` | JSON with purchase stats |
| B9 | `/hb/arbitrage-opportunities` | JSON array |
| B10 | `/hb/stock-check` | JSON with stock data |
| B11 | `/hb/inventory-aging` | JSON with aging data |
| B12 | `/hb/pick-list` | JSON array |
| B13 | `/hb/upcoming-pickups` | JSON array |
| B14 | `/hb/lookup-asin?set_number=40448` | JSON with ASIN |
| B15 | `/hb/competitive-pricing?asin=...` | JSON with pricing |
| B16 | `/hb/sets/40448` | JSON with set details |

#### C. POST Endpoint Tests

| Test | Endpoint | Body | Expected |
|------|----------|------|----------|
| C1 | `/hb/purchases` | Purchase JSON | 201 Created |
| C2 | `/hb/inventory` | Inventory JSON | 201 Created |
| C3 | `/hb/batch-import` | Batch JSON | 200 OK with results |
| C4 | `/hb/task-complete` | Task ID | 200 OK |
| C5 | `/hb/schedule-pickup` | Pickup JSON | 200 OK |

#### D. Peter Skill Simulation Tests

| Test | Skill | Steps | Expected |
|------|-------|-------|----------|
| D1 | hb-add-purchase | lookup-asin → competitive-pricing → batch-import | Purchase + Inventory created |
| D2 | hb-add-inventory | lookup-asin → competitive-pricing → inventory POST | Inventory created |
| D3 | hb-eval-purchase | lookup-asin → competitive-pricing | Pricing data returned |
| D4 | hb-dashboard | dashboard GET | KPIs returned |

#### E. End-to-End Flow Tests

| Test | Flow | Verification |
|------|------|--------------|
| E1 | Add purchase via Peter | Check Supabase for new purchase + inventory records |
| E2 | Email batch import | Check records created match input |
| E3 | Task completion | Check task status updated in Supabase |

---

## Execution Checklist

### Phase 1: Sync Keys

- [ ] Update HB `.env.local` `INTERNAL_API_KEY` to match Discord-Messenger key
- [ ] Restart HB dev server (or Vercel redeploy)
- [ ] Verify Hadley API can reach HB: `curl http://172.19.64.1:8100/hb/dashboard`

### Phase 2: Run Auth Tests (A1-A3)

- [ ] A1: Valid key returns 200
- [ ] A2: Invalid key returns 401
- [ ] A3: No key returns 401

### Phase 3: Run GET Tests (B1-B16)

- [ ] All GET endpoints return valid JSON
- [ ] No 401/403 errors
- [ ] No 500 errors

### Phase 4: Run POST Tests (C1-C5)

- [ ] C1: Purchase creation works
- [ ] C2: Inventory creation works
- [ ] C3: Batch import works
- [ ] C4: Task completion works
- [ ] C5: Pickup scheduling works

### Phase 5: Peter Skill Tests (D1-D4)

- [ ] D1: Add purchase skill full flow
- [ ] D2: Add inventory skill full flow
- [ ] D3: Eval purchase returns pricing
- [ ] D4: Dashboard returns KPIs

### Phase 6: E2E Verification

- [ ] E1: Purchase added via Discord shows in Supabase
- [ ] E2: Batch import creates correct records
- [ ] E3: Scheduled job runs without auth errors

---

## Rollback Plan

If issues occur after key sync:

1. Revert HB `.env.local` to previous key
2. Restart HB
3. Investigate logs for specific failure

---

## Success Criteria

**The task is COMPLETE when:**

1. ✅ Single key value used across both systems
2. ✅ All 16 GET endpoints return 200 with valid data
3. ✅ All 5 POST endpoints work correctly
4. ✅ Peter can successfully add a purchase (full flow test)
5. ✅ Peter can successfully add inventory (full flow test)
6. ✅ No auth-related errors in logs for 24 hours

---

## Post-Implementation: Documentation Updates

Update these files to reflect consolidated auth:

1. `hadley_api/README.md` - Document single auth method
2. `domains/peterbot/wsl_config/CLAUDE.md` - Confirm API key usage
3. Remove any references to `hb_sk_*` format or service endpoints
