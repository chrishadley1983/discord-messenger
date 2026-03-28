---
name: life-admin-scan
description: Daily life admin obligation scanner - fires tiered alerts for upcoming deadlines
trigger: []
scheduled: true
conversational: false
channel: "#alerts+WhatsApp:chris"
---

# Life Admin Scan

## Purpose

Daily check of all life admin obligations. Fires alerts based on tiered lead times —
overdue items first, then critical/high/medium/low by days until due. Runs once daily
and records which alert tiers have been sent to prevent duplicate notifications.

## Pre-fetched Data

Data injected by the scheduler via `get_life_admin_scan_data()`:

```json
{
  "alerts": {
    "overdue": [
      {
        "id": "uuid",
        "name": "Boiler service",
        "category": "property",
        "due_date": "2026-03-15",
        "days_overdue": 13,
        "provider": "British Gas",
        "provider_contact": "0333 202 9802",
        "reference_number": null,
        "amount": null
      }
    ],
    "critical": [],
    "high": [
      {
        "id": "uuid",
        "name": "Car MOT VW Polo",
        "category": "vehicle",
        "due_date": "2026-05-15",
        "days_until_due": 48,
        "alert_tier": "high",
        "provider": "Local garage",
        "reference_number": "AB12 CDE",
        "amount": null,
        "already_alerted_tiers": ["low"]
      }
    ],
    "medium": [],
    "low": []
  },
  "summary": {
    "total_active": 24,
    "due_this_week": 1,
    "due_this_month": 3,
    "overdue": 1
  }
}
```

## Output Format

```
**Life Admin** — 28 Mar 2026

🔴 **1 overdue:**
• Boiler service (due 15 Mar) — 13 days overdue. British Gas: 0333 202 9802

🟡 **2 due soon:**
• Car MOT VW Polo (15 May) — 48 days. Book at local garage.
• Home insurance (12 Apr) — 15 days. Admiral HH-123456. Last year: £342

🟢 All clear: Passport (2031), driving licence (2033), TV licence (Apr, auto-renews)

24 tracked | 3 this month | 1 overdue
```

## Post-Delivery Actions

After sending the alert message, record each alert tier that was delivered to prevent
re-sending on subsequent runs:

```
POST http://172.19.64.1:8100/life-admin/alerts/record
{
  "obligation_id": "uuid",
  "alert_tier": "high"
}
```

Call this for every obligation+tier combination included in the message.

## Rules

- Lead with overdue (red), then due soon (amber), then all clear (green)
- Include provider contact info where available
- Include last year's amount for renewals to help comparison shopping
- After delivering, call `POST /life-admin/alerts/record` for each alert tier sent
- `NO_REPLY` if no new alerts to send (all tiers already sent or nothing due)
- Don't repeat alerts that have already been sent at this tier — check `already_alerted_tiers`
- Critical priority items: include action suggestion ("Book NOW", "Renew before X")
- Keep under 2000 chars for Discord
- Use short date format: "15 Mar", "12 Apr"
- Group overdue items together, then due-soon items by urgency
- Summary footer always present with counts

## Examples

### Alerts to send

```
**Life Admin** — 28 Mar 2026

🔴 **1 overdue:**
• Boiler service (due 15 Mar) — 13 days overdue. British Gas: 0333 202 9802

🟡 **2 due soon:**
• Home insurance (12 Apr) — 15 days. Admiral HH-123456. Last year: £342. Renew before 5 Apr.
• Domain renewal hadleybricks.co.uk (18 Apr) — 21 days. 123-reg.

🟢 All clear: Passport (2031), driving licence (2033), car insurance (Sep)

24 tracked | 3 this month | 1 overdue
```

### Nothing new to report

```
NO_REPLY
```
