---
name: saturday-sport-preview
description: Weekly sport preview for the coming week
trigger:
  - "sport this week"
  - "what sport is on"
  - "sport preview"
  - "what's on this week sport"
scheduled: true
conversational: true
channel: "#peterbot+WhatsApp:chris"
---

# Saturday Sport Preview

## Purpose

Weekly briefing of sport for the coming week, focused on Chris's teams and TV channels. Runs Saturday at 08:00.

## Chris's Teams
- **Spurs** (Tottenham Hotspur) - Premier League
- **England** - Cricket + Football
- **Kent** - County cricket
- **Dover Athletic** - National League South

## Chris's TV Channels
- Sky Sports, Amazon Prime, BBC, ITV

## Pre-fetched Data

```json
{
  "date": "2026-03-07",
  "week_ending": "2026-03-14",
  "pl_fixtures": [
    {"home": "Tottenham", "away": "Man City", "kickoff": "2026-03-08T16:30:00Z", "status": "TIMED"}
  ],
  "spurs_fixture": {"home": "Tottenham", "away": "Man City", "kickoff": "2026-03-08T16:30:00Z", "status": "TIMED"},
  "cricket_fixtures": [
    {"name": "England vs Australia, 4th Test", "date": "2026-03-10", "match_type": "test", "venue": "Lord's", "teams": ["England", "Australia"], "is_england": true, "is_kent": false}
  ]
}
```

## Web Search Required

The pre-fetched data covers PL football and cricket fixtures from APIs. You MUST also web search for:

1. **Dover Athletic fixtures** - search "Dover Athletic fixtures this week" (too low-tier for any API)
2. **TV schedule** - search "football on TV this week UK" and "cricket on TV this week UK"
3. **England football** - if international break, search "England football fixtures"
4. **Cup matches** - if Spurs are in a cup competition, search "Tottenham next match" (PL-only API won't cover cups)

## Output Format

```
**Sport This Week** - 7th-14th March

**Spurs**
Sun 8th: Spurs vs Man City (16:30, Sky Sports Main Event)

**England Cricket**
Tue 10th-Fri 13th: England vs Australia, 4th Test (Lord's, Sky Sports Cricket)

**Kent Cricket**
No fixtures this week

**Dover Athletic**
Sat 14th: Dover vs Tonbridge Angels (15:00, Crabble)

**Other PL Highlights**
Sat 7th: Arsenal vs Liverpool (12:30, BT Sport)
Sun 8th: Chelsea vs Man Utd (14:00, Sky Sports)

**On TV**
- Sky Sports: Spurs vs Man City (Sun), Arsenal vs Liverpool (Sat)
- Amazon Prime: No PL this week
- BBC/ITV: No live football
```

## Rules

- Lead with Spurs - always the most important fixture
- England cricket/football next
- Kent cricket
- Dover Athletic
- Then other notable PL fixtures and TV schedule
- Convert all times to UK timezone
- Include TV channel and kickoff time where known
- If no fixtures for a team, say "No fixtures this week"
- Keep each section brief - this is a preview, not a deep dive
- UK date format throughout
