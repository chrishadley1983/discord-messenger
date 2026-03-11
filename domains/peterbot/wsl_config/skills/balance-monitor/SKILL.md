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
    "balance": 45.23,
    "current_month_cost": 12.50,
    "error": "string if failed"
  },
  "moonshot": {
    "balance": 12.50,
    "voucher": 5.00,
    "cash": 7.50
  },
  "grok": {
    "balance": 5.09,
    "today_cost": 0.12
  },
  "max": {
    "five_hour": {"utilization": 3},
    "seven_day": {"utilization": 43}
  },
  "gcp": {
    "configured": true,
    "cost_so_far_usd": 4.52,
    "projected_monthly_usd": 18.50,
    "projected_monthly_gbp": 14.62,
    "days_elapsed": 7.3,
    "requests_so_far": 2450,
    "top_services": [
      {"name": "Directions", "requests": 1200, "cost": 2.10},
      {"name": "Places Text Search", "requests": 85, "cost": 1.72}
    ]
  },
  "threshold": 5.00,
  "timestamp": "2026-03-09 07:03"
}
```

## Output Format

```
💰 **API Balance Check** — 07:03

💳 Claude: $8.70
🌙 Kimi: $9.75
🤖 Grok: $5.09
☁️ GCP: $4.52 MTD (proj ~$19/mo)
   Directions 1200, Places Text Search 85

Max (Claude Code): 3% 5h | 43% 7d

All balances healthy ✓
```

If GCP projected spend is high (>£20/mo):
```
⚠️ GCP: $12.30 MTD (proj ~$38/mo)
   Places Text Search 450, Directions 2100
...
⚠️ GCP projected $38/mo — review API usage!
```

If GCP not configured:
```
☁️ GCP: not configured (see setup instructions)
```

## Rules

- Show Claude, Kimi, Grok balances + GCP month-to-date spend
- GCP shows cost so far + projected monthly total + top API callers
- Use ⚠️ for balances below $5 threshold OR GCP projected >$20/mo
- If GCP not configured, show setup reminder (not an error)
- Keep it brief — this runs hourly
