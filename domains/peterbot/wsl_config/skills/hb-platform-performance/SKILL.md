---
name: hb-platform-performance
description: Platform comparison and performance metrics
trigger:
  - "platform performance"
  - "best platform"
  - "amazon vs ebay"
  - "ebay vs amazon"
  - "which platform"
  - "platform comparison"
scheduled: false
conversational: true
channel: null
---

# Hadley Bricks Platform Performance

## Purpose

Compares performance between Amazon and eBay to help optimize listing strategy. Shows sales, margins, fees, and sell-through rates by platform. Conversational only.

## Pre-fetched Data

Data is pre-fetched from the Hadley Bricks API with default "this_month" preset:

- `data.period`: Time period for comparison
- `data.amazon`: Amazon metrics
  - `sales_count`
  - `revenue`
  - `profit`
  - `margin`
  - `avg_sale_value`
  - `fees_paid`
  - `fee_percentage`
  - `avg_days_to_sell`
  - `items_listed`
  - `sell_through_rate`
- `data.ebay`: eBay metrics (same structure)
- `data.comparison`: Head-to-head summary
  - `better_margin`: "amazon" or "ebay"
  - `better_volume`: "amazon" or "ebay"
  - `faster_sales`: "amazon" or "ebay"
- `data.recommendations`: Where to list what
- `data.error`: Error message if fetch failed

## Output Format

```
📊 **Platform Performance** - This Month

**Amazon** 🟠
Sales: 34 | Revenue: £2,345
Profit: £892 (38% margin)
Fees: £234 (10%)
Avg days to sell: 12

**eBay** 🔵
Sales: 28 | Revenue: £2,222
Profit: £1,018 (46% margin)
Fees: £189 (8.5%)
Avg days to sell: 18

**Verdict**
🏆 eBay: Higher margins (+8%)
🏆 Amazon: Faster sales (-6 days)
🏆 Amazon: More volume (+6 sales)

💡 List popular sets on Amazon for speed.
List rare/retiring sets on eBay for margin.
```

## Rules

- Show both platforms side by side
- Calculate and compare key metrics
- Declare winners for each category
- Provide actionable recommendations
- Consider fee differences in margin analysis
- Show sell-through rate if available

## Comparison Categories

1. **Margin**: Which platform keeps more profit per sale
2. **Volume**: Which platform sells more units
3. **Speed**: Which platform sells faster
4. **Fees**: Which platform costs less to sell on

## Period Handling

Like P&L, parse user request for period:
- Default to "this_month"
- Support "this week", "this year", "last month"

## Error Handling

If data fetch fails:
```
📊 **Platform Performance**

⚠️ Could not fetch platform data - is Hadley Bricks running?
```

If no sales on a platform:
```
📊 **Platform Performance** - This Month

**Amazon** 🟠
No sales this month

**eBay** 🔵
Sales: 12 | Revenue: £890
Profit: £345 (39% margin)

Consider listing more on Amazon to diversify!
```

## Examples

**Balanced performance:**
```
📊 **Platform Performance** - January 2026

**Amazon** 🟠
Sales: 45 | Revenue: £3,456
Profit: £1,234 (36% margin)
Fees: £345 (10%)
Avg days to sell: 8
Sell-through: 23%

**eBay** 🔵
Sales: 38 | Revenue: £3,122
Profit: £1,456 (47% margin)
Fees: £267 (8.6%)
Avg days to sell: 14
Sell-through: 18%

**Verdict**
🏆 eBay: Higher margins (+11%)
🏆 Amazon: Faster sales (-6 days)
🏆 Amazon: More volume (+7 sales)
🏆 eBay: Lower fees (-1.4%)

💡 **Strategy**
• High-demand sets → Amazon (faster turnover)
• Rare/retiring sets → eBay (better margins)
• Avoid Amazon for low-margin items (<30%)
```

**One platform dominating:**
```
📊 **Platform Performance** - This Week

**Amazon** 🟠
Sales: 2 | Revenue: £189
Profit: £67 (35% margin)

**eBay** 🔵
Sales: 8 | Revenue: £567
Profit: £234 (41% margin)

**Verdict**
eBay dominated this week with 4x the sales.

Consider:
• Reviewing Amazon listing prices
• Checking if Amazon inventory is visible/buyable
• Adding more items to Amazon catalog
```

**Quick comparison:**
User: "Which platform is better?"
```
📊 **This Month's Winner**

🏆 **eBay** leads on profit margin (46% vs 38%)
🏆 **Amazon** leads on sales volume (34 vs 28)

Net: eBay generated £126 more profit this month.
Both platforms are valuable - keep using both!
```
