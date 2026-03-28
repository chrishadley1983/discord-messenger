---
name: life-admin-email-scan
description: Overnight Gmail scan for new life admin obligations - detects renewals, policy docs, bills
trigger: []
scheduled: true
conversational: false
channel: "#peter-heartbeat!quiet"
---

# Life Admin Email Scan

## Purpose

Scan Gmail overnight for emails containing obligation-relevant information. Extract dates,
amounts, reference numbers. Create new obligations or update existing ones. Runs unattended
and logs results for transparency.

## Pre-fetched Data

Data injected by the scheduler via `get_life_admin_email_scan_data()`:

```json
{
  "email_results": {
    "insurance": [
      {
        "subject": "Your home insurance renewal",
        "from": "noreply@admiral.com",
        "date": "2026-03-27",
        "snippet": "Your policy HH-123456 renews on 12 April 2026 for £358.00",
        "body_text": "..."
      }
    ],
    "dvla": [],
    "mot_service": [],
    "council": [],
    "utility": [],
    "passport": [],
    "domain": [],
    "school": [],
    "warranty": []
  },
  "existing_obligations": [
    {
      "id": "uuid",
      "name": "Home insurance",
      "category": "insurance",
      "provider": "Admiral",
      "reference_number": "HH-123456",
      "due_date": "2026-04-12",
      "amount": 342.00
    }
  ]
}
```

## Workflow

1. For each email in `email_results`, extract: obligation name, due date, amount, reference number, provider
2. Match against `existing_obligations` by provider + category
3. **If matched**: update the existing obligation via `PATCH http://172.19.64.1:8100/life-admin/obligations/{id}`:
   ```json
   {
     "amount": 358.00,
     "due_date": "2026-04-12",
     "reference_number": "HH-123456"
   }
   ```
4. **If new**: create via `POST http://172.19.64.1:8100/life-admin/obligations`:
   ```json
   {
     "name": "Home insurance",
     "category": "insurance",
     "provider": "Admiral",
     "reference_number": "HH-123456",
     "due_date": "2026-04-12",
     "amount": 358.00,
     "recurrence": "annual",
     "alert_lead_days": [30, 14, 7, 3],
     "alert_priority": "high"
   }
   ```
5. Record the scan: `POST http://172.19.64.1:8100/life-admin/scans`:
   ```json
   {
     "scan_type": "email",
     "emails_scanned": 12,
     "obligations_created": 1,
     "obligations_updated": 2,
     "details": "Insurance: 1 updated (Admiral amount £342->£358). Domain: 1 new (123-reg, hadleybricks.co.uk)"
   }
   ```

## Default alert_lead_days by Category

| Category | Lead Days |
|----------|-----------|
| identity | [180, 90, 30, 14, 7] |
| vehicle | [28, 14, 7, 3] |
| insurance | [30, 14, 7, 3] |
| tax | [90, 30, 14, 7, 3] |
| property | [30, 14, 7, 3] |
| children | [14, 7, 3] |
| domain | [30, 14, 7] |
| utility | [30, 14, 7] |
| appliance | [30, 14] |

## Default alert_priority by Category

| Category | Priority |
|----------|----------|
| identity, tax | critical |
| vehicle, insurance | high |
| property, children, domain | medium |
| utility, appliance | low |

## Output Format

Brief summary of what was found/updated:

```
**Email Scan** — 28 Mar 2026

3 relevant emails found:
• **Updated**: Home insurance (Admiral) — amount changed £342 -> £358, due 12 Apr
• **New**: Domain renewal hadleybricks.co.uk — 123-reg, due 18 Apr, £12.99/yr
• **Skipped**: Council tax email — no actionable date found

Scan complete: 42 emails checked, 1 new obligation, 1 updated
```

If nothing found:

```
NO_REPLY
```

## Rules

- Be conservative — only create obligations when confident about the extraction
- For ambiguous emails, log in scan details but don't create obligations
- Never duplicate an existing obligation — always match by provider + category first
- Use the Hadley API base URL `http://172.19.64.1:8100`
- When updating, only change fields where the email provides new/different information
- For recurring obligations, infer recurrence from context (insurance = annual, utility = monthly, etc.)
- Log every email processed in the scan record, even skipped ones
- `NO_REPLY` if no relevant emails found in any category
- Keep Discord output concise — full details go in the scan record

## Examples

### Emails found and processed

```
**Email Scan** — 28 Mar 2026

3 relevant emails found:
• **Updated**: Home insurance (Admiral) — amount changed £342 -> £358, due 12 Apr
• **Updated**: Car MOT reminder (DVLA) — confirmed due 15 May
• **New**: Boiler warranty (British Gas) — expires 1 Sep 2026, £0 (covered)

Scan complete: 38 emails checked, 1 new obligation, 2 updated
```

### Nothing relevant

```
NO_REPLY
```
