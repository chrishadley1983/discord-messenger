# Directions

## Purpose
Directions, route planning, and live traffic checks (merged from the old traffic-check skill).

## Triggers
- "directions to {place}"
- "how do I get to {place}"
- "route to {destination}"
- "how long to {place}"
- "best way to {place}"
- "traffic", "how's the traffic", "is there traffic"
- "school run traffic", "how long to school"
- "should I leave now"

## School Run Quick Check

For school-traffic questions use `curl http://172.19.64.1:8100/traffic/school`:

```
🚗 **Traffic to School**
⏱️ {duration_mins} mins (usually {typical_mins})
{traffic_icon} {traffic_level} traffic

Leave by {leave_time} to arrive on time.
```

Traffic indicators: 🟢 Light (at/below typical) · 🟡 Moderate (+1-5 mins) · 🔴 Heavy (+5-15 mins) · ⚠️ Severe (+15 mins). Compare to typical time, not just absolute, and include a departure recommendation.

## Schedule
None (conversational only)

## Data Source
Hadley API: `curl "http://172.19.64.1:8100/directions?destination={place}"`

Optional parameters:
- `origin` - start point (default: home)
- `mode` - DRIVE (default), WALK, BICYCLE, TRANSIT

Example: `curl "http://172.19.64.1:8100/directions?destination=Bluewater&mode=DRIVE"`

## Output Format

**Driving:**
```
🚗 **Directions to {destination}**

📍 Distance: {distance_km} km
⏱️ Time: {duration_mins} mins

From: {origin}
```

**Walking:**
```
🚶 **Walk to {destination}**

📍 Distance: {distance_km} km
⏱️ Time: {duration_mins} mins
```

## Guidelines
- **Never show raw JSON** - only present the formatted human-readable output
- Default to driving unless walking distance (<1 mile) or user specifies
- Include practical notes about the journey
- For transit, mention train stations if relevant

## Conversational
Yes - follow-ups:
- "What about by train?"
- "What time should I leave to arrive by 10am?"
