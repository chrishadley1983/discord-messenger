# Directions

## Purpose
Get directions and route planning for ad-hoc journeys.

## Triggers
- "directions to {place}"
- "how do I get to {place}"
- "route to {destination}"
- "how long to {place}"
- "best way to {place}"

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
