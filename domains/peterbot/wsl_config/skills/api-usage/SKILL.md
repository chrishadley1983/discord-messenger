---
name: api-usage
description: Weekly API usage and cost summary
trigger:
  - "api usage"
  - "api costs"
  - "how much have i spent"
scheduled: true
conversational: true
channel: #api-usage
---

# Weekly API Usage Summary

## Purpose

Weekly summary every Monday at 9am UK showing API usage and costs for the previous week.

## Pre-fetched Data

If available, data will be pre-fetched. Otherwise, note that current implementation may need manual checking.

```json
{
  "anthropic": {
    "total_cost": 12.50,
    "requests": 450,
    "input_tokens": 2500000,
    "output_tokens": 180000
  },
  "openai": {
    "total_cost": 3.20,
    "requests": 120
  },
  "grok": {
    "total_cost": 2.80,
    "requests": 85
  },
  "week_ending": "2026-01-31"
}
```

## Output Format

```
📊 **Weekly API Usage** - Week ending 31 January

**Claude (Anthropic)** 🔮
Cost: $12.50
Requests: 450

**OpenAI** 🤖
Cost: $3.20
Requests: 120

**Grok (xAI)** ⚡
Cost: $2.80
Requests: 85

---
**Total: $18.50**

[Brief note if usage is unusual - higher/lower than typical]
```

## Rules

- Show each API provider separately
- Include request counts where available
- Calculate and show total
- Note any unusual spikes
- If data unavailable for a provider, say "Data unavailable" not an error
- Keep it factual - this is a report, not motivation
