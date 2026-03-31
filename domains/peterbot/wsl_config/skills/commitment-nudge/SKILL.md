---
name: commitment-nudge
description: Daily nudge for unfulfilled promises Chris made in WhatsApp and email
trigger: []
scheduled: true
conversational: false
channel: "WhatsApp:chris"
---

# Commitment Nudge

## Purpose

Scans for open commitments Chris has made in WhatsApp conversations (and eventually
email) that haven't been followed through on. Sends a single WhatsApp message
summarising what he's forgotten. Runs daily in the evening to catch anything from
the day or earlier.

## Pre-fetched Data

Data injected by the scheduler via `get_commitment_nudge_data()`:

```json
{
  "open_commitments": [
    {
      "id": "uuid",
      "text": "I'll book that restaurant tonight",
      "matched_pattern": "I'll book",
      "category": "direct_commitment",
      "recipient": "Abby",
      "source": "whatsapp",
      "detected_at": "2026-03-27T19:30:00Z",
      "age_hours": 26,
      "nudge_count": 0
    }
  ],
  "count": 1,
  "dismissed_today": 0,
  "resolved_today": 2
}
```

## Output Format

Keep it brief and casual. Chris doesn't want a task manager — he wants a mate
giving him a gentle nudge.

```
🧠 **Quick reminder** — couple of things you said you'd do:

• **Book restaurant** (to Abby, yesterday) — "I'll book that restaurant tonight"
• **Send Japan dates to Mum** (3 days ago) — "I'll send you the Japan dates"

Reply with numbers to mark done (e.g. "1 done" or "both done"), or "skip" to dismiss.
```

## Post-Delivery Actions

After sending, record the nudge for each commitment:
```
POST http://172.19.64.1:8100/commitments/{id}/nudge
```

## Rules

- `NO_REPLY` if no open commitments (nothing to nudge about)
- Group by recipient where possible (all Abby items together)
- Show the original matched text in quotes so Chris remembers context
- Include age in human terms: "yesterday", "2 days ago", "last week"
- Max 5 items per nudge — if more, show top 5 by age and mention "and X more"
- Don't nudge the same commitment more than once per day
- If a commitment has been nudged 3+ times with no action, suggest dismissing it
- Never nudge about things said to Peter (bot conversations are not commitments)
- Keep under 500 chars — this goes to WhatsApp, not Discord
- Warm tone, not naggy. More "heads up" than "you forgot"
