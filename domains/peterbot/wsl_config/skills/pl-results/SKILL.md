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

Morning roundup of yesterday's Premier League results with detailed match reports. Runs daily at 05:00 — NO_REPLY on days with no PL action.

## Pre-fetched Data

```json
{
  "matches": [
    {
      "home": "Chelsea",
      "away": "West Ham",
      "home_score": 2,
      "away_score": 1,
      "ht_home": 1,
      "ht_away": 0,
      "status": "FINISHED",
      "kickoff": "2026-01-31T12:30:00Z",
      "scorers": [
        {"player": "Cole Palmer", "minute": 23, "team": "Chelsea", "type": "REGULAR"},
        {"player": "Nicolas Jackson", "minute": 67, "team": "Chelsea", "type": "REGULAR"},
        {"player": "Jarrod Bowen", "minute": 55, "team": "West Ham", "type": "PENALTY"}
      ],
      "venue": "Stamford Bridge",
      "referee": "Michael Oliver"
    }
  ],
  "spurs_match": null,
  "date": "2026-01-31"
}
```

`spurs_match` is populated when Spurs played, `null` otherwise.

## NO_REPLY Cases

- No finished PL matches yesterday -> respond with just `NO_REPLY`

## Output Format

```
**Premier League Results** - Saturday 31st January

**Chelsea 2-1 West Ham** (HT: 1-0)
Palmer 23', Jackson 67' | Bowen 55' (pen)
Stamford Bridge

**Arsenal 3-0 Brighton** (HT: 2-0)
Saka 12', Havertz 34', Trossard 78'
Emirates Stadium

**Liverpool 1-1 Newcastle** (HT: 0-1)
Salah 62' | Isak 29'
Anfield

**Wolves 0-2 Spurs** (HT: 0-1)
Son 38', Kulusevski 71'
Molineux

---

**Spurs Report**
A professional away performance from Spurs at Molineux. Son opened the scoring before half-time with a trademark curling effort from the edge of the box, and Kulusevski doubled the lead midway through the second half with a well-placed finish after a slick counter-attack. Wolves barely threatened and Spurs were comfortable throughout — Ange's side moving up to 4th with this win. A clean sheet too, which has been rare lately. Exactly the kind of result you want heading into a busy run of fixtures. COYS!

**Around the League**
Arsenal made light work of Brighton at the Emirates — Saka was unplayable again, opening the scoring after just 12 minutes before Havertz and Trossard added to the tally. They're looking ominous in the title race. At Anfield, Newcastle took a surprise lead through Isak's clinical finish but Salah equalised from the spot in the second half. A point each feels fair — Liverpool will be disappointed not to win at home but Newcastle remain a tough nut to crack. Chelsea ground out a win against West Ham thanks to Palmer's brilliance and a late Jackson goal, despite Bowen pulling one back from the penalty spot.
```

## Rules

### Results Block
- One match per block: **bold scoreline** with HT score, scorers on next line, venue below
- Scorers format: `Name minute'` — separate home and away scorers with `|`
- Mark penalties as `(pen)`, own goals as `(og)`
- Sort by kickoff time

### Spurs Report (when Spurs played)
- **Detailed write-up, roughly 100-150 words** about the Spurs match specifically
- Cover the key moments, goalscorers, how they played, what it means for the table
- Tone: passionate Spurs fan — celebrate wins properly, be honest about poor performances
- End with "COYS!" on wins or draws. On losses, be measured but don't sugarcoat.

### Around the League
- **Detailed write-up, roughly 100-150 words** covering highlights from ALL the other matches
- Pick out the main talking points: title race, relegation battles, individual performances, upsets, controversy
- Tone: knowledgeable football mate giving you the morning briefing
- Punchy and opinionated — have a take, don't just list facts

### General
- If Spurs didn't play, skip the Spurs Report section — just do results + Around the League
- If only 1 match played (no other games), skip Around the League
- Web search for additional context if the pre-fetched data lacks scorer details (the API sometimes omits goals)
- UK date format throughout

## Conversational Use

If asked about PL results in chat without pre-fetched data:
1. Use web search for "Premier League results yesterday" and "Premier League scorers yesterday"
2. Format using the same output format above
