# Business Playbook

READ THIS for any Hadley Bricks business query — orders, inventory, listings, P&L.

## Data Sources — ALWAYS FETCH, NEVER HARDCODE

- Listing targets: Supabase `business_targets` table (eBay count, Amazon count, margin %)
- Order data: hb-* skills (pre-fetched) or /hadley/orders
- Inventory: /hadley/inventory or hb-inventory skill
- Revenue/P&L: /hadley/financials or hb-dashboard skill
- Platform health: /hadley/platform-status

IMPORTANT: Listing targets, margin targets, and platform mix all change.
Always fetch current targets from business_targets before comparing.

## The Interpretation Layer

THIS IS THE KEY DIFFERENCE. Chris doesn't need Peter to read numbers back to him.
He needs Peter to tell him what the numbers MEAN.

### Always Add:
- **Comparison**: vs target (from business_targets), vs last week/month
- **Trend direction**: improving, declining, flat
- **Anomalies**: anything unusual that needs attention
- **Action items**: what to do about it

### Example — Bad vs Good

❌ "You have 112 orders this week and revenue of £1,247."

✅ "📈 Strong week — £1,247 revenue (+18% vs last week). Amazon driving
growth this week. Margin at 42% against [target from business_targets].
12 items over 90 days — consider repricing."

## Dashboard Interpretation

When hb-dashboard fires or Chris asks "how's business":
1. Fetch current targets from business_targets
2. Lead with verdict: good/bad/steady relative to targets
3. Revenue + comparison to target and last period
4. Orders + platform split
5. Margin trend vs target
6. Inventory health (aging, stock levels vs targets)
7. Any operational issues (pending orders, returns)
8. Suggested actions

## Inventory Queries

"What's slow moving?" / "Aging inventory":
- Pull from hb-inventory-aging or Supabase
- Categorize: 60-90 days (⚠️ watch), 90-180 (🔴 reprice), 180+ (❌ consider clearing)
- Suggest specific actions: reprice %, bundle, auction, clear to BrickLink

## Platform Comparison

"How's Amazon vs eBay?":
- Revenue, orders, margin per platform
- Listing count vs targets (fetch from business_targets)
- Growth trend per platform
- Where to focus effort

## P&L and Financial

Use REPORTS.md format with business-specific additions:
- Revenue, COGS, gross profit, margin %
- Fee breakdown by platform
- Comparison to previous period AND to targets
- Projected month-end based on current run rate

## Things to Flag Proactively

When processing business data, flag if you notice:
- Pending orders aging beyond fulfilment SLA
- Stock of any set dropping to last unit
- Return rate increasing vs previous period
- Margin on a platform dropping below target (from business_targets)
- Listing count below target (from business_targets)

---

## Hadley API — HB Proxy Endpoints

Base URL: `http://172.19.64.1:8100`

All `/hb/*` endpoints proxy to the Hadley Bricks app (localhost:3000/api/*).
Auth is handled automatically — just call the endpoints.

### Read Endpoints

| Query | Endpoint | Method | Key Params |
|-------|----------|--------|------------|
| Orders | `/hb/orders` | GET | `page`, `pageSize`, `platform`, `status`, `startDate`, `endDate` |
| Order stats | `/hb/orders/stats` | GET | `platform` |
| Order status summary | `/hb/orders/status-summary` | GET | `platform`, `days` (7/30/90/all) |
| eBay orders | `/hb/orders/ebay` | GET | |
| Amazon orders | `/hb/orders/amazon` | GET | |
| Dispatch deadlines | `/hb/orders/dispatch-deadlines` | GET | |
| Inventory | `/hb/inventory` | GET | `page`, `pageSize`, `status`, `condition`, `platform`, `search`, cost/date ranges |
| Inventory summary | `/hb/inventory/summary` | GET | `excludeSold`, `platform` |
| Inventory listing counts | `/hb/inventory/listing-counts` | GET | |
| Purchases | `/hb/purchases` | GET | `page`, `pageSize`, `source`, `dateFrom`, `dateTo`, `search` |
| Purchase search | `/hb/purchases/search` | GET | |
| P&L report | `/hb/reports/profit-loss` | GET | `preset` or `startDate`+`endDate` |
| Daily activity | `/hb/reports/daily-activity` | GET | `preset`, `granularity` (daily/monthly) |
| Inventory aging | `/hb/reports/inventory-aging` | GET | |
| Inventory valuation | `/hb/reports/inventory-valuation` | GET | `condition`, `category` |
| Purchase ROI | `/hb/reports/purchase-analysis` | GET | |
| Pick list (eBay) | `/hb/picking-list/ebay` | GET | `format` (json/pdf) |
| Pick list (Amazon) | `/hb/picking-list/amazon` | GET | `format` (json/pdf) |
| Set lookup | `/hb/brickset/lookup?query={set_number}` | GET | |
| Set pricing | `/hb/brickset/pricing?setNumber={num}` | GET | |
| Stock check | `/hb/brickset/inventory-stock?setNumber={num}` | GET | |
| Arbitrage deals | `/hb/arbitrage` | GET | |
| Arbitrage summary | `/hb/arbitrage/summary` | GET | |
| Tasks today | `/hb/workflow/tasks/today` | GET | |
| Upcoming pickups | `/hb/pickups/upcoming` | GET | |

### Write Endpoints

| Action | Endpoint | Method | Body |
|--------|----------|--------|------|
| Add purchase | `/hb/purchases` | POST | `{purchase_date, short_description, cost, source?, payment_method?}` |
| Add inventory item | `/hb/inventory` | POST | `{set_number, item_name?, condition?, cost?, purchase_id?, storage_location?}` |
| Bulk add inventory | `/hb/service/inventory` | POST | `{items: [{set_number, name, condition, cost, purchase_id, ...}]}` |
| Service add purchase | `/hb/service/purchases` | POST | `{source, cost, payment_method, purchase_date, ...}` |
| Update order status | `/hb/orders/{id}/status` | POST | `{status}` |

### Presets (for report endpoints)

`today`, `yesterday`, `this_week`, `last_week`, `this_month`, `last_month`, `this_quarter`, `last_quarter`, `this_year`, `last_year`, `last_30_days`, `last_90_days`, `custom` (with startDate+endDate)

## HB Skills Reference

| Skill | Triggers | Purpose |
|-------|----------|---------|
| `hb-dashboard` | "business summary", "how's the business" | Daily P&L, inventory, orders overview |
| `hb-pick-list` | "picking list", "what needs shipping" | Amazon/eBay items to pick |
| `hb-orders` | "pending orders", "orders today" | Unfulfilled orders |
| `hb-daily-activity` | "what did I list today" | Listings and sales tracking |
| `hb-arbitrage` | "arbitrage deals", "buying opportunities" | Vinted profit opportunities |
| `hb-pnl` | "profit and loss", "p&l" | P&L by period |
| `hb-inventory-status` | "inventory status", "stock value" | Inventory valuation |
| `hb-inventory-aging` | "slow stock", "aging inventory" | Slow-moving items |
| `hb-platform-performance` | "platform performance", "amazon vs ebay" | Platform comparison |
| `hb-purchase-analysis` | "purchase roi", "best sources" | ROI by purchase source |
| `hb-set-lookup` | "look up 75192", "price check" | LEGO set info and pricing |
| `hb-stock-check` | "how many 75192", "do I have" | Check stock for a set |
| `hb-tasks` | "tasks today", "what needs doing" | Workflow tasks |

**Note:** Skills pre-fetch current month data. Use direct API endpoints for custom date ranges.

## Data Sources

- **Listing targets, margin targets**: Supabase `business_targets` table
