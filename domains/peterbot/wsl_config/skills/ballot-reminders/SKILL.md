---
name: ballot-reminders
description: Proactive alerts when ticket ballots open for England Cricket, England Football, Oval Invincibles
trigger:
  - "ballot"
  - "ticket ballot"
  - "any ballots open"
scheduled: true
conversational: true
channel: "#peterbot+WhatsApp:chris"
---

# Ballot Reminders

## Purpose

Proactive alerts when ticket ballots open for:
- **England Cricket** (ECB / Kia Oval)
- **England Football** (FA)
- **Oval Invincibles** (The Hundred)

Runs daily at 09:00. Checks Gmail for ballot notification emails from the last 7 days.

## Pre-fetched Data

When ballots found:
```json
{
  "ballots": [
    {
      "subject": "England vs Australia - Ballot Now Open",
      "from": "noreply@ecb.co.uk",
      "date": "2026-03-05",
      "snippet": "Register now for the ballot for England vs Australia at The Oval..."
    }
  ],
  "count": 1
}
```

When no ballots:
```json
{
  "no_ballots": true
}
```

## NO_REPLY Cases

- `no_ballots` is `true` -> respond with just `NO_REPLY`

## Output Format

```
**Ticket Ballot Alert!**

**England vs Australia - Ballot Now Open**
From: ECB
Date: 5th March
Register now for the ballot for England vs Australia at The Oval...

Action: Check your email and register before the deadline!
```

## Rules

- Highlight urgency - ballots have deadlines
- Include the email subject and key snippet
- Tell Chris to check his email and act
- If multiple ballots, list them all
- Keep it actionable - this is a reminder to DO something
- Don't duplicate ballots already mentioned in previous days (if the same email subject appeared before, skip it)

## Conversational Use

If asked about ballots in chat without pre-fetched data:
1. Use web search for "ECB ticket ballot 2026" or "England football ballot"
2. Also check "Oval Invincibles tickets 2026"
3. Report what you find
