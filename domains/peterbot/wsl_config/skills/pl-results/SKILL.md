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

Morning roundup of yesterday's Premier League results with detailed match reports based on real match coverage. Runs daily at 05:00 — NO_REPLY on days with no PL action.

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
        {"player": "Cole Palmer", "minute": 23, "team": "Chelsea", "type": "REGULAR"}
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

## MANDATORY: Web Search Before Writing

**You MUST web search before writing the report.** The pre-fetched data gives you scores and structure, but web search gives you the actual story. Do NOT write reports from the API data alone — it often lacks scorers and has no context.

### Required searches:

1. **If Spurs played:** Search `"Tottenham [opponent] match report"` and `"Tottenham [opponent] player ratings"` — read at least 2 sources (BBC Sport, Sky Sports, Guardian, etc.) to get scorers, key incidents, talking points, manager quotes
2. **For all other matches:** Search `"Premier League results [date]"` and `"Premier League match reports [date]"` — get scorers and headlines for every game
3. **If multiple matches:** Search `"Premier League talking points [date]"` for broader narrative (title race, relegation, individual performances)

Use the search results to write factual, informed reports — not generic filler. Include real scorer names, real minutes, real incidents, real quotes where available.

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
[~150-200 words based on actual match reports from web search. Real details — who scored and how, key chances, tactical setup, turning points, manager reaction, what it means for the table. Written as a knowledgeable Spurs fan, not a neutral commentator.]

**Around the League**
[~100-150 words covering highlights from the other matches. Based on web search — real scorers, real incidents, title/relegation implications. Opinionated and punchy.]
```

## Rules

### Results Block
- One match per block: **bold scoreline** with HT score, scorers on next line, venue below
- Scorers format: `Name minute'` — separate home and away scorers with `|`
- Mark penalties as `(pen)`, own goals as `(og)`
- Sort by kickoff time
- Scorers MUST come from web search or API data — never guess or fabricate

### Spurs Report (when Spurs played)
- **150-200 words** about the Spurs match specifically
- MUST be based on web search results — include real details: how goals were scored, key saves, tactical decisions, red/yellow cards, injuries, manager quotes
- Cover what went right and wrong — balanced but from a Spurs perspective
- End with "COYS!" on wins or draws. On losses, be honest and measured.

### Around the League
- **100-150 words** covering highlights from ALL the other matches
- Based on web search — pick out the real talking points
- Title race, relegation battles, individual brilliance, controversy, VAR incidents
- Tone: knowledgeable football mate — punchy, opinionated, informed

### General
- If Spurs didn't play, skip the Spurs Report section — just do results + Around the League (make it longer, ~200 words)
- If only 1 match played (no other games), skip Around the League
- NEVER fabricate scorer names, minutes, or match details. If you can't find them via web search, say "scorers TBC" rather than guessing
- UK date format throughout

## Conversational Use

If asked about PL results in chat without pre-fetched data:
1. Web search for "Premier League results yesterday" and specific match reports
2. Format using the same output format above
