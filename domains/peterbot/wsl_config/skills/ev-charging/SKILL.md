# EV Charging (Ohme)

## Purpose
Check car charging status and battery level.

## Triggers
- "car charging", "is the car charging", "charge status"
- "how much charge", "battery level"
- "when will the car be ready"

## Schedule
- 07:00 UK daily (if relevant, part of morning-briefing)

## Data Source
**Preferred (actual battery data):**
`curl http://172.19.64.1:8100/ev/combined`

**Kia Connect only (car data):**
`curl http://172.19.64.1:8100/kia/status`

**Ohme only (charger data):**
`curl http://172.19.64.1:8100/ev/status`

## Output Format

**Currently Charging:**
```
🔌 **Car Charging**
🔋 Battery: {battery_level}% → {target_level}% target
⚡ Charging at {charge_rate_kw}kW
```

**Idle/Plugged In:**
```
🔌 **Car Plugged In**
🔋 Battery: {battery_level}%
Status: {status}
```

**Not Plugged In:**
```
🚗 Car not plugged in
🔋 Last known: {battery_level}%
```

## Guidelines
- **Never show raw JSON** - only present the formatted human-readable output
- Default target is 80% (better for battery longevity)
- For morning briefing, only include if car is plugged in or charging
- Note if battery is low (<20%)

## Battery Level Note
The Kia doesn't have a direct API connection to Ohme, so:
- `battery_level` will be `null` (not available)
- `battery_level_estimated` is extrapolated from energy added this session only
- `battery_source: "EXTRAPOLATION"` means it's NOT the actual car battery level
- **Don't report the estimated battery as the real SOC** - tell the user Ohme can't read the actual battery level

## Conversational
Yes - follow-ups:
- "Will it be ready for school run?"
- "What's the charge percentage?"
