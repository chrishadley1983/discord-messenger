---
name: pl-results
description: Morning football results — Premier League, Champions League, Dover Athletic
trigger:
  - "PL results"
  - "premier league results"
  - "football results yesterday"
  - "champions league results"
  - "dover results"
scheduled: true
conversational: true
channel: "#peterbot"
---

# Football Results Summary

## Purpose

Morning roundup of yesterday's football results across Premier League, Champions League, and Dover Athletic. Runs daily at 06:05 — NO_REPLY on days with no football action at all.

## Pre-fetched Data

```json
{
  "pl_matches": [
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
  "cl_matches": [
    {
      "home": "Barcelona",
      "away": "Man City",
      "home_score": 3,
      "away_score": 1,
      ...
    }
  ],
  "spurs_match": null,
  "date": "2026-01-31"
}
```

- `pl_matches`: Yesterday's finished Premier League matches (may be empty)
- `cl_matches`: Yesterday's finished Champions League matches (may be empty)
- `spurs_match`: Populated when Spurs played in either competition, `null` otherwise

## MANDATORY: Web Search Before Writing

**You MUST web search before writing the report.** The pre-fetched data gives you scores and structure, but web search gives you the actual story. Do NOT write reports from the API data alone — it often lacks scorers and has no context.

### Required searches:

1. **If Spurs played:** Search `"Tottenham [opponent] match report"` and `"Tottenham [opponent] player ratings"` — read at least 2 sources (BBC Sport, Sky Sports, Guardian, etc.) to get scorers, key incidents, talking points, manager quotes
2. **For PL matches:** Search `"Premier League results [date]"` and `"Premier League match reports [date]"` — get scorers and headlines for every game
3. **For CL matches:** Search `"Champions League results [date]"` — get scorers and key talking points
4. **If multiple PL matches:** Search `"Premier League talking points [date]"` for broader narrative
5. **Always search:** `"Dover Athletic result"` or `"Dover Athletic score [date]"` — Dover are in the National League South, too low for any API. Web search is the ONLY way to get their results. If no result found, skip the Dover section (don't say "no result found").

Use the search results to write factual, informed reports — not generic filler. Include real scorer names, real minutes, real incidents, real quotes where available.

## NO_REPLY Cases

- No finished PL matches AND no finished CL matches AND no Dover result found -> respond with just `NO_REPLY`
- If ANY of the three have results, produce a report (even if just one section)

## Output Format

```
**Football Results** - Saturday 31st January

**Premier League**

**Chelsea 2-1 West Ham** (HT: 1-0)
Palmer 23', Jackson 67' | Bowen 55' (pen)
Stamford Bridge

**Arsenal 3-0 Brighton** (HT: 2-0)
Saka 12', Havertz 34', Trossard 78'
Emirates Stadium

**Wolves 0-2 Spurs** (HT: 0-1)
Son 38', Kulusevski 71'
Molineux

---

**Spurs Report**
[~150-200 words based on actual match reports from web search.]

---

**Champions League**

**Barcelona 3-1 Man City** (HT: 2-0)
Yamal 12', Lewandowski 34', Pedri 78' | Haaland 55'
Camp Nou

**PSG 0-0 Bayern Munich**
Parc des Princes

[~50-100 words on CL highlights — key results, upsets, English club performances]

---

**Dover Athletic**
**Dover 2-1 Tonbridge Angels**
Goals from Murphy 34', Smith 67'
Crabble Athletic Ground

---

**Around the League**
[~100-150 words covering highlights from all competitions]
```

## Rules

### Section Order
1. **Premier League** results (if any)
2. **Spurs Report** (if Spurs played in PL or CL)
3. **Champions League** results (if any)
4. **Dover Athletic** (if result found via web search)
5. **Around the League** summary

Only include sections that have content. Use `---` dividers between sections.

### Results Block
- One match per block: **bold scoreline** with HT score, scorers on next line, venue below
- Scorers format: `Name minute'` — separate home and away scorers with `|`
- Mark penalties as `(pen)`, own goals as `(og)`
- Sort by kickoff time within each competition
- Scorers MUST come from web search or API data — never guess or fabricate

### Spurs Report (when Spurs played)
- **150-200 words** about the Spurs match specifically
- MUST be based on web search results — include real details: how goals were scored, key saves, tactical decisions, red/yellow cards, injuries, manager quotes
- Cover what went right and wrong — balanced but from a Spurs perspective
- End with "COYS!" on wins or draws. On losses, be honest and measured.
- Applies whether Spurs played in PL or CL

### Champions League Section
- Same scoreline format as PL
- Add **50-100 words** of CL highlights after the results — focus on English clubs, upsets, drama
- If Spurs played in CL, the Spurs Report section covers them — don't repeat

### Dover Athletic Section
- Result comes entirely from web search (no API data)
- Include scorers and venue if found
- Keep brief — 2-3 lines max
- If web search finds no Dover result, omit the section entirely (no "no result found" message)

### Around the League
- **100-150 words** covering highlights from ALL competitions played yesterday
- Based on web search — pick out the real talking points
- Title race, relegation, CL drama, individual brilliance, controversy
- Tone: knowledgeable football mate — punchy, opinionated, informed

### General
- If Spurs didn't play, skip the Spurs Report section
- If only 1 match across all competitions, skip Around the League
- NEVER fabricate scorer names, minutes, or match details. If you can't find them via web search, say "scorers TBC" rather than guessing
- UK date format throughout
- Title is now "Football Results" not "Premier League Results"

## Conversational Use

If asked about football results in chat without pre-fetched data:
1. Web search for "Premier League results yesterday", "Champions League results yesterday", "Dover Athletic result"
2. Format using the same output format above
