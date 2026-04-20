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
    // Shape depends on gcp.source:
    //   "bigquery" — real billing data from GCP BigQuery export (preferred)
    //   "estimates" — fallback from Cloud Monitoring + Supabase token counts
    "configured": true,
    "source": "bigquery",
    "currency": "GBP",
    "month_to_date": {
      "cost_gbp": 1.45,            // if source=bigquery
      "gross_gbp": 2.37,
      "credits_gbp": -0.92,
      "service_breakdown": [
        {"service": "Cloud Scheduler", "cost_gbp": 1.20},
        {"service": "Artifact Registry", "cost_gbp": 0.22}
      ]
      // if source=estimates: has cost_usd, gemini_calls, maps_breakdown instead
    },
    "today_gbp": 0.05,             // bigquery only
    "yesterday_gbp": 0.08,         // bigquery only
    "projected_monthly_gbp": 2.24,
    "days_elapsed": 19.4
  },
  "threshold": 5.00,
  "timestamp": "2026-03-09 07:03"
}
```

## Output Format

**If `gcp.source == "bigquery"` (use £ and service_breakdown):**
```
💰 **API Balance Check** — 12:03

💳 Claude: $8.70
🌙 Kimi: $9.75
🤖 Grok: $5.09
☁️ GCP: £1.45 MTD (proj ~£2.24/mo)
   Cloud Scheduler £1.20, Artifact Registry £0.22

Max (Claude Code): 3% 5h | 43% 7d

All balances healthy ✓
```

**If `gcp.source == "estimates"` (fallback, use $ and maps_breakdown):**
```
☁️ GCP: $4.52 MTD (est, proj ~$19/mo)
   Directions 1200, Places Text Search 85
```

**If GCP not configured:**
```
☁️ GCP: not configured (see setup instructions)
```

## Rules

- Show Claude, Kimi, Grok balances + GCP month-to-date spend
- **Pick GCP currency symbol from `gcp.currency` field** — `£` for GBP (bigquery path), `$` for USD (estimates path)
- For bigquery: show top 2–3 entries from `service_breakdown` with `£{cost_gbp}`
- For estimates: show top entries from `maps_breakdown` with request counts
- Use ⚠️ for balances below $5 threshold OR `gcp.projected_monthly_gbp > 15` OR `gcp.alert: true`
- If `gcp.today_gbp` or `yesterday_gbp` is high (>£1), include it in the line
- If GCP not configured, show setup reminder (not an error)
- Keep it brief — this runs hourly
