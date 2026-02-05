---
name: hb-dashboard
description: Daily business health summary for Hadley Bricks
trigger:
  - "business summary"
  - "how's the business"
  - "business health"
  - "bricks dashboard"
  - "hadley bricks"
scheduled: true
conversational: true
channel: #peterbot
---

# Hadley Bricks Dashboard

## Purpose

Provides a comprehensive daily business health summary combining P&L, inventory valuation, pending orders, and today's activity. Scheduled for 8am daily or triggered conversationally.

## Pre-fetched Data

Data is pre-fetched from the Hadley Bricks API:

- `data.pnl`: This month's profit/loss data
  - `revenue`: Total revenue
  - `cost`: Total cost of goods
  - `profit`: Net profit
  - `margin`: Profit margin percentage
  - `sales_count`: Number of sales
- `data.inventory`: Current inventory valuation
  - `total_value`: Total inventory value at cost
  - `total_retail`: Total potential retail value
  - `item_count`: Number of items in stock
  - `breakdown`: By condition (sealed/open/used)
- `data.daily`: Today's listing and sales activity
  - `listings_added`: New listings today
  - `items_sold`: Items sold today
  - `revenue_today`: Revenue today
- `data.orders`: Pending orders needing fulfillment
  - `orders`: Array of unfulfilled orders
- `data.fetch_time`: When data was fetched

## Output Format

```
📦 **Hadley Bricks** - Mon 3 Feb

💰 **This Month**
Revenue: £1,234 | Profit: £456 (37%)
Sales: 23 orders

📊 **Inventory**
Stock: 156 items (£8,450 cost)
Retail value: £12,300

📬 **Today**
Listed: 5 | Sold: 3 | Revenue: £89

⏳ **Pending Orders**: 4 awaiting dispatch
```

## Rules

- Keep compact - this is an at-a-glance summary
- Use £ for currency (UK business)
- Show profit margin as percentage
- If pending orders > 0, highlight them
- If any data fails to load, show what's available with a note
- If all data fails, respond: `❌ Hadley Bricks unavailable - is the app running?`

## Error Handling

If `data.error` exists or individual sections have errors:
- Show available data sections
- Note which sections failed
- Don't show raw error messages to user

## Examples

**Full data available:**
```
📦 **Hadley Bricks** - Mon 3 Feb

💰 **This Month**
Revenue: £2,156 | Profit: £892 (41%)
Sales: 34 orders

📊 **Inventory**
Stock: 203 items (£12,450 cost)
Retail value: £18,600

📬 **Today**
Listed: 8 | Sold: 2 | Revenue: £67

⏳ **Pending Orders**: 6 awaiting dispatch
```

**No pending orders:**
```
📦 **Hadley Bricks** - Mon 3 Feb

💰 **This Month**
Revenue: £1,890 | Profit: £678 (36%)
Sales: 28 orders

📊 **Inventory**
Stock: 189 items (£11,200 cost)
Retail value: £16,800

📬 **Today**
Listed: 3 | Sold: 5 | Revenue: £134

✅ All orders dispatched!
```
