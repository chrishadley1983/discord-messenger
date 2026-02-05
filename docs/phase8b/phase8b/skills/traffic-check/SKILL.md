# Traffic Check

## Purpose
Check current traffic conditions for regular routes (school, work, etc.).

## Triggers
- "traffic", "how's the traffic", "is there traffic"
- "how long to {destination}"
- "school run traffic", "commute time"
- "should I leave now"
- "M25", "A21" (specific roads)

## Schedule
- Part of `school-run` skill (07:30 UK)
- Part of `school-pickup` skill (14:30 UK)

## Data Source
Google Maps Routes API
- Endpoint: `https://routes.googleapis.com/directions/v2:computeRoutes`
- Requires: Google Cloud API key with Routes API enabled

## Pre-fetcher
`get_traffic_data()` - fetches:
- Current travel time vs typical
- Traffic conditions (light, moderate, heavy)
- Incidents/delays on route
- Alternative routes if faster

## Saved Routes (Configure)
```python
SAVED_ROUTES = {
    "school": {
        "origin": "Tonbridge home address",
        "destination": "School address",
        "typical_time": 12  # minutes
    },
    "station": {
        "origin": "Tonbridge home address", 
        "destination": "Tonbridge Station",
        "typical_time": 8
    },
    # Add more routes
}
```

## Output Format

**Quick Check:**
```
🚗 **Traffic to School**
⏱️ 15 mins (usually 12)
🔴 Moderate traffic - A26 congestion

Leave by 08:15 to arrive for 08:30.
```

**Detailed:**
```
🚗 **Traffic Report**

**To School:** 15 mins (+3)
🔴 Slow on A26 near Hadlow

**To Station:** 10 mins (+2)
🟡 Minor delays on High Street

**M25 (J5):** Heavy traffic ⚠️
Avoid if possible - accident near Sevenoaks
```

**All Clear:**
```
🚗 **Traffic Clear** ✓
School run: 12 mins (normal)
Roads looking good - no delays reported.
```

## Traffic Indicators
- 🟢 Light (at or below typical)
- 🟡 Moderate (+1-5 mins)
- 🔴 Heavy (+5-15 mins)
- ⚠️ Severe (incident, +15 mins)

## Guidelines
- Compare to typical time, not just absolute
- Include departure time recommendation
- Note specific causes (roadworks, accident, school traffic)
- For school run, factor in parking/drop-off time

## Conversational
Yes - follow-ups:
- "What about the back roads?"
- "When should I leave?"
- "Is the M25 better?"
- "Show me alternative routes"

## Integration with Calendar
When user has an appointment:
- "Traffic to dentist appointment" → Get appointment location from calendar
- "How long to get to my 2pm meeting?" → Calendar lookup + traffic
