---
name: pl-results
description: Morning Premier League results summary from yesterday
trigger:
  - "PL results"
  - "premier league results"
  - "football results yesterday"
scheduled: true
conversational: true
channel: "#peterbot"
---

# PL Results Summary

## Purpose

Morning roundup of yesterday's Premier League results with a brief summary. Runs daily at 05:00 — NO_REPLY on days with no PL action.

## Pre-fetched Data

```json
{
  "matches": [
    {
      "home": "Chelsea",
      "away": "West Ham",
      "home_score": 2,
      "away_score": 1,
      "status": "FINISHED",
      "minute": null,
      "kickoff": "2026-01-31T12:30:00Z"
    }
  ],
  "date": "2026-01-31"
}
```

## NO_REPLY Cases

- No finished PL matches yesterday -> respond with just `NO_REPLY`

## Output Format

```
**Premier League Results** - Saturday 31st January

Chelsea 2-1 West Ham
Arsenal 3-0 Brighton
Liverpool 1-1 Newcastle
Wolves 0-2 Spurs

**Summary:** Goals galore on Saturday — Arsenal demolished Brighton, while Spurs picked up a solid away win at Molineux. Liverpool and Newcastle shared the spoils in a tight affair at Anfield.

Spurs win! COYS
```

## Rules

- List all finished matches, one per line
- Format: `Home Score-Score Away`
- Add a 1-2 sentence **Summary** after the results highlighting the key talking points (big wins, upsets, title race implications, relegation drama)
- If Spurs played, add a brief Spurs-specific comment at the end (celebrate wins, commiserate losses)
- Sort by kickoff time (earliest first)
- Use the full date in the header (e.g. "Saturday 31st January")
- Keep the summary punchy and opinionated — like a mate giving you the highlights
- UK date format

## Conversational Use

If asked about PL results in chat without pre-fetched data:
1. Use web search for "Premier League results yesterday"
2. Format using the same output format above
