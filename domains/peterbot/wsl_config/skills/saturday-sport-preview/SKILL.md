---
name: saturday-sport-preview
description: Weekly sport preview for the coming week
trigger:
  - "sport this week"
  - "what sport is on"
  - "sport preview"
  - "what's on this week sport"
  - "weekend sport"
scheduled: true
conversational: true
channel: "#peterbot+WhatsApp:chris"
---

# Saturday Sport Preview

## Purpose

Weekly briefing of sport for the coming week, focused on Chris's teams, F1, and what's on his TV channels. Runs Saturday at 08:00.

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
  "pl_fixtures": [...],
  "spurs_fixture": {...},
  "cricket_fixtures": [...],
  "f1": {
    "race_name": "Australian Grand Prix",
    "circuit": "Albert Park Grand Prix Circuit",
    "location": "Australia",
    "race_date": "2026-03-08",
    "race_time": "05:00:00Z",
    "round": "2",
    "fp1_date": "2026-03-06",
    "fp1_time": "02:30:00Z",
    "qualifying_date": "2026-03-07",
    "qualifying_time": "06:00:00Z",
    "sprint_date": "2026-03-07",
    "sprint_time": "02:30:00Z"
  }
}
```

`f1` will be `null` if no race this week.

## Web Search Required

The pre-fetched data covers PL football, cricket fixtures, and F1 from APIs. You MUST also web search for:

1. **Dover Athletic fixtures** - search "Dover Athletic fixtures this week" (too low-tier for any API)
2. **TV sport highlights this week** - search "sport on TV this week UK Sky Sports BBC ITV Amazon Prime" to find all major live sport across Chris's channels. This is the most important search — cover ALL sport, not just football.
3. **England football** - if international break, search "England football fixtures"
4. **Cup matches** - if Spurs are in a cup competition, search "Tottenham next match" (PL-only API won't cover cups)

## Output Format

```
**Sport This Week** - 7th-14th March

**Spurs**
Sun 8th: Spurs vs Man City (16:30, Sky Sports Main Event)

**F1 - Australian Grand Prix** (Albert Park, Round 2)
Fri 6th: Practice 1 (12:30 GMT)
Sat 7th: Qualifying (06:00 GMT)
Sun 8th: Race (05:00 GMT, Sky Sports F1)

**Cricket**
*ICC T20 World Cup Final* - Sun 8th: Australia vs South Africa (14:00, Sky Sports Cricket)
*England:* Tue 10th-Fri 13th: England vs Australia, 4th Test (Lord's, Sky Sports Cricket)
*England Lions:* Sun 9th: Pakistan A vs England Lions, 5th Unofficial ODI (Abu Dhabi)
*Kent:* No fixtures this week
*IPL:* Mumbai Indians vs Chennai Super Kings (Sat 15:00, Sky Sports Cricket)

**Dover Athletic**
Sat 14th: Dover vs Tonbridge Angels (15:00, Crabble)

**Other PL Highlights**
Sat 7th: Arsenal vs Liverpool (12:30, Sky Sports)
Sun 8th: Chelsea vs Man Utd (14:00, Sky Sports)

**On TV This Week**
- **Sky Sports:** Spurs vs Man City (Sun), F1 Australian GP (Fri-Sun), T20 World Cup Final (Sun), England vs Australia Test (Tue-Fri), Arsenal vs Liverpool (Sat), Indian Wells tennis
- **Amazon Prime:** Newcastle vs Barcelona CL Wed 18:30
- **BBC:** Six Nations rugby - England vs France (Sat 16:45)
- **ITV:** Cheltenham Festival (Tue-Fri)
```

## Rules

- Lead with Spurs - always the most important fixture
- F1 next - include full weekend schedule (practice, qualifying, sprint if applicable, race) with UK times
- **Cricket section** — cover ALL cricket from the pre-fetched data, organised by priority:
  1. ICC events first (World Cups, Champions Trophy) — these are unmissable
  2. England / England Lions
  3. Kent
  4. IPL (if in season)
  5. Other notable international matches (Tests, ODIs between major nations)
  - Skip low-profile domestic matches from other countries (SA provincial, etc.)
- Dover Athletic
- Then other notable PL fixtures
- **On TV This Week** section at the end is critical — list ALL notable live sport across Sky Sports, Amazon Prime, BBC, and ITV. Not just football — include rugby, cricket, F1, golf, tennis, boxing, darts, whatever is on. This is the section Chris cares about most for planning his week.
- Convert all times to UK timezone (GMT or BST as appropriate)
- Include TV channel and kickoff/start time where known
- If no fixtures for a team, say "No fixtures this week"
- Keep each section brief - this is a preview, not a deep dive
- UK date format throughout
