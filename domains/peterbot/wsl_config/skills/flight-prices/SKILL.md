---
name: flight-prices
description: Daily flight price monitoring for nonstop UK-Tokyo flights with deal alerts
trigger:
  - "flight prices"
  - "flight deals"
  - "cheap flights"
  - "tokyo flights"
  - "flights to japan"
scheduled: true
conversational: true
channel: "#alerts"
---

# Flight Price Monitor

## Purpose

Monitor nonstop economy flights from London Heathrow (LHR) to Tokyo Haneda (HND) for 2 passengers. Runs daily to track prices, detect deals, and alert when prices drop significantly.

Airlines operating this route: British Airways, JAL, ANA.

## Pre-fetched Data

Data is injected by the scheduler. Structure:

- `data.scan_results` — today's scanned date pairs with prices per route
  - Each result has: `outbound`, `return`, `price_pp`, `price_total`, `airline`, `duration_min`, `insights`
  - `insights` includes: `lowest_price`, `typical_low`, `typical_high`, `price_level` (low/typical/high)
- `data.cheapest_overall` — top 5 cheapest prices found in last 30 days
- `data.deals` — any detected deals (price drops >10% or below target threshold)
- `data.summary` — monitoring stats: total checks, active routes, recent alerts

## Output Format

**Deals found:**
```
**Flight Deals** — {date}

**London to Tokyo** (nonstop, economy, 2 pax)

**Deal Alert**
{airline} | {outbound} - {return} ({nights}n)
{price_pp}pp / {price_total} total | {drop_pct}% below average
Google says: {price_level} price (typical range: {typical_low}-{typical_high})

**Today's Scan**
{airline} | {date range} | {price_pp}pp
{airline} | {date range} | {price_pp}pp

**Cheapest Found (30d)**
{price_pp}pp — {airline} | {outbound} ({nights}n)

{total_checks} checks this week | {active_routes} routes tracked
```

**No deals (daily scheduled):**
```
**Flight Monitor** — {date}

**London to Tokyo** | No deals today

**Today's Scan**
{airline} | {date range} | {price_pp}pp
{airline} | {date range} | {price_pp}pp

**Cheapest Found (30d)**: {price_pp}pp — {airline} | {date}
```

**Nothing to report:** If no scan results and no deals, respond with `NO_REPLY`

## Rules

- Prices are per person (pp) and total for 2 passengers
- Currency is GBP
- Only show nonstop flights
- When Google Flights says price_level is "low", highlight it
- Keep under 2000 chars for Discord
- For scheduled runs: compact format, deals first
- For conversational: include more detail, answer specific date questions
- Link format for manual checking: `google.com/travel/flights` (don't fabricate deep links)
- If data has `error` key, report the issue briefly and suggest checking SERPAPI_KEY

## Conversational Mode

When Chris asks about flights directly:
- "how much to fly to Tokyo in July?" — check specific dates, report prices
- "cheapest dates for Tokyo?" — show top 5 cheapest from DB
- "any flight deals?" — run detect_deals and report
- Can trigger an on-demand scan via Hadley API: `POST http://172.19.64.1:8100/flights/check-now`
