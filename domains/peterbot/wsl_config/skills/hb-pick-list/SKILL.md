---
name: hb-pick-list
description: Amazon, eBay and Shopify picking lists for order fulfillment
trigger:
  - "picking list"
  - "pick list"
  - "what needs shipping"
  - "what needs picking"
  - "orders to ship"
scheduled: true
conversational: true
channel: #peterbot
---

# Hadley Bricks Pick List

## Purpose

Generates consolidated picking lists for Amazon, eBay and Shopify orders. Shows items that need to be picked from inventory for shipping. Scheduled for 7am daily or triggered conversationally.

## Data Source — EXACT ENDPOINTS, DO NOT GUESS

If pre-fetched data is missing or errored, fetch it yourself from these EXACT paths
(via the HB proxy, base `http://172.19.64.1:8100`):

- `GET /hb/picking-list/amazon?format=json`
- `GET /hb/picking-list/ebay?format=json`
- `GET /hb/picking-list/shopify?format=json`

The path is `picking-list` (NOT `pick-list`, `picklist`, or `pick`), and the platform
segment is REQUIRED. Never substitute `/hb/orders` for the pick list — orders data has
no storage locations, and reporting "no location" from it is wrong: the picking-list
endpoint is what performs the inventory match and returns the real locations.

## Pre-fetched Data

Data is pre-fetched from the Hadley Bricks API (same shape as the endpoint responses):

- `data.amazon`: Amazon picking list
  - `items`: Array of items to pick
    - `setNo`: LEGO set number
    - `asin`: Amazon ASIN
    - `itemName`: Item name
    - `quantity`: Quantity to pick
    - `location`: Storage location (null = matched but no location recorded)
    - `matchStatus`: `matched` or `unmatched` (unmatched = no inventory match found)
    - `amazonOrderId`: Amazon order ID
  - `unmatchedItems` / `unknownLocationItems`: subsets needing a warning
  - `totalItems`, `totalOrders`, `pickUrl`
- `data.ebay`: eBay picking list (similar structure; `location` per item)
- `data.shopify`: Shopify picking list (similar structure); extra fields per item:
  - `sku`: inventory SKU (use when `setNo` is null)
  - `orderName`: human order number like `#1011` — show this as the order reference
  - Shopify rows are one per unit (`quantity` 1 each); combine duplicates as usual
- `data.fetch_time`: When data was fetched

## Output Format

```
📋 **Pick List** - Mon 3 Feb

**Amazon** (3 items)
• 75192 Millennium Falcon x1 → A3-B2
• 10300 DeLorean x2 → C1-A1
• 42143 Ferrari Daytona → D2-C3

**eBay** (2 items)
• 10497 Galaxy Explorer x1 → A1-B4
• 21330 Home Alone x1 → B2-A1

**Shopify** (2 items)
• 43273 Frozen Advent Calendar x1 → Loft - S72
• 75358 Tenoo Jedi Temple x1 → Loft - S54

Total: 7 items to pick
```

## Rules

- Group by platform (Amazon first, then eBay, then Shopify)
- Show location codes for easy picking
- Combine duplicates with quantity
- Keep set names short if needed
- If no items to pick, celebrate: `✅ All caught up! No items to pick.`
- Show total count at bottom

## Error Handling

If a platform fails:
```
📋 **Pick List** - Mon 3 Feb

**Amazon** (3 items)
• 75192 Millennium Falcon x1 → A3-B2
...

**eBay**: ⚠️ Data unavailable

Total: 3 items (Amazon only)
```

## Examples

**Both platforms have items:**
```
📋 **Pick List** - Mon 3 Feb

**Amazon** (4 items)
• 75192 Millennium Falcon x1 → A3-B2
• 10300 DeLorean x2 → C1-A1
• 42143 Ferrari Daytona x1 → D2-C3

**eBay** (2 items)
• 10497 Galaxy Explorer x1 → A1-B4
• 21330 Home Alone x1 → B2-A1

Total: 6 items to pick
```

**No items to pick:**
```
📋 **Pick List** - Mon 3 Feb

✅ All caught up! No items to pick.

All Amazon, eBay and Shopify orders are fulfilled.
```

**Only Amazon:**
```
📋 **Pick List** - Mon 3 Feb

**Amazon** (2 items)
• 10300 DeLorean x1 → C1-A1
• 42143 Ferrari Daytona x1 → D2-C3

**eBay**: No items

Total: 2 items to pick
```

## Missing / just-placed order?

The pick list and `/hb/orders` only show what has already been imported. If an
order Chris mentions is missing, trigger the import and re-fetch — never guess
other endpoint names (see `docs/playbooks/BUSINESS.md` → "Missing order?"):

```
POST http://172.19.64.1:8100/hb/sync/trigger      → 202 {accepted: true}
sleep 180
GET  http://172.19.64.1:8100/hb/sync/status       → running:false, ok:true
GET  http://172.19.64.1:8100/hb/picking-list/amazon?format=json
```

`/hb/orders/refresh`, `/hb/orders/sync`, `/hb/workflow/sync-all` and `/hb/cron/*`
are NOT valid — they 401/404/504.
