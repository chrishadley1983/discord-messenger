# EV Charging (Ohme)

## Purpose
Check car charging status, control charging, and view energy usage.

## Triggers
- "car charging", "is the car charging", "charge status"
- "how much charge", "battery level"
- "start/stop charging"
- "when will the car be ready"
- "charging cost", "energy usage"

## Schedule
- 07:00 UK daily (if car plugged in, part of morning-briefing)

## Data Source
Ohme API
- Base URL: `https://api.ohme.io`
- Auth: OAuth2 (email/password → access token)

## Pre-fetcher
`get_ev_charging_data()` - fetches:
- Charger status (charging, idle, scheduled, disconnected)
- Current battery level (%)
- Charge rate (kW)
- Time to target
- Energy added this session (kWh)
- Cost estimate (based on tariff)

## Output Format

**Currently Charging:**
```
🔌 **Car Charging**
🔋 Battery: 45% → 80% target
⚡ Charging at 7.2kW
⏱️ Ready by: 06:30 (2h 15m remaining)
💰 Session cost: ~£1.85 (so far)
```

**Scheduled:**
```
🔌 **Charging Scheduled**
🔋 Battery: 45%
⏰ Starts: 00:30 (cheap rate)
🎯 Target: 80% by 07:00
💰 Est. cost: ~£3.20
```

**Idle/Disconnected:**
```
🔌 **Car Not Charging**
🔋 Last known: 72%
📍 Status: Disconnected

Plug in to start charging.
```

## Commands

**Check status:** (default)
- "Is the car charging?"
- "Car battery level?"

**Start charging:**
- "Start charging now"
- "Charge to {percent}%"
- "Override schedule, charge now"

**Stop charging:**
- "Stop charging"
- "Pause the charge"

**Set target:**
- "Charge to 100% tonight" (usually for long trips)
- "Set charge limit to 80%"

## Guidelines
- Default target is 80% (better for battery longevity)
- Note if charging during expensive rate
- Warn if battery very low (<20%)
- For morning briefing, only include if relevant (plugged in)

## Conversational
Yes - follow-ups:
- "Charge to 100% instead"
- "When's the cheapest time to charge?"
- "How much did last week's charging cost?"
- "Will it be ready for school run?"

## Smart Charging Notes
Ohme optimises for:
- Cheapest electricity rates (if smart tariff like Octopus Go)
- Target ready time
- Battery health (avoids constant 100%)

Peter should understand and explain these optimisations.
