---
name: pl-results
description: End-of-day Premier League results roundup
trigger:
  - "PL results"
  - "premier league results"
  - "football results today"
scheduled: true
conversational: true
channel: "#peterbot"
---

# PL Results Summary

## Purpose

End-of-day roundup of all Premier League results. Runs Saturday and Sunday evenings at 21:30.

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

- No finished PL matches today -> respond with just `NO_REPLY`

## Output Format

```
**Premier League Results** - Saturday 31st January

Chelsea 2-1 West Ham
Arsenal 3-0 Brighton
Liverpool 1-1 Newcastle
Wolves 0-2 Spurs

Spurs win! COYS
```

## Rules

- List all finished matches, one per line
- Format: `Home Score-Score Away`
- If Spurs played, add a brief comment at the end (celebrate wins, commiserate losses)
- Sort by kickoff time (earliest first)
- Use the full date in the header (e.g. "Saturday 31st January")
- Keep it concise - just results, no extended commentary
- If some matches are still live/scheduled, only show finished ones and note how many are still in progress
- UK date format

## Conversational Use

If asked about PL results in chat without pre-fetched data:
1. Use web search for "Premier League results today"
2. Format using the same output format above
