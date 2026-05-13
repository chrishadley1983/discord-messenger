---
name: cost-digest
description: Daily roll-up of Claude usage across router_v2 and channel sessions
trigger:
  - "cost digest"
  - "claude costs"
  - "how much did peter cost"
  - "peter cost today"
scheduled: true
conversational: true
channel: #alerts
---

# Daily Claude Cost Digest

## Purpose

Daily roll-up at 23:55 UK of all Claude usage across the two pathways:

- **router_v2** — `claude -p` per-message fallback. Definitely programmatic after Jun 15 2026.
- **channels** — the 3 persistent Claude Code sessions (peter, whatsapp, jobs). Classification TBD; today they consume Max subscription rate limits, but they may be reclassified as programmatic.

This skill exists so we have a paper trail to react quickly if Anthropic moves channels onto the new programmatic credit on Jun 15.

## Pre-fetched Data

```json
{
  "day": {
    "window_hours": 24,
    "calls": 108,
    "total_usd": 49.69,
    "total_gbp": 39.26,
    "router_v2": {"cost_usd": 1.76, "note": "programmatic"},
    "channels": {"cost_usd": 47.94, "note": "TBD"},
    "by_source": {"channel:jobs-channel": {"calls": 77, "cost_usd": 47.94}, "scheduled:hydration": {"calls": 15, "cost_usd": 0.64}},
    "by_channel": {"jobs-channel": {"calls": 77, "cost_usd": 47.94}, "#food-log": {"calls": 20, "cost_usd": 0.85}},
    "by_model": {"claude-opus-4-6": {"calls": 77, "cost_usd": 47.94}, "claude-sonnet-4-6": {"calls": 31, "cost_usd": 1.76}}
  },
  "week": {
    "window_hours": 168,
    "calls": 1500,
    "total_usd": 420.00,
    "router_v2": {"cost_usd": 14.00},
    "channels": {"cost_usd": 406.00}
  },
  "credit_estimate": {
    "max_5x_remaining_usd": 100.0,
    "max_20x_remaining_usd": 200.0,
    "monthly_run_rate_usd_programmatic_only": 53.0,
    "monthly_run_rate_usd_if_channels_reclassified": 1490.0
  },
  "timestamp": "2026-05-13 23:55"
}
```

## Output Format

```
💸 **Claude Cost Digest** — 23:55

**Last 24h:** $49.69 (£39.26) · 108 calls
  • router_v2 (programmatic): $1.76
  • channels (TBD): $47.94

**Top spend:**
  • jobs-channel — $47.94 (77 calls, Opus 4.6)
  • #food-log — $0.85 (hydration ×15)
  • #peterbot — $0.61

**Last 7d:** $420.00 · 1500 calls

**Run-rate vs Jun 15 credit:**
  • Programmatic only: $53/mo → comfortably inside Max 5x credit ($100)
  • If channels reclassified: $1,490/mo → 7× over Max 20x ($200)

[One-line action note if numbers spike or if channels jumped]
```

## Rules

- Always include both 24h and 7d totals.
- Show router_v2 and channels split EVERY time — that is the whole point of this digest.
- Pull top 3 spenders from `by_source` or `by_channel`, whichever is more readable.
- Flag the action implication: if `if_channels_reclassified > $200`, note "channels would blow Max 20x credit".
- Use £ for GBP totals; keep USD for the per-line costs (matches Anthropic's billing currency).
- Keep it under 12 lines.
- NEVER respond with `NO_REPLY` — Chris wants this card every day for the next ~4 weeks.

## Action Suggestions (only if relevant)

If `channels.cost_usd > 30` for the 24h window, append:
```
⚠️ jobs-channel running hot — consider dropping scheduled-job model to Sonnet to cut ~80%.
```

If `router_v2.cost_usd > 5` for the 24h window, append:
```
⚠️ router_v2 spike — was {n}× yesterday's $X. Worth checking what triggered.
```
