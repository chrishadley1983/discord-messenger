# Directions

## Purpose
Get directions and route planning for ad-hoc journeys.

## Triggers
- "directions to {place}"
- "how do I get to {place}"
- "route to {destination}"
- "navigate to {address}"
- "best way to {place}"

## Schedule
None (conversational only)

## Data Source
Google Maps Routes API
- Endpoint: `https://routes.googleapis.com/directions/v2:computeRoutes`
- Supports: driving, walking, cycling, transit

## Parameters
Extract from user message:
- `destination` - where they want to go
- `mode` - driving (default), walking, cycling, transit
- `departure_time` - now (default) or specified time
- `avoid` - tolls, motorways, ferries

## Output Format

**Driving:**
```
🚗 **Directions to Bluewater**

📍 Distance: 28 miles
⏱️ Current time: 45 mins (via M25)
🛣️ Route: A21 → M25 → A2

**Traffic:** 🟡 Moderate
+8 mins due to M25 J5 congestion

**Alternative:** A20 route
⏱️ 52 mins but avoids motorway

💰 No tolls on either route
```

**Walking:**
```
🚶 **Walk to Tonbridge Station**

📍 Distance: 0.8 miles
⏱️ Time: 15 mins

Head down High Street, turn right at the bridge.
Mostly flat, pavement all the way.
```

**Transit:**
```
🚆 **Transit to London Bridge**

**Option 1:** Direct train
🚆 Tonbridge → London Bridge
⏱️ 45 mins | Departs 09:12 | Platform 2

**Option 2:** Via Sevenoaks
🚆 Tonbridge → Sevenoaks → London Bridge  
⏱️ 52 mins | Departs 09:08

Next 3 departures: 09:12, 09:32, 09:45
```

## Guidelines
- Default to driving unless walking distance (<1 mile) or transit requested
- Include current traffic impact
- Show alternatives if main route is congested
- For transit, show next few departure times
- Include practical notes (parking, station facilities)

## Conversational
Yes - follow-ups:
- "What about by train?"
- "Avoid the motorway"
- "What time should I leave to arrive by 10am?"
- "Is there parking there?"

## Smart Features

**Departure time calculation:**
- "I need to be there by 2pm" → Calculate leave time including traffic
- "Arrive for 10am meeting" → Factor in parking + walking

**Calendar integration:**
- "Directions to my next appointment" → Get location from calendar
- "How do I get to the dentist?" → Look up dentist appointment address

**Memory integration:**
- Remember frequently visited places
- "The usual route" → Recall preferred routes
- "Take me to mum's" → Use saved address from memory

## Address Resolution
If destination is ambiguous:
- Search Google Places API for options
- Ask for clarification if multiple matches
- Remember chosen location for future
