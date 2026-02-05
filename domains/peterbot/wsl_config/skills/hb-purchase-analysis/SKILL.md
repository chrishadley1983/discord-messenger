---
name: hb-purchase-analysis
description: ROI analysis by purchase source
trigger:
  - "purchase roi"
  - "best sources"
  - "where should I buy"
  - "purchase analysis"
  - "sourcing analysis"
  - "best purchases"
scheduled: false
conversational: true
channel: null
---

# Hadley Bricks Purchase Analysis

## Purpose

Analyzes return on investment by purchase source (Vinted, Facebook Marketplace, retail, trade shows, etc.). Helps optimize sourcing strategy by showing which sources provide best margins and volume. Conversational only.

## Pre-fetched Data

Data is pre-fetched from the Hadley Bricks API with default "this_year" preset:

- `data.period`: Analysis period
- `data.by_source`: Breakdown by purchase source
  - `source_name`: e.g., "Vinted", "Facebook Marketplace", "LEGO Store", "Trade Show"
  - `purchases_count`: Number of purchases
  - `total_spent`: Total amount spent
  - `items_acquired`: Total items bought
  - `avg_cost_per_item`: Average cost per item
  - `items_sold`: Items from this source that sold
  - `revenue_generated`: Revenue from sold items
  - `profit_generated`: Profit from sold items
  - `roi_percentage`: Return on investment
  - `avg_margin`: Average profit margin on sales
  - `avg_days_to_sell`: How fast items from this source sell
- `data.best_source`: Source with highest ROI
- `data.most_volume`: Source with most purchases
- `data.total_spent`: Total spending across all sources
- `data.total_roi`: Overall return on investment
- `data.error`: Error message if fetch failed

## Output Format

```
📊 **Purchase Analysis** - 2026 YTD

**Best Performing Sources**

🥇 **Vinted** - 89% ROI
Spent: £2,345 | Profit: £2,087
45 purchases | Avg margin: 42%
Avg days to sell: 23

🥈 **Facebook Marketplace** - 67% ROI
Spent: £1,890 | Profit: £1,266
28 purchases | Avg margin: 38%
Avg days to sell: 31

🥉 **Trade Shows** - 52% ROI
Spent: £1,234 | Profit: £642
12 purchases | Avg margin: 35%
Avg days to sell: 45

**Other Sources**
LEGO Store: £890 spent | 23% ROI
Retail (Smyths/Argos): £456 spent | 18% ROI

💡 **Insight**
Vinted delivers best ROI - prioritize scanning.
Retail purchases are lowest margin - only buy retiring sets.
```

## Rules

- Rank sources by ROI (return on investment)
- Show top 3 with medals (🥇🥈🥉)
- Include both volume and profitability metrics
- Calculate days to sell to show turnover speed
- Provide actionable insights
- Note which sources to prioritize

## ROI Calculation

ROI = (Profit Generated / Total Spent) × 100

- 50%+ ROI: Excellent source 🟢
- 30-50% ROI: Good source 🟡
- 15-30% ROI: Acceptable 🟠
- <15% ROI: Review strategy 🔴

## Error Handling

If data fetch fails:
```
📊 **Purchase Analysis**

⚠️ Could not fetch purchase data - is Hadley Bricks running?
```

If no purchase data:
```
📊 **Purchase Analysis**

No purchase data recorded yet.

Start logging purchases to track ROI by source!
```

## Examples

**Full analysis:**
```
📊 **Purchase Analysis** - 2026 YTD

**Best Performing Sources**

🥇 **Vinted** - 94% ROI 🟢
Spent: £3,456 on 67 purchases
Profit generated: £3,249
Items: 89 acquired → 72 sold
Avg margin: 44% | Sells in 21 days

🥈 **Facebook Marketplace** - 71% ROI 🟢
Spent: £2,345 on 34 purchases
Profit generated: £1,665
Items: 45 acquired → 38 sold
Avg margin: 39% | Sells in 28 days

🥉 **eBay (buying)** - 58% ROI 🟢
Spent: £1,234 on 23 purchases
Profit generated: £716
Items: 28 acquired → 24 sold
Avg margin: 36% | Sells in 32 days

**Other Sources**
Trade Shows: £890 spent | 45% ROI 🟡
LEGO Store: £567 spent | 28% ROI 🟠
Smyths/Argos: £345 spent | 15% ROI 🔴

**Summary**
Total invested: £8,837
Total profit generated: £6,523
Overall ROI: 74%

💡 **Recommendations**
• Vinted is your cash cow - increase scanning time
• Avoid retail unless retiring (15% ROI isn't worth capital lock-up)
• Facebook Marketplace solid but slower turnover
```

**Quick source question:**
User: "Where should I buy LEGO?"
```
📊 **Best Sources by ROI** (2026)

1. **Vinted** - 94% ROI (fastest turnaround)
2. **Facebook Marketplace** - 71% ROI
3. **eBay buying** - 58% ROI

Avoid retail stores unless sets are retiring - only 15-28% ROI.

Your best bet: Keep scanning Vinted for arbitrage opportunities!
```

**Comparing specific sources:**
User: "Vinted vs Facebook Marketplace?"
```
📊 **Source Comparison**

**Vinted** 🥇
ROI: 94% | Margin: 44%
Sells in: 21 days avg
Why: Better arbitrage finds, lower purchase prices

**Facebook Marketplace** 🥈
ROI: 71% | Margin: 39%
Sells in: 28 days avg
Why: Larger lots, but more negotiation needed

**Verdict**: Vinted wins on ROI and speed.
Use FB Marketplace for bulk/lot purchases.
```
