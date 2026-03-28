---
name: life-admin-dashboard
description: Weekly life admin digest with traffic-light dashboard — published to surge.sh
trigger:
  - "life admin dashboard"
  - "life admin overview"
  - "admin status"
scheduled: true
conversational: true
channel: "#peterbot"
---

# Life Admin Dashboard

## Purpose

Weekly comprehensive overview of all life admin obligations. Produces a concise Discord
summary and publishes an interactive HTML dashboard to `hadley-life-admin.surge.sh`.
Runs weekly on Sunday 09:15 UK, and also available conversationally on demand.

## Pre-fetched Data

Data injected by the scheduler via `get_life_admin_dashboard_data()`:

```json
{
  "dashboard": {
    "overdue": [
      {
        "id": "uuid",
        "name": "Boiler service",
        "category": "property",
        "due_date": "2026-03-15",
        "days_overdue": 13,
        "provider": "British Gas",
        "amount": null
      }
    ],
    "due_this_week": [],
    "due_this_month": [
      {
        "id": "uuid",
        "name": "Home insurance",
        "category": "insurance",
        "due_date": "2026-04-12",
        "days_until_due": 15,
        "provider": "Admiral",
        "amount": 342.00
      }
    ],
    "all_clear": [
      {
        "name": "Passport",
        "due_date": "2031-06-15",
        "category": "identity"
      }
    ],
    "snoozed": [],
    "actioned_recently": [
      {
        "name": "Car tax",
        "actioned_date": "2026-03-25",
        "next_due": "2027-04-01"
      }
    ]
  },
  "recent_scans": {
    "count": 7,
    "obligations_created": 2,
    "obligations_updated": 4,
    "last_scan": "2026-03-28"
  },
  "date": "2026-03-28"
}
```

## Discord Output Format

```
**Life Admin Weekly** — w/c 24 Mar 2026

🔴 **Overdue (1)**
• Boiler service — 13 days overdue

🟡 **Due This Month (3)**
• Home insurance — 12 Apr (15 days)
• Car tax — 1 Apr (4 days)
• Domain renewal — 18 Apr (21 days)

🟢 **All Clear (20)**
Passport, driving licence, MOT, car insurance, life insurance...

**Recently Done:** Car tax (25 Mar)

**Email Scanner**: 7 scans this week, 2 new obligations detected, 4 updated

Dashboard: https://hadley-life-admin.surge.sh
```

## Surge Dashboard

Generate an HTML page and deploy to `hadley-life-admin.surge.sh`.

### Deployment Method

Use the Hadley API surge endpoint:

```
POST http://172.19.64.1:8100/deploy/surge
{
  "html": "<full HTML content>",
  "domain": "hadley-life-admin.surge.sh",
  "filename": "index.html"
}
```

If the API is unavailable, fall back to CLI:
```bash
source ~/peterbot/.env
echo '<html>...</html>' > /tmp/life-admin-dash/index.html
surge /tmp/life-admin-dash hadley-life-admin.surge.sh
```

### Dashboard HTML Requirements

The HTML page should include:

- **Traffic light cards** for each obligation:
  - Red: overdue items
  - Amber: due within 30 days
  - Green: more than 30 days away
- **Grouped by category** with collapsible sections
- Each card shows: name, due date, days remaining, provider, amount (if known)
- **Summary bar** at top: total tracked, overdue count, due this month, all clear
- **Recently actioned** section showing completed items
- **Email scanner stats**: scans this week, new/updated counts
- **Mobile-responsive** design (flexbox/grid, works on phone)
- **Clean modern design**: dark header, white cards, subtle shadows
- Colour scheme: navy (#1a2332) header, white (#fff) cards, red/amber/green status badges
- **Static snapshot** — data baked in at generation time (no live API calls from browser)
- Generated timestamp in footer

### HTML Structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Life Admin Dashboard — Hadley Family</title>
  <style>
    /* Inline styles — single file deployment */
    /* Navy header, white cards, traffic light badges */
    /* Mobile-first responsive grid */
  </style>
</head>
<body>
  <!-- Summary bar -->
  <!-- Category sections with obligation cards -->
  <!-- Recently actioned -->
  <!-- Email scanner stats -->
  <!-- Footer with timestamp -->
</body>
</html>
```

## Rules

- Always publish the dashboard, even if no alerts — the all-clear state is useful
- Discord message should be a concise summary, not the full list
- Link to the surge dashboard for full details
- Include email scanner stats for transparency
- Run weekly on Sunday 09:15 UK time
- Also available conversationally ("show me the life admin dashboard")
- Keep Discord message under 2000 chars — the dashboard has the full detail
- Group obligations by category in both Discord and dashboard
- Show "Recently Done" only if items were actioned in the last 7 days
- Always include the dashboard URL at the end of the Discord message
- If surge deployment fails, still send the Discord summary and note the deploy error
- All CSS and JS must be inline (single-file deployment to surge)
