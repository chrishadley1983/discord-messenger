---
name: flight-prices
description: Daily London-Tokyo flight watch (Google Flights scrape, SerpApi fallback) for the Easter 2027 family trip
trigger:
  - "flight prices"
  - "flight deals"
  - "cheap flights"
  - "tokyo flights"
  - "flights to japan"
  - "flight watch"
scheduled: true
conversational: true
channel: "#alerts"
---

# Flight Watch — London ↔ Tokyo (Easter 2027)

## Purpose

Daily watch on flights for the family Japan trip (**2 adults + 2 children, ages 8 & 10 = 4 seats**).
Posts **every day** so Chris can see the current numbers and spot a dip.

**Trip dates:** out **Thu 25 Mar 2027** (evening/after school), back **Sun 11 Apr 2027** (morning) — school is back Mon 12 Apr.

Two things are tracked each day:
1. **Best value 1-stop** — cheapest Thursday-evening departure with a short layover.
2. **Best direct (nonstop)** — Thursday-night departure, LHR → Tokyo Haneda.

## How it works (don't re-implement — data is pre-fetched)

- **Primary source:** a live Google Flights scrape via the dedicated CDP Chrome (`services/flight_scrape.cjs`) — **no API quota**.
- **Fallback:** SerpApi, automatically, per-watch, only if a scrape yields nothing.
- **Config:** `data/flight_watches.json` — add a watch there to track more routes/variations; they all roll into this one daily post.
- Price history is stored in SQLite so we can show "lowest seen" and day-to-day movement.

## Pre-fetched Data

The scheduler injects `data`:

- `data.watches` — list, one per watch. Each item:
  - `label`, `outbound`, `return`, `pax`
  - `best` — chosen flight: `price_total`, `price_pp`, `airlines`, `depart_time`, `arrive_time`, `plus_days`, `duration_min`, `stops`, `nonstop`, `layover_min`, `layover_airports`, `off_criteria`
  - `source` — `"scrape"` or `"serpapi"`
  - `insight` — Google's price level (`low`/`typical`/`high`) when available
  - `history` — `lowest_pp` (lowest pp ever recorded for this watch), `checks`, `prev_pp` (previous reading)
  - `error` — present if neither source returned anything
- `data.scrape_ok`, `data.fallback_used`, `data.source_primary`, `data.scrape_error`

## Output Format

Format **both watches** into one compact post. Money: show **family total** and **per-person**. `depart_time`/`arrive_time` are 24h. `duration_min` → `Xh Ym`. `layover_min` → `Xh Ym` (add `via {layover_airports}` if present).

```
**✈️ Flight Watch — London → Tokyo** · {today}
Easter 2027 · 4 of us · out Thu 25 Mar · back Sun 11 Apr

**① Best value (1-stop)** — {airlines}
£{price_total} total · £{price_pp}pp
dep {depart_time} Thu → arr {arrive_time} (+{plus_days}d) · {duration} · {layover_min} layover[ via {layover_airports}]
{movement line}

**② Best direct (nonstop)** — {airlines}
£{price_total} total · £{price_pp}pp
dep {depart_time} Thu → arr {arrive_time} (+{plus_days}d) · {duration} · nonstop
{movement line}

_Source: live Google Flights{ · SerpApi fallback used} · check: google.com/travel/flights_
```

**Movement line** (per watch, from `history`):
- If `prev_pp` and it changed: `↓ £{diff}pp vs last check` (down = good) or `↑ £{diff}pp vs last check`.
- Append lowest-seen when checks ≥ 2: `· lowest seen £{lowest_pp}pp`.
- If `insight` present: `· Google: {insight} price`.
- If today's `price_pp` equals `lowest_pp` and checks ≥ 3: prepend `🔥 lowest yet — `.

## Rules

- Always post (daily readout, not deal-only). Use `NO_REPLY` only if `data.watches` is empty/missing entirely.
- Money in GBP. Lead with the **family total**, per-person in brackets.
- If a watch's `best.off_criteria` is true, add a short caveat e.g. `(no evening option today — closest match shown)`.
- If a watch has `error`, show `⚠️ {label}: couldn't fetch today` instead of a price.
- If `data.fallback_used` is true, note `SerpApi fallback used` in the source line.
- If `data.scrape_ok` is false AND there's no data at all, post: `⚠️ Flight watch couldn't fetch today ({scrape_error}).` so the breakage is visible.
- Layover: only append `via {layover_airports}` when it's non-empty — never render "via None"/"via []". Nonstop fares have no layover segment at all.
- Keep under 2000 chars for Discord. Don't fabricate booking deep links — point to `google.com/travel/flights`.
- Context for Chris (brief, only when a real dip happens): peak-Easter fares don't reliably fall closer to departure, so a clear drop is worth grabbing rather than waiting.

## Conversational Mode

When Chris asks about flights directly:
- "what's the flight watch?" / "how much to Tokyo?" — summarise both watches from `data.watches`.
- "add a watch for X" / "track Osaka too" — offer to add it to `data/flight_watches.json` (origin, destination, dates, adults, children, maxStops, select filters); it appears in the next post.
- "is now a good time to book?" — compare today's `price_pp` to `history.lowest_pp` and `insight`; remember peak-date fares trend flat-to-up.
- On-demand refresh: `POST http://172.19.64.1:8100/flights/check-now`.
