# Trip Prep

## Purpose

Consolidated trip preparation check - combines calendar, directions, and EV status for upcoming trips.

## Triggers

- "trip prep"
- "am I ready for [destination]"
- "trip to [place]"
- "ready for my trip"

## Data Sources

All via Hadley API (http://172.19.64.1:8100):

1. **Calendar**: `/calendar/today` or `/calendar/tomorrow` - find the trip event
2. **Directions**: `/directions?destination={address}` - get route and travel time
3. **EV Status**: `/ev/status` - check charge level and if sufficient for trip

## Process

1. Identify the trip from user query or scan calendar for travel-related events
2. Extract destination address from calendar event (location field)
3. Fetch directions to get distance and current travel time
4. Fetch EV status to check battery level
5. Calculate if charge is sufficient (assume ~5 km/kWh efficiency)
6. Recommend leave time based on appointment minus travel time minus 10 min buffer

## Output Format

```
**Trip Prep: [Event Name]**

**When:** [Day, Date] at [Time]
**Where:** [Destination]

**Route**
- Distance: [X] km
- Current estimate: [Y] mins
- Leave by: [Time] (10 min buffer)

**EV Status**
- Battery: [X]% ([estimated/actual])
- Range needed: ~[Y] km round trip
- Status: [Sufficient / Charge recommended]

[Any warnings or notes]
```

## Rules

- If no trip specified, check today's and tomorrow's calendar for travel events
- Always calculate round-trip distance for EV check
- Use 5 km/kWh as conservative efficiency estimate
- Flag if battery is below 20% after estimated trip
- If EV is currently charging, note expected completion

## Example

User: "Am I ready for Brickstop?"

```
**Trip Prep: Brickstop Cafe**

**When:** Sunday, 1 Feb at 10:15 AM
**Where:** 26 Godstone Rd, Caterham CR3 6RA

**Route**
- Distance: 32 km (64 km round trip)
- Current estimate: 42 mins
- Leave by: 09:20 (10 min buffer)

**EV Status**
- Battery: ~45% (estimated)
- Range needed: ~64 km round trip (~13 kWh)
- Status: Sufficient

Have a good trip!
```
