---
name: spurs-match
description: Live Spurs match score updates during games
trigger:
  - "spurs score"
  - "tottenham score"
  - "how are spurs doing"
scheduled: true
conversational: true
channel: #peterbot
---

# Spurs Match Updates

## Purpose

Post live Tottenham Hotspur score updates to #peterbot during matches. Runs every 15 minutes during match time.

## Pre-fetched Data

Uses Football-Data.org API (same as football-scores skill):

```json
{
  "matches": [
    {
      "home": "Tottenham",
      "away": "Man City",
      "home_score": 1,
      "away_score": 0,
      "status": "IN_PLAY",
      "minute": 67,
      "kickoff": "2026-02-01T16:30:00Z"
    }
  ],
  "spurs_playing": true,
  "date": "2026-02-01"
}
```

## Scheduled Trigger

**Match Day Schedule** (requires SCHEDULE.md entry):
- Check fixtures at 06:00 to see if Spurs play today
- If match found, schedule updates at: kickoff, +15, +30, HT (~+45), +60, +75, FT (~+95)
- Post to #peterbot

## Output Format

**Kickoff:**
```
**Spurs vs Man City - KICKOFF**
0-0 | Tottenham Hotspur Stadium
COYS
```

**During Match:**
```
**Spurs 1-0 Man City** (67')
Kulusevski 42'
```

**Halftime:**
```
**HALF-TIME: Spurs 1-0 Man City**
Kulusevski 42'
```

**Full Time:**
```
**FULL TIME: Spurs 2-1 Man City**
Kulusevski 42', Son 78' | Haaland 55'
```

## Conversational Use

If asked about Spurs score in chat:
1. Use web search for "Tottenham score today" or "Spurs match live"
2. Return formatted score update
3. If no match today, say when next match is

## Status Mapping

- `SCHEDULED` / `TIMED` - Not started
- `IN_PLAY` / `LIVE` - Match in progress
- `PAUSED` - Half-time
- `FINISHED` - Match complete

## NO_REPLY Cases

- No Spurs match today
- Match finished (after FT update posted)
- Outside match window

## Rules

- Always include scorer names if available
- Convert times to UK timezone
- Keep updates brief - just score and key info
- Show opponent name, not just "Opponent"
- Add "COYS" on kickoff only
