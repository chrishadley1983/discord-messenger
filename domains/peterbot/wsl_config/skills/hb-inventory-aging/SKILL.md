---
name: hb-inventory-aging
description: Slow-moving stock alerts and aging analysis
trigger:
  - "slow stock"
  - "aging inventory"
  - "stale items"
  - "old stock"
  - "what's not selling"
  - "inventory aging"
scheduled: false
conversational: true
channel: null
---

# Hadley Bricks Inventory Aging

## Purpose

Identifies slow-moving inventory that may need price adjustments or should be prioritized for sale. Shows items by how long they've been in stock. Conversational only.

## Pre-fetched Data

Data is pre-fetched from the Hadley Bricks API:

- `data.aging_buckets`: Items grouped by age
  - `0_30_days`: { count, value, items }
  - `31_60_days`: { count, value, items }
  - `61_90_days`: { count, value, items }
  - `90_plus_days`: { count, value, items }
- `data.oldest_items`: Top 10 oldest items
  - `set_number`
  - `set_name`
  - `days_in_stock`
  - `cost`
  - `listed_price`
  - `platform`
- `data.total_aged_value`: Value of items 90+ days old
- `data.avg_days_in_stock`: Average days across all inventory
- `data.recommendations`: AI-suggested actions
- `data.error`: Error message if fetch failed

## Output Format

```
📊 **Inventory Aging Report**

**Overview**
Avg days in stock: 45
Items 90+ days old: 23 (£3,450 tied up)

**Age Distribution**
🟢 0-30 days: 89 items (£5,200)
🟡 31-60 days: 56 items (£3,400)
🟠 61-90 days: 31 items (£2,100)
🔴 90+ days: 23 items (£3,450)

**Oldest Stock** (needs attention)
• 10276 Colosseum - 156 days - £449 → Consider price drop
• 75313 AT-AT - 134 days - £349 → Review pricing
• 42115 Lamborghini - 128 days - £279 → High competition

💡 **Recommendation**
Consider 10-15% price reduction on 5 items over 120 days.
Potential to recover £1,200 in tied-up capital.
```

## Rules

- Color code age buckets (green to red)
- Focus attention on 90+ day items
- Show value tied up in old stock
- Provide actionable recommendations
- Suggest specific price adjustments where appropriate
- Calculate opportunity cost of tied-up capital

## Age Thresholds

- 🟢 0-30 days: Fresh stock, no concern
- 🟡 31-60 days: Monitor, normal turnover
- 🟠 61-90 days: Getting stale, review pricing
- 🔴 90+ days: Action needed, consider repricing

## Recommendations Logic

For items 90+ days:
- If priced above market: Suggest price match
- If priced at market: Suggest 10% reduction
- If rare/retiring: Note potential appreciation

## Error Handling

If data fetch fails:
```
📊 **Inventory Aging**

⚠️ Could not fetch aging data - is Hadley Bricks running?
```

If all stock is fresh:
```
📊 **Inventory Aging**

✅ All stock is moving well!

No items over 90 days old.
Average days in stock: 28

Keep up the good turnover!
```

## Examples

**Significant aged stock:**
```
📊 **Inventory Aging Report**

**Overview**
Avg days in stock: 52
Items 90+ days old: 31 (£4,890 tied up) ⚠️

**Age Distribution**
🟢 0-30 days: 78 items (£4,500)
🟡 31-60 days: 45 items (£2,800)
🟠 61-90 days: 35 items (£2,340)
🔴 90+ days: 31 items (£4,890)

**Oldest Stock** (needs attention)
• 10276 Colosseum - 187 days - £449
  Listed at £499, market avg £459 → Drop to £449
• 75313 AT-AT - 156 days - £349
  Listed at £379, market avg £349 → Already competitive
• 42115 Lamborghini - 145 days - £279
  Listed at £299, high competition → Try £269
• 21330 Home Alone - 134 days - £199
  Listed at £229, retiring soon → Hold for appreciation
• 10300 DeLorean - 128 days - £139
  Listed at £149, steady demand → Drop to £139

💡 **Recommendation**
Reprice 3 items (Colosseum, Lambo, DeLorean) for ~15% reduction.
Could recover ~£850 in the next 30 days.
```

**Healthy inventory:**
```
📊 **Inventory Aging**

✅ Inventory health: Good

Avg days in stock: 34
Only 8 items over 90 days (£890)

**Age Distribution**
🟢 0-30 days: 112 items (£6,700)
🟡 31-60 days: 52 items (£3,200)
🟠 61-90 days: 17 items (£1,100)
🔴 90+ days: 8 items (£890)

Stock is turning over nicely. No urgent action needed.
```
