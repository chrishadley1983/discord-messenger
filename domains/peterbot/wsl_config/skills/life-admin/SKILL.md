---
name: life-admin
description: Query, manage, and update life admin obligations conversationally
trigger:
  - "life admin"
  - "upcoming deadlines"
  - "what's due"
  - "when does my MOT expire"
  - "when does my passport expire"
  - "insurance renewal"
  - "what needs renewing"
  - "obligations"
  - "mark as done"
  - "snooze"
  - "add obligation"
scheduled: false
conversational: true
channel: "#peterbot"
---

# Life Admin

## Purpose

Let Chris query and manage life admin obligations through natural conversation.
Supports querying, adding, actioning, snoozing, and searching obligations via
the Hadley API.

## API Endpoints

Use the Hadley API at `http://172.19.64.1:8100`:

- `GET /life-admin/obligations?status=active` — List all active obligations
- `GET /life-admin/obligations?category=vehicle` — Filter by category
- `GET /life-admin/obligations?search=MOT` — Search by keyword
- `POST /life-admin/obligations` — Create new obligation
- `PATCH /life-admin/obligations/{id}` — Update obligation fields
- `POST /life-admin/obligations/{id}/action` — Mark as done (auto-advances recurrence)
- `POST /life-admin/obligations/{id}/snooze` — Snooze until a given date
- `DELETE /life-admin/obligations/{id}` — Remove obligation
- `GET /life-admin/dashboard` — Overview with counts and groupings

### Categories

`vehicle`, `insurance`, `tax`, `property`, `health`, `children`, `identity`,
`subscription`, `utility`, `domain`, `appliance`, `other`

## Workflows

### Querying

"What's due this month?" / "Show me life admin"

1. Call `GET /life-admin/dashboard`
2. Filter by relevant time period
3. Format as grouped bullet list with dates and days remaining

### Adding

"Add a new obligation" / "Track my car MOT"

1. Parse what Chris has said — extract: name, category, due date, recurrence, provider, reference
2. Ask for any missing required fields (name, category, due_date at minimum)
3. **ALWAYS confirm before creating** — show what you understood:
   ```
   I'll add this obligation:
   - **Name:** Car MOT VW Polo
   - **Category:** vehicle
   - **Due:** 15 May 2026
   - **Recurrence:** annual
   - **Provider:** Local garage
   - **Reg:** AB12 CDE

   Shall I go ahead?
   ```
4. Only after Chris confirms → call `POST /life-admin/obligations`
5. Confirm creation with next alert date

### Actioning

"MOT is done" / "Mark boiler service as complete"

1. Search obligations by keyword to find the match
2. If ambiguous, list matches and ask Chris to clarify
3. Call `POST /life-admin/obligations/{id}/action`
4. Confirm: "Marked MOT as done. Next one due 15 May 2027."

### Snoozing

"Snooze boiler for 2 weeks" / "Push back home insurance to next month"

1. Find the obligation by keyword
2. Parse the snooze duration or target date
3. Call `POST /life-admin/obligations/{id}/snooze` with `{"snooze_until": "2026-04-11"}`
4. Confirm: "Snoozed boiler service until 11 Apr. Alerts will resume then."

### Searching

"When does my passport expire?" / "What's the reference for my car insurance?"

1. Call `GET /life-admin/obligations?search=passport`
2. Return the match with due date, days remaining, provider, and reference number
3. If no match: "I don't have a passport obligation tracked. Want me to add one?"

### Deleting

"Remove the old Sky subscription" / "Delete that obligation"

1. Find the obligation by keyword
2. **ALWAYS confirm before deleting**: "Delete 'Sky TV subscription'? This can't be undone."
3. Only after Chris confirms → call `DELETE /life-admin/obligations/{id}`

## Output Formats

### Dashboard / List View

```
**Life Admin — Vehicle**

• Car MOT VW Polo — due 15 May 2026 (48 days)
  Reg: AB12 CDE | Last done: 15 May 2025
• Car service — due 1 Aug 2026 (126 days)
  Provider: Halfords | Est: £199

2 items | Next due in 48 days
```

### Single Item

```
**Car MOT VW Polo**
Due: 15 May 2026 (48 days)
Reg: AB12 CDE
Provider: Local garage
Recurrence: Annual
Last done: 15 May 2025
```

### After Action

```
Marked Car MOT VW Polo as done.
Next due: 15 May 2027 (413 days)
```

### After Snooze

```
Snoozed boiler service until 11 Apr 2026.
Alerts will resume from that date.
```

### Full Overview

```
**Life Admin Overview**

🔴 **Overdue (1):** Boiler service (13 days)
🟡 **This month (3):** Home insurance, car tax, domain renewal
🟢 **All clear (20):** Everything else on track

24 tracked | Next due: Car tax (4 days)
```

## Rules

1. Always confirm before creating or deleting — never auto-mutate from ambiguous messages
2. For "mark as done" on recurring items, always show the next due date
3. Group by category when showing multiple obligations
4. Include reference numbers and provider info when available
5. Natural conversational tone (Peter's personality)
6. Use short date format: "15 May 2026"
7. Always show days remaining in parentheses
8. When listing, sort by due date (soonest first)
9. For uncertain requests, ask for missing information rather than guessing
10. If an obligation isn't tracked, offer to add it
