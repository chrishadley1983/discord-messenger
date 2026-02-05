---
name: hb-inventory-status
description: Inventory valuation and breakdown
trigger:
  - "inventory status"
  - "stock value"
  - "inventory value"
  - "what's in stock"
  - "inventory breakdown"
scheduled: false
conversational: true
channel: null
---

# Hadley Bricks Inventory Status

## Purpose

Shows current inventory valuation with breakdown by condition, platform listing status, and storage locations. Conversational only - triggered by user asking about inventory.

## Pre-fetched Data

Data is pre-fetched from the Hadley Bricks API:

- `data.total_items`: Total number of inventory items
- `data.total_cost`: Total cost basis of inventory
- `data.total_retail`: Estimated retail value
- `data.potential_profit`: Estimated profit if all sold
- `data.by_condition`: Breakdown by condition
  - `sealed`: { count, cost, retail }
  - `open_complete`: { count, cost, retail }
  - `open_incomplete`: { count, cost, retail }
  - `used`: { count, cost, retail }
- `data.by_platform`: Listing status by platform
  - `ebay_listed`: count
  - `amazon_listed`: count
  - `unlisted`: count
- `data.by_location`: Items per storage location
- `data.top_value_items`: Top 5 highest value items
  - `set_number`
  - `set_name`
  - `cost`
  - `retail_value`
- `data.error`: Error message if fetch failed

## Output Format

```
📦 **Inventory Status**

**Overview**
Items: 203 | Cost: £12,450 | Retail: £18,600
Potential profit: £6,150 (49% markup)

**By Condition**
Sealed: 156 items (£9,200 cost)
Open Complete: 34 items (£2,100 cost)
Open Incomplete: 8 items (£450 cost)
Used: 5 items (£700 cost)

**Listing Status**
🔵 eBay: 145 listed
🟠 Amazon: 98 listed
⬜ Unlisted: 23 items

**Top Value Items**
1. 75192 Millennium Falcon - £649 retail
2. 10300 DeLorean - £149 retail
3. 42143 Ferrari Daytona - £369 retail
```

## Rules

- Lead with the key numbers (count, cost, value)
- Show condition breakdown - condition affects pricing
- Highlight unlisted items (potential revenue not being captured)
- Show top value items for context
- Use £ for all currency values
- Calculate markup percentage

## Quick Responses

For simple queries like "how many items in stock":
```
📦 203 items in stock

Cost basis: £12,450
Retail value: £18,600
```

For "what's my stock worth":
```
📦 Inventory Value

Cost: £12,450
Retail: £18,600
Potential profit: £6,150 (49% markup)
```

## Error Handling

If data fetch fails:
```
📦 **Inventory Status**

⚠️ Could not fetch inventory data - is Hadley Bricks running?
```

## Examples

**Full status:**
```
📦 **Inventory Status**

**Overview**
Items: 189 | Cost: £11,234 | Retail: £16,890
Potential profit: £5,656 (50% markup)

**By Condition**
Sealed: 142 items (£8,900 cost)
Open Complete: 28 items (£1,534 cost)
Open Incomplete: 12 items (£500 cost)
Used: 7 items (£300 cost)

**Listing Status**
🔵 eBay: 134 listed
🟠 Amazon: 89 listed
⬜ Unlisted: 18 items (£1,200 value)

**Top Value Items**
1. 75192 Millennium Falcon - £649 retail
2. 10276 Colosseum - £549 retail
3. 42143 Ferrari Daytona - £369 retail
4. 10300 DeLorean - £149 retail
5. 21330 Home Alone - £239 retail
```

**Highlighting unlisted items:**
```
📦 **Inventory Status**

Items: 189 | Cost: £11,234 | Retail: £16,890

⚠️ **18 items unlisted** worth £1,200 retail
Consider listing these to capture potential sales!

🔵 eBay: 134 listed
🟠 Amazon: 89 listed
```
