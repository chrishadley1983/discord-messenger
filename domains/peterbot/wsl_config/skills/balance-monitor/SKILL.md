---
name: balance-monitor
description: Check API credit balances and alert if low
trigger:
  - "balance"
  - "credits"
  - "api balance"
scheduled: true
conversational: true
channel: #api-costs
---

# Balance Monitor

## Purpose

Hourly check of API credit balances (7am-9pm UK). Alert if any balance drops below threshold.

## Pre-fetched Data

```json
{
  "claude": {
    "balance": 45.23,  // or null if unavailable
    "current_month_cost": 12.50,  // fallback if balance unavailable
    "error": "string if failed"
  },
  "moonshot": {
    "balance": 12.50,
    "voucher": 5.00,
    "cash": 7.50
  },
  "grok": {
    "balance": null,  // xAI has no billing API
    "note": "Check console.x.ai manually",
    "configured": true
  },
  "threshold": 5.00,
  "timestamp": "2026-01-31 09:00"
}
```

## Output Format

```
💰 **API Balance Check** - 09:00

💳 **Claude:** $45.23
🌙 **Kimi:** $12.50
🤖 **Grok:** Check console.x.ai

All balances healthy ✓
```

If below threshold:
```
💰 **API Balance Check** - 09:00

⚠️ **Claude:** $3.50 (below $5 threshold!)
🌙 **Kimi:** $12.50
🤖 **Grok:** Check console.x.ai

🚨 Claude credits running low - top up soon
```

If Claude balance unavailable but monthly cost is:
```
💳 **Claude:** $12.50 spent this month (balance unavailable)
```

## Rules

- Show Claude, Moonshot (Kimi), and Grok balances
- Use ⚠️ emoji for balances below threshold
- Grok has no billing API - show manual check reminder
- Add alert message at bottom if any balance is low
- If balance unavailable, show error or monthly cost fallback
- Keep it brief - this runs hourly
