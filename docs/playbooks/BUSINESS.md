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

## Hadley API Endpoints

Base URL: `http://172.19.64.1:8100`

| Query | Endpoint | Method |
|-------|----------|--------|
| P&L report | `/hb/pnl?preset=this_month` or `?start_date=...&end_date=...` | GET |
| Inventory overview | `/hb/inventory` | GET |
| Inventory aging | `/hb/inventory/aging` | GET |
| Daily activity | `/hb/daily?preset=today` or `?date=2026-01-15` | GET |
| Orders | `/hb/orders?status=Paid,Pending` | GET |
| Platform comparison | `/hb/platform?preset=last_month` | GET |
| Purchase ROI analysis | `/hb/purchase-analysis` | GET |
| Set lookup | `/hb/set/{set_number}` | GET |
| Stock check | `/hb/stock/{set_number}` | GET |
| Pick list | `/hb/pick-list` or `?platform=amazon` | GET |
| Arbitrage deals | `/hb/arbitrage?limit=10` | GET |
| Tasks | `/hb/tasks` | GET |
| Upcoming pickups | `/hb/pickups` | GET |
| Calculator | `/calculate?expr=...` | GET |

**HB Presets:** `today`, `yesterday`, `this_week`, `last_week`, `this_month`, `last_month`, `this_year`, `last_year`

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
