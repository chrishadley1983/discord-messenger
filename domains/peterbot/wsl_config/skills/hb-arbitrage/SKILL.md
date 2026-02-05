---
name: hb-arbitrage
description: Profitable LEGO buying opportunities from Vinted scanner
trigger:
  - "arbitrage deals"
  - "buying opportunities"
  - "arbitrage"
  - "vinted deals"
  - "what should I buy"
scheduled: true
conversational: true
channel: #peterbot
---

# Hadley Bricks Arbitrage

## Purpose

Shows profitable buying opportunities from the Vinted scanner. These are LEGO sets being sold below market value that could be purchased for resale. Scheduled for 9am daily or triggered conversationally.

## Pre-fetched Data

Data is pre-fetched from the Hadley Bricks API:

- `data.opportunities`: Array of arbitrage opportunities
  - `set_number`: LEGO set number
  - `set_name`: Set name
  - `asking_price`: Vinted listing price
  - `market_value`: Estimated market value
  - `potential_profit`: Estimated profit after fees
  - `profit_margin`: Profit margin percentage
  - `condition`: Item condition
  - `url`: Link to Vinted listing
  - `found_at`: When opportunity was found
- `data.summary`: Summary stats
  - `total_opportunities`: Total opportunities found
  - `avg_profit_margin`: Average profit margin
  - `total_potential_profit`: Sum of potential profits
- `data.fetch_time`: When data was fetched
- `data.error`: Error message if fetch failed

## Output Format

```
🎯 **Arbitrage Opportunities** - Mon 3 Feb

**Top Deals** (showing 5 of 12)

1. **75192 Millennium Falcon**
   Ask: £450 | Value: £620 | Profit: ~£120 (27%)
   Condition: Sealed | [View](url)

2. **10300 DeLorean**
   Ask: £95 | Value: £140 | Profit: ~£30 (32%)
   Condition: NISB | [View](url)

3. **42143 Ferrari Daytona**
   Ask: £280 | Value: £380 | Profit: ~£65 (23%)
   Condition: Sealed | [View](url)

📊 **Summary**
12 opportunities | Avg margin: 28%
Total potential profit: ~£430
```

## Rules

- Show top 5-7 opportunities by profit margin
- Always include Vinted link for quick access
- Show condition clearly (Sealed, NISB, Open, Used)
- Profit estimates include approximate platform fees
- Use ~ to indicate estimates
- Sort by profit margin (highest first)
- Include summary stats at bottom

## Profit Thresholds

Only show opportunities meeting these criteria:
- Minimum £15 potential profit
- Minimum 20% profit margin

## Urgency Indicators

- Found <1 hour ago: "🔥 Hot deal!"
- Found 1-6 hours ago: Normal
- Found >6 hours ago: May be gone

## Error Handling

If data fetch fails:
```
🎯 **Arbitrage Opportunities** - Mon 3 Feb

⚠️ Could not fetch opportunities - is Hadley Bricks running?
```

If no opportunities:
```
🎯 **Arbitrage Opportunities** - Mon 3 Feb

No profitable opportunities found right now.

The scanner is running - deals will appear when found!
```

## Examples

**Good opportunities:**
```
🎯 **Arbitrage Opportunities** - Mon 3 Feb

**Top Deals** (showing 5 of 8)

1. **75192 Millennium Falcon** 🔥 Hot deal!
   Ask: £450 | Value: £620 | Profit: ~£120 (27%)
   Sealed | [View](https://vinted.co.uk/...)

2. **10300 DeLorean**
   Ask: £95 | Value: £140 | Profit: ~£30 (32%)
   NISB | [View](https://vinted.co.uk/...)

3. **42143 Ferrari Daytona**
   Ask: £280 | Value: £380 | Profit: ~£65 (23%)
   Sealed | [View](https://vinted.co.uk/...)

4. **10497 Galaxy Explorer**
   Ask: £65 | Value: £95 | Profit: ~£20 (31%)
   Sealed | [View](https://vinted.co.uk/...)

5. **21330 Home Alone**
   Ask: £180 | Value: £240 | Profit: ~£40 (22%)
   NISB | [View](https://vinted.co.uk/...)

📊 **Summary**
8 opportunities | Avg margin: 26%
Total potential profit: ~£340
```

**Few opportunities:**
```
🎯 **Arbitrage Opportunities** - Mon 3 Feb

**Today's Deals** (2 found)

1. **10300 DeLorean** 🔥 Hot deal!
   Ask: £90 | Value: £140 | Profit: ~£35 (39%)
   Sealed | [View](https://vinted.co.uk/...)

2. **42143 Ferrari Daytona**
   Ask: £290 | Value: £380 | Profit: ~£55 (19%)
   NISB | [View](https://vinted.co.uk/...)

📊 Light day - scanner watching for more deals
```
