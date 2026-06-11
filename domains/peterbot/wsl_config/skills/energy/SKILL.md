---
name: energy
description: Live home energy — current demand, today's usage/cost, appliance events, EV charging
trigger:
  - "energy"
  - "electricity"
  - "how much power"
  - "what's using power"
  - "energy usage today"
  - "is the oven on"
  - "ev charge"
  - "car charging"
scheduled: false
conversational: true
---

# Energy (Live — Octopus Home Mini)

## Purpose

Answer questions about home energy using LIVE data (10-second resolution from the smart meter), not yesterday's history.

## Endpoints (Hadley API, base `http://172.19.64.1:8100`)

| Question | Endpoint |
|----------|----------|
| "what's using power right now" / current demand | `GET /energy/live` → `demand_w`, current rate, today so far |
| "how much energy/cost today" | `GET /energy/today` → total_kwh, est_cost_pounds, peak_demand_w |
| "is the oven on" / "did the kettle just boil" / appliance activity | `GET /energy/events?hours=6` → typed events (kettle, oven_or_heater, ev_charge, spike, high_load) |
| "when is the car charging" / EV cost | `GET /energy/ev` → planned + completed Intelligent Go dispatch slots |
| daily/weekly history | `GET /energy/summary?days=7` → complete daily summaries (note: official data lags 1–2 days; for today ALWAYS use /energy/today) |

## Interpretation guide

- `demand_w` ~200–400W = house baseline; 1.5–3kW = cooking/kettle; 4.5kW+ sustained = EV charging
- `offpeak_now: true` = Intelligent Go cheap rate (23:30–05:30 UTC + dispatch slots) — good time for dishwasher/washing
- Events with `"ongoing": true` in detail are still running
- EV charging during dispatch slots costs the off-peak rate (~7p/kWh) — never count it as "expensive usage"
- For "is something left on": check /energy/live demand vs baseline + /energy/events for ongoing high_load/oven events

## Timestamps (IMPORTANT)

All `read_at` / `started_at` / dispatch times are **UTC** — UK time is 1h ahead during BST. NEVER show raw UTC timestamps: use `age_seconds` ("10 seconds ago") for live readings, and convert event times to UK local (e.g. 10:41Z → 11:41 UK in summer).

## Response style

Short and concrete: "House is drawing 280W (baseline) — nothing unusual on." or "Kettle boiled at 14:02 (3 min, 2.8kW). Oven's been on 45 min — dinner?" Convert to £ when asked about cost. Flag off-peak opportunities when relevant ("dishwasher now would cost 4x what it will at 23:30").
