---
name: hb-stock-check
description: Check current stock for a specific LEGO set
trigger:
  - "how many"
  - "stock of"
  - "do I have"
  - "in stock"
  - "got any"
  - "check stock"
scheduled: false
conversational: true
channel: null
---

# Hadley Bricks Stock Check

## Purpose

Quickly check how many of a specific set we have in inventory, including conditions, locations, and listing status. Conversational - user provides set number in their message.

## Input Parsing

Extract set number from user message:
- "How many 75192 do I have?"
- "Stock of 10300"
- "Do I have any DeLoreans?"
- "Got any Millennium Falcons?"

For set names, try to match to set number.

## Pre-fetched Data

Data from the Hadley Bricks API:

- `data.set_number`: The set number queried
- `data.set_name`: Set name for display
- `data.in_stock`: Boolean - do we have any
- `data.quantity`: Total count
- `data.items`: Array of inventory items
  - `condition`: Sealed, Open Complete, etc.
  - `location`: Storage location code
  - `cost`: What we paid
  - `listed_price`: Current listing price
  - `platform`: Where listed (or "Unlisted")
  - `days_in_stock`: How long we've had it
  - `sku`: Internal SKU
- `data.total_cost`: Total cost of this set in stock
- `data.total_retail`: Total retail value
- `data.error`: Error message if fetch failed

## Output Format

**Simple stock check:**
```
📦 **10300 DeLorean** - 3 in stock

Sealed: 2 (A3-B2, C1-A1) @ £139 eBay
Open Complete: 1 (B2-C3) @ £109 Amazon

Total cost: £315 | Value: £387
```

**Detailed view (if requested):**
```
📦 **10300 DeLorean** - Stock Details

**In Stock: 3 items**

1. Sealed - Location A3-B2
   Cost: £105 | Listed: £139 (eBay)
   Days in stock: 12 | SKU: DEL-001

2. Sealed - Location C1-A1
   Cost: £110 | Listed: £139 (eBay)
   Days in stock: 8 | SKU: DEL-002

3. Open Complete - Location B2-C3
   Cost: £100 | Listed: £109 (Amazon)
   Days in stock: 23 | SKU: DEL-003

**Summary**
Total cost: £315 | Total value: £387
Avg margin: 23%
```

## Rules

- Lead with the count - that's what they're asking
- Show conditions grouped for quick view
- Include locations for finding items
- Note if any are unlisted
- Keep response concise for quick checks
- Offer detail if multiple items

## Not In Stock Response

```
📦 **75192 Millennium Falcon**

❌ Not currently in stock.

Market price: ~£589 (BrickLink)
💡 Consider adding to arbitrage watchlist.
```

## Error Handling

If set number not found:
```
📦 **Stock Check**

Couldn't find set "99999".
Please provide a valid LEGO set number.
```

If API fails:
```
📦 **Stock Check**

⚠️ Could not check stock - is Hadley Bricks running?
```

## Examples

**Single item:**
```
📦 **75192 Millennium Falcon** - 1 in stock

Sealed - Location A1-A1
Cost: £480 | Listed: £599 (eBay)
Days in stock: 34

Margin: £119 (25%)
```

**Multiple items:**
```
📦 **10300 DeLorean** - 4 in stock

Sealed: 3 @ £139 (2 eBay, 1 Amazon)
Open Complete: 1 @ £109 (eBay)

Locations: A3-B2, C1-A1, C1-A2, B2-C3
Total cost: £420 | Value: £526
```

**Quick yes/no:**
User: "Do I have any Home Alone sets?"
```
📦 **21330 Home Alone**

✅ Yes! 2 in stock (both sealed)
Listed @ £229 on eBay
```

**None in stock:**
User: "How many Colosseum?"
```
📦 **10276 Colosseum**

❌ None in stock.

This set is retired - watch for arbitrage opportunities!
Market value: ~£450-500
```

**With unlisted warning:**
```
📦 **42143 Ferrari Daytona** - 2 in stock

Sealed: 1 @ £349 (eBay)
Sealed: 1 - ⚠️ UNLISTED

Location: D2-C3, D2-C4
Total cost: £580

💡 1 item not listed - potential missed sales!
```
