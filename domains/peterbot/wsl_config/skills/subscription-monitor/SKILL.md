---
name: subscription-monitor
description: Weekly subscription health check - detect new subs, price changes, missed payments, upcoming renewals
trigger:
  - "subscription check"
  - "sub monitor"
  - "subscription health"
scheduled: true
conversational: true
channel: "#alerts+WhatsApp:chris"
---

# Subscription Monitor

## Purpose

Weekly proactive check of all personal and business subscriptions. Analyses bank transactions to detect changes and issues.

## Pre-fetched Data

```json
{
  "alerts": [
    {
      "type": "price_change",
      "subscription": "Netflix",
      "old_amount": 10.99,
      "new_amount": 12.99,
      "last_transaction_date": "2026-02-15",
      "description": "NETFLIX.COM"
    },
    {
      "type": "missed_payment",
      "subscription": "Spotify",
      "expected_by": "2026-02-28",
      "last_payment_date": "2026-01-15",
      "amount": 10.99
    },
    {
      "type": "new_recurring",
      "description": "SOME NEW SERVICE",
      "avg_amount": 9.99,
      "occurrences": 3,
      "first_seen": "2025-12-01"
    },
    {
      "type": "cancellation_window",
      "subscription": "Disney+",
      "renewal_date": "2026-03-20",
      "cancellation_deadline": "2026-03-06",
      "amount": 7.99,
      "frequency": "monthly"
    }
  ],
  "upcoming_renewals": [
    {
      "name": "Amazon Prime",
      "renewal_date": "2026-03-15",
      "amount": 95.00,
      "frequency": "annual"
    }
  ],
  "summary": {
    "total_active": 42,
    "total_monthly_cost": 450.00,
    "alerts_count": 3,
    "scanned_transactions": 500
  },
  "timestamp": "2026-03-06 09:00"
}
```

## Output Format

If there are alerts:
```
**Subscription Health Check**

**3 alerts found:**

**Price Change** - Netflix went from 10.99 to 12.99/mo (last charge 15 Feb)
**Missed Payment** - Spotify: no payment since 15 Jan (expected by 28 Feb). Cancelled or billing issue?
**New Subscription Detected** - "SOME NEW SERVICE" 9.99/mo (3 charges since Dec). Want me to add it?
**Cancellation Window** - Disney+ (7.99/mo) renews 20 Mar. Cancel by 6 Mar if you don't want it.

**Upcoming renewals (7 days):**
- Amazon Prime: 95.00 annual on 15 Mar

42 active subs | 450/mo total
```

If no alerts:
```
**Subscription Health Check** - All clear

No price changes, missed payments, or new subscriptions detected.

**Upcoming renewals (7 days):**
- None

42 active subs | 450/mo total
```

## Rules

- Lead with alerts - most important info first
- Price changes: show old vs new amount clearly
- Missed payments: include days overdue and suggest possible reasons
- New recurring: show description and ask if Chris wants to add it
- Cancellation windows: only show if within the cancellation notice period
- Upcoming renewals: show next 7 days, highlight annual ones (bigger amounts)
- Keep it concise - this is a weekly digest, not a full report
- Use GBP amounts (no symbol needed, just the number)
- If no alerts at all, keep it very short
- Always end with a link to the dashboard: http://localhost:5000/#/subscriptions
