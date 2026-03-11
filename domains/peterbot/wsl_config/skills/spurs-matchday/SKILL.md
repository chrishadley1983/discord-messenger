---
name: spurs-matchday
description: Morning alert when Spurs are playing today
trigger:
  - "are spurs playing today"
  - "spurs today"
  - "is there a spurs game"
scheduled: true
conversational: true
channel: "#peterbot+WhatsApp:chris"
---

# Spurs Match-Day Reminder

## Purpose

Morning heads-up when Spurs have a match today. Runs at 08:00 daily — NO_REPLY on non-match days.

## Pre-fetched Data

```json
{
  "spurs_playing": true,
  "home": "Tottenham",
  "away": "Man City",
  "is_home": true,
  "kickoff": "2026-02-01T16:30:00Z",
  "kickoff_uk": "16:30",
  "venue": "Tottenham Hotspur Stadium",
  "competition": "Premier League",
  "date": "2026-02-01"
}
```

When no match: `{"spurs_playing": false}`

## NO_REPLY Cases

- `spurs_playing` is `false` -> respond with just `NO_REPLY`

## Web Search

Search `"Tottenham team news today"` or `"Spurs predicted lineup [opponent]"` to add a line or two of context — injuries, form, what's at stake.

## Output Format

```
**Spurs play today!**
Spurs vs Man City - 16:30 KO
Tottenham Hotspur Stadium | Premier League

[1-2 lines of context from web search — e.g. key injury news, league position context, what's at stake]

COYS!
```

## Rules

- Always format as "Spurs vs [opponent]" regardless of home/away
- Include kickoff time in UK timezone, venue, and competition
- Add brief context from web search (injuries, form, stakes) — max 2 lines
- End with "COYS!"
- Keep it short and punchy — this is a heads-up, not a preview
