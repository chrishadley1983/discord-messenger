---
name: hb-pnl
description: Profit and loss summary by platform and period
trigger:
  - "profit and loss"
  - "p&l"
  - "pnl"
  - "how much profit"
  - "profit this month"
  - "profit this week"
  - "profit today"
scheduled: false
conversational: true
channel: null
---

# Hadley Bricks P&L Report

## Purpose

Provides profit and loss summary for the business. Can show data for different periods (today, this week, this month, this year). Conversational only - triggered by user asking about profits.

## Pre-fetched Data

Data is pre-fetched from the Hadley Bricks API with default "this_month" preset:

- `data.period`: Time period label (e.g., "This Month", "This Week")
- `data.revenue`: Total revenue
- `data.cost`: Total cost of goods sold
- `data.profit`: Net profit (revenue - cost - fees)
- `data.margin`: Profit margin percentage
- `data.fees`: Platform fees breakdown
  - `ebay_fees`: eBay fees
  - `amazon_fees`: Amazon fees
  - `paypal_fees`: PayPal fees
- `data.sales_count`: Number of sales
- `data.avg_sale_value`: Average sale value
- `data.avg_profit_per_sale`: Average profit per sale
- `data.by_platform`: Breakdown by platform
  - `amazon`: { revenue, profit, sales }
  - `ebay`: { revenue, profit, sales }
- `data.error`: Error message if fetch failed

## Period Interpretation

Parse user request for period:
- "today", "today's" → today
- "this week", "weekly" → this_week
- "this month", "monthly" → this_month (default)
- "this year", "yearly", "ytd" → this_year
- "last month" → last_month
- "last week" → last_week

## Output Format

```
💰 **P&L Report** - This Month

**Summary**
Revenue: £2,456
COGS: £1,234
Fees: £289 (eBay £156, Amazon £89, PayPal £44)
**Profit: £933** (38% margin)

**By Platform**
🟠 Amazon: £1,234 revenue | £456 profit | 23 sales
🔵 eBay: £1,222 revenue | £477 profit | 19 sales

**Averages**
Per sale: £58.48 revenue | £22.21 profit
Total sales: 42
```

## Rules

- Always show the period clearly
- Break down fees by platform
- Show platform comparison
- Calculate and show margin percentage
- Bold the profit line - it's the key metric
- Use £ for all currency
- Round to 2 decimal places for averages

## Conversational Responses

If user asks "how much profit this month":
- Lead with the profit number
- Then provide context

If user asks for comparison:
- Show both periods side by side if possible
- Highlight change (up/down arrows)

## Error Handling

If data fetch fails:
```
💰 **P&L Report**

⚠️ Could not fetch P&L data - is Hadley Bricks running?
```

If period has no data:
```
💰 **P&L Report** - Today

No sales recorded today yet.

Check back later or ask about a different period!
```

## Examples

**Monthly summary:**
```
💰 **P&L Report** - January 2026

**Summary**
Revenue: £4,567
COGS: £2,123
Fees: £534 (eBay £298, Amazon £156, PayPal £80)
**Profit: £1,910** (42% margin)

**By Platform**
🟠 Amazon: £2,345 revenue | £892 profit | 34 sales
🔵 eBay: £2,222 revenue | £1,018 profit | 28 sales

**Averages**
Per sale: £73.66 revenue | £30.81 profit
Total sales: 62
```

**Quick profit check:**
User: "How much profit this week?"
```
💰 **This Week's Profit: £234**

Revenue: £567 | Margin: 41%
12 sales (8 eBay, 4 Amazon)
```

**Today with no sales:**
User: "Profit today?"
```
💰 **Today's P&L**

No sales recorded today yet.

This month so far: £1,234 profit from 28 sales.
```
