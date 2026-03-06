---
name: cricket-scores
description: Daily morning cricket score roundup from yesterday
trigger:
  - "cricket scores"
  - "cricket results"
  - "how did England do"
  - "county cricket"
scheduled: true
conversational: true
channel: "#peterbot"
---

# Cricket Score Summary

## Purpose

Morning roundup of yesterday's cricket across all major competitions. Runs daily at 08:30.

## Pre-fetched Data

```json
{
  "matches_by_competition": {
    "International": [
      {
        "name": "England vs Australia, 3rd Test",
        "status": "England won by 5 wickets",
        "match_type": "test",
        "venue": "The Oval, London",
        "score": [
          {"r": 312, "w": 10, "o": 87.3, "inning": "Australia Inning 1"},
          {"r": 350, "w": 10, "o": 95.1, "inning": "England Inning 1"}
        ],
        "teams": ["England", "Australia"]
      }
    ],
    "English Domestic": [...],
    "IPL": [...],
    "Australian Domestic": [...]
  },
  "date": "2026-03-05"
}
```

If no cricket yesterday:
```json
{
  "no_matches": true
}
```

## NO_REPLY Cases

- `no_matches` is `true` -> respond with just `NO_REPLY`

## Output Format

```
**Cricket Roundup** - Thursday 5th March

**International**
England vs Australia, 3rd Test - England won by 5 wickets (The Oval)
ENG 350 & 245/5 dec | AUS 312 & 280

**English Domestic**
Kent vs Surrey, County Championship - Kent won by 3 wickets (Canterbury)
Surrey vs Essex - Match drawn

**IPL**
Mumbai Indians 185/4 beat Chennai Super Kings 172/8 by 13 runs
```

## Rules

- Group by competition type with bold headers
- England and Kent matches get priority placement within their groups
- Show result status prominently
- Include key scores where available (innings totals for Tests, final scores for limited overs)
- Include venue for International and England/Kent matches
- Keep concise - one or two lines per match max
- If a Test match is still in progress (multi-day), show current state
- UK date format in header

## Conversational Use

If asked about cricket in chat without pre-fetched data:
1. Use web search for "cricket scores yesterday" or the specific query
2. Format using the same output format above
