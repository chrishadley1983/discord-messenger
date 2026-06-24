---
name: home-sensors
description: Live INDOOR temperature & humidity per room from the home Zigbee sensors
trigger:
  - "temperature in the bedroom"
  - "how warm is it in here"
  - "room temperature"
  - "house temperature"
  - "is it cold in the kitchen"
  - "how warm is the bedroom"
  - "humidity"
  - "how humid is it"
  - "indoor temperature"
scheduled: false
conversational: true
---

# Home Sensors (Live — indoor Zigbee)

## Purpose

Answer questions about the **inside** of the house — room temperature, humidity,
whether a room is occupied — using LIVE readings from the Zigbee sensors on the
dashboard Pi. This is the indoor counterpart to the `weather` skill.

## Indoor vs outdoor (IMPORTANT)

- **Inside / a room / "in here" / "upstairs" / a named room (bedroom, kitchen, lounge) / humidity** → THIS skill (`/home/sensors`).
- **Outside / "is it raining" / forecast / "do I need a jacket"** → the `weather` skill (`/weather/current`).

If it's ambiguous ("what's the temperature?") and Chris is clearly at home talking about a room, prefer indoor; if it's about going out or the day ahead, prefer outdoor. When genuinely unsure, give the indoor reading and note the outdoor temp in one line.

## Endpoint (Hadley API, base `http://172.19.64.1:8100`)

| Question | Endpoint |
|----------|----------|
| "what's the temperature in the bedroom" / "how warm is it in here" / "is the kitchen humid" | `GET /home/sensors` |

Response shape:
```json
{
  "sensors": [
    {"id": "sensor_kitchen", "room": "Kitchen", "temperature_c": 27.7, "humidity_pct": 64.8,
     "occupancy": null, "illuminance_lux": null, "battery_pct": 100, "link_quality": 108},
    {"id": "sensor_bedroom", "room": "Bedroom", "temperature_c": 26.6, "humidity_pct": 68.2, ...},
    {"id": "motion_lounge", "room": "Lounge", "temperature_c": null, "humidity_pct": null,
     "occupancy": true, "illuminance_lux": 542, ...}
  ],
  "count": 3,
  "bridge": "http://192.168.0.110:5001",
  "fetched_at": "2026-06-24T..."
}
```

## Current sensors

- **Kitchen**, **Bedroom** — temperature + humidity + battery.
- **Lounge** — a motion sensor: reports `occupancy` and `illuminance_lux` (light level), **no** temperature/humidity (`null`). Use it for "is anyone in the lounge / is the light on", not temperature.

The endpoint is generic — if Chris pairs a new sensor it appears automatically with a room name derived from its key.

## Trends & history

The bridge keeps ~30 days of readings, so Peter can answer "is it warmer than
yesterday?", "what was the overnight low?", "has humidity climbed this week?".

| Question | Endpoint |
|----------|----------|
| Weekly/daily trend per room (min/max/avg + vs-yesterday) | `GET /home/sensors/trend?days=7` → `rooms[]` each with `daily[{date,temp_min,temp_max,temp_avg,humidity_avg}]` + `avg_change_vs_prev_day_c` |
| Raw curve for one room | `GET /home/sensors/history?room=bedroom&hours=24` (add `&kind=motion` for the lounge motion timeline) |

- "warmer than yesterday" → `/trend`, compare the last two `daily` `temp_avg` (or use `avg_change_vs_prev_day_c`).
- "overnight low" → `/history?room=…&hours=12` overnight, take the min temperature.
- Only Kitchen + Bedroom have temperature history (the Lounge is motion-only).

## Interpretation guide

- Comfort: ~18–21°C is the usual indoor comfort band; below ~16°C reads as chilly, above ~26°C as warm/stuffy.
- Humidity: ~40–60% is comfortable; >65% sustained invites damp/mould, <30% is dry.
- A `temperature_c`/`humidity_pct` of `null` means that device doesn't measure it (e.g. the lounge motion sensor) — don't report it as 0 or "no data" for the house; just use the rooms that do report.
- `battery_pct` low (<15%) means the sensor needs a new battery (the watchdog also alerts #alerts).

## If the data is unavailable

`/home/sensors` returns 502 when the bridge can't be reached — that means the dashboard Pi (`192.168.0.110`) is offline (it also serves the pocket-money dashboard). Tell Chris the home sensors are unreachable and that the Pi may be off the network; don't invent readings.

## Response style

Short and concrete: "Bedroom's 26.6°C, a bit warm — humidity 68%." or "Kitchen 27.7°C / 64% humidity, lounge is occupied." Convert nothing; quote the live numbers. Round to one decimal. If asked about the whole house, list the rooms that report temperature.
