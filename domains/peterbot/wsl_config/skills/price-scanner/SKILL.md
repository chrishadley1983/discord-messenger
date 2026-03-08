---
name: price-scanner
description: Scan Sainsbury's prices for common proteins and staples, report deals
trigger:
  - "check prices"
  - "what's on offer"
  - "sainsburys deals"
  - "price scan"
  - "any deals"
  - "what's cheap this week"
scheduled: true
conversational: true
channel: "#food-log"
---

# Price Scanner

## Purpose

Scan Sainsbury's prices for common proteins and staples weekly. Report what's on offer so the meal plan generator can prefer cheaper ingredients. Also responds to conversational queries about current deals.

## Pre-fetched Data

Data fetcher: `price-scanner` — pulls cached price data including deals list.

## Workflow

### Scheduled (Monday 06:00 UK)

1. Trigger a fresh scan: `POST http://172.19.64.1:8100/grocery/price-scan`
2. Report deals to #food-log:

```
🏷️ **This Week's Deals at Sainsbury's**

🥩 **Proteins on offer:**
- Chicken Breast 1kg — £5.50 (was £6.50) — "Save £1"
- Prawns 300g — £3.50 — "2 for £6"

🥬 **Staples on offer:**
- Peppers 3-pack — £1.00 — "Price Lock"

💡 I'll factor these into this week's meal plan if you generate one.
```

If no deals: `NO_REPLY` (don't spam with "nothing on offer").

### Conversational

When Chris asks "what's on offer" or "any deals":
1. Check `data` from price-scanner fetcher
2. If cache is older than 7 days, trigger a fresh scan first
3. Present deals in the same format

## Rules

- Only report items that are genuinely on offer (have promotions)
- Don't report items that failed to scan
- Keep it brief — just the deals, not the full price list
- UK English
