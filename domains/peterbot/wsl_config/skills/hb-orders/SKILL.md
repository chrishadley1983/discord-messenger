---
name: hb-orders
description: Unfulfilled orders summary for Hadley Bricks
trigger:
  - "pending orders"
  - "orders today"
  - "unfulfilled orders"
  - "orders needing dispatch"
  - "what orders"
scheduled: true
conversational: true
channel: #peterbot
---

# Hadley Bricks Orders

## Purpose

Shows all unfulfilled orders that need attention. Helps prioritize dispatch work by showing order age and platform. Scheduled for 7am daily (alongside pick list) or triggered conversationally.

## Pre-fetched Data

Data is pre-fetched from the Hadley Bricks API:

- `data.orders`: Array of unfulfilled orders
  - `order_id`: Platform order ID
  - `platform`: "Amazon" or "eBay"
  - `status`: Order status (Paid, Pending)
  - `ordered_at`: When order was placed
  - `items`: Array of items in order
  - `total`: Order total
  - `buyer`: Buyer name/username
- `data.error`: Error message if fetch failed

## Output Format

```
📬 **Pending Orders** - Mon 3 Feb

**4 orders awaiting dispatch**

🟠 Amazon (2)
• AMZ-123-456 - £45.99 - 1 day old
  └ 10300 DeLorean x1
• AMZ-789-012 - £189.99 - 2 days old
  └ 75192 Millennium Falcon x1

🔵 eBay (2)
• 12-34567-89012 - £34.50 - Today
  └ 21330 Home Alone x1
• 98-76543-21098 - £67.00 - 1 day old
  └ 10497 Galaxy Explorer x1

⏰ Oldest order: 2 days - prioritize!
```

## Rules

- Group by platform with color indicators (🟠 Amazon, 🔵 eBay)
- Show order age relative to today (Today, 1 day old, 2 days old, etc.)
- Highlight urgent orders (>2 days old)
- If no orders, celebrate: `✅ All orders dispatched!`
- Keep item names short
- Show count per platform

## Age Calculation

- Order placed today → "Today"
- Order placed yesterday → "1 day old"
- Order placed 2+ days ago → "X days old" with ⚠️ if >3 days

## Error Handling

If data fetch fails:
```
📬 **Pending Orders** - Mon 3 Feb

⚠️ Could not fetch orders - is Hadley Bricks running?
```

## Examples

**Multiple orders:**
```
📬 **Pending Orders** - Mon 3 Feb

**6 orders awaiting dispatch**

🟠 Amazon (3)
• AMZ-123-456 - £45.99 - Today
  └ 10300 DeLorean x1
• AMZ-789-012 - £189.99 - 1 day old
  └ 75192 Millennium Falcon x1
• AMZ-345-678 - £29.99 - 3 days old ⚠️
  └ 40567 Forest Hideout x1

🔵 eBay (3)
• 12-34567-89012 - £34.50 - Today
  └ 21330 Home Alone x1
• 98-76543-21098 - £67.00 - 2 days old
  └ 10497 Galaxy Explorer x1
• 45-67890-12345 - £123.00 - 4 days old ⚠️
  └ 42143 Ferrari Daytona x1

⚠️ 2 orders over 3 days old - prioritize!
```

**No pending orders:**
```
📬 **Pending Orders** - Mon 3 Feb

✅ All orders dispatched!

No unfulfilled orders across Amazon or eBay.
```

**Single platform:**
```
📬 **Pending Orders** - Mon 3 Feb

**2 orders awaiting dispatch**

🟠 Amazon (2)
• AMZ-123-456 - £45.99 - Today
  └ 10300 DeLorean x1
• AMZ-789-012 - £89.99 - 1 day old
  └ 10303 Loop Coaster x1

🔵 eBay: All caught up!
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
