---
name: football-scores
description: Get live/recent Premier League scores
trigger:
  - "football scores"
  - "premier league"
  - "PL scores"
  - "how did [team] do"
  - "what's the score"
  - "footy"
  - "EPL"
scheduled: false
conversational: true
channel: null
---

# Football Scores

Get live/recent Premier League scores from Football-Data.org API.

## Pre-fetched Data

```json
{
  "matches": [
    {
      "home": "Chelsea",
      "away": "West Ham",
      "home_score": 2,
      "away_score": 1,
      "status": "IN_PLAY",
      "minute": 67,
      "kickoff": "2026-01-31T15:00:00Z"
    },
    {
      "home": "Brighton",
      "away": "Everton",
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

## Status Values

- `IN_PLAY` / `LIVE` - Match currently in progress
- `PAUSED` - Half-time
- `FINISHED` - Match complete
- `SCHEDULED` / `TIMED` - Not started yet

## Response Format

**Live/In Play:**
```
⚽ **Premier League - Live**

Chelsea 2-1 West Ham (67')
Liverpool 0-0 Newcastle (12')
```

**Finished:**
```
⚽ **Premier League - Final**

Brighton 2-1 Everton ✓
Leeds 0-3 Arsenal ✓
```

**Scheduled:**
```
⚽ **Premier League - Today**

17:30: Chelsea vs West Ham
20:00: Liverpool vs Newcastle
```

**No matches:**
```
⚽ No Premier League matches today.

Next: Saturday 7th Feb - Arsenal vs Man City (12:30)
```

## Rules

- Group by status: LIVE first, then FINISHED, then SCHEDULED
- Show minute for live games in parentheses
- UK times only (convert from UTC)
- If asked about specific team, filter to that team's match
- Keep it brief - just scores, no commentary
- If no matches today, mention next scheduled match if available

## Conversational Use (No Pre-fetched Data)

If someone asks about football scores in casual chat (not via `!skill`), you WON'T have pre-fetched data. In that case:

1. **Use web search** for "Premier League scores today" or "Premier League results"
2. Format the results using the same response format above
3. If web search fails, tell them to try `!skill football-scores` for live API data
