---
name: spurs-live
description: Auto-post live Spurs score updates during matches (every 10 min)
trigger: []
scheduled: true
conversational: false
channel: "#peterbot"
---

# Spurs Live Updates

## Purpose

Automatic score updates during Tottenham Hotspur Premier League matches. Runs every 10 minutes via interval job. Silent on non-match days (NO_REPLY).

This is the **scheduled** variant. The existing `spurs-match` skill remains for conversational on-demand use.

## Pre-fetched Data

When Spurs are playing:
```json
{
  "spurs_playing": true,
  "home": "Tottenham",
  "away": "Man City",
  "home_score": 1,
  "away_score": 0,
  "status": "IN_PLAY",
  "minute": 67,
  "kickoff": "2026-02-01T16:30:00Z",
  "kickoff_uk": "16:30",
  "scorers": [
    {"player": "Kulusevski", "minute": 42, "team": "Tottenham"}
  ],
  "venue": "Tottenham Hotspur Stadium",
  "date": "2026-02-01"
}
```

When Spurs are NOT playing (most runs):
```json
{
  "spurs_playing": false
}
```

## NO_REPLY Cases

- `spurs_playing` is `false` -> respond with just `NO_REPLY`
- This will be the case most of the time (non-match days, outside match window)

## Output Format

**Pre-match (SCHEDULED/TIMED status, within 15 min of kickoff):**
```
**Spurs vs Man City** - 16:30 KO
Tottenham Hotspur Stadium
COYS!
```

**During match (IN_PLAY/LIVE):**
```
**Spurs 1-0 Man City** (67')
Kulusevski 42'
```

**Half-time (PAUSED):**
```
**HT: Spurs 1-0 Man City**
Kulusevski 42'
```

**Full-time (FINISHED):**
```
**FT: Spurs 2-1 Man City**
Kulusevski 42', Son 78' | Haaland 55'
COYS!
```

## Rules

- Always format as Spurs first regardless of home/away (e.g. "Spurs 1-0 Man City" even if away)
- Include scorer names and minutes when available
- Separate home and away scorers with `|`
- Add "COYS!" on kickoff and wins only
- Show match minute in parentheses for live games
- Keep updates brief - just score and key info
- If Spurs lose at FT, no "COYS" - just the result
