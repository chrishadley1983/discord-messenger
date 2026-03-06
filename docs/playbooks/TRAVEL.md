# Travel Playbook

READ THIS for any travel planning, trip, or destination research query.

## Data Sources

- **Bookings in Second Brain**: Search for travel bookings — flights, hotels, trains, check-in instructions are auto-imported from Gmail
- Active trip details: Check memory context + Notion (/notion/search)
- Places: /places/search, /places/nearby, /places/details
- Directions: /directions?destination=X, /directions/matrix
- Weather: /weather/forecast (for date-specific planning)
- Calendar: /calendar/range (for trip date conflicts)
- Currency: /currency (for price conversions)
- Web search: for reviews, guides, tips, opening hours

IMPORTANT: Trip dates, accommodation, and itinerary details live in memory
context, Notion, AND Second Brain (booking confirmations). Check all three.

## Booking Intelligence (Second Brain)

Travel bookings are automatically imported from Gmail into Second Brain by the `travel-bookings` seed adapter. This means you CAN answer questions about upcoming trips, booking details, and provide proactive travel intelligence.

**To find bookings, search Second Brain:**
- `"flight british airways"` — BA flight bookings
- `"hotel booking"` or `"airbnb"` — accommodation bookings
- `"train trainline"` — rail bookings
- `"check-in instructions"` — check-in details (door codes, house rules, etc.)
- `"travel beeksebergen"` or `"travel lalandia"` — holiday park bookings

**Data available per booking type:**

| Type | Fields |
|------|--------|
| **Flights** | Airline, flight number, PNR, airports, times, terminals, seat, class, baggage, manage booking link |
| **Hotels** | Hotel name, address, phone, check-in/out dates, room type, price, cancellation policy, parking, WiFi |
| **Trains** | Stations, times, operator, carriage, seat, ticket type, railcard, collection method, e-ticket link |
| **Check-in** | Check-in instructions, door codes, WiFi password, host contact, house rules, required documents |
| **Airbnb** | Full listing details (amenities, reviews, neighbourhood) imported separately by the Airbnb scraper |

**Proactive alerts to give Chris:**

| Situation | What to say |
|-----------|-------------|
| Flight within 7 days | "Your BA flight to Tokyo is in 5 days. Ref: ABC123. Check-in opens 24hrs before departure." |
| Airbnb check-in email received | "Your Kyoto Airbnb host sent check-in instructions — door code is 4521, WiFi: sakura2026" |
| Hotel cancellation deadline approaching | "Free cancellation for your Booking.com hotel expires in 3 days (March 8th)" |
| Required documents pending | "Your Japan Airbnb host has requested passport details — check-in is in 5 days" |
| Pre-trip briefing | "Tomorrow: check-out Osaka Airbnb by 11am. Train to Kyoto at 13:30 (carriage B, seat 42). Kyoto Airbnb check-in from 3pm." |

| Chris asks | Action |
|-----------|--------|
| "What trips have I got coming up?" | Search Second Brain for recent travel bookings, group by trip |
| "What's my booking ref for Japan?" | Search for flight/hotel bookings with Japan-related keywords |
| "When's check-in for the Airbnb?" | Search for check-in instructions for the relevant property |
| "Do I need to do anything for the trip?" | Check for pending document requests, upcoming cancellation deadlines, check-in windows |
| "What's the WiFi at the hotel?" | Search check-in instructions for WiFi details |

## What Makes Travel Queries Different

Travel combines multiple data sources in a single response. A good travel
response weaves these together — don't just answer one dimension.

When recommending places, ALWAYS include:
- Price range in LOCAL CURRENCY + approximate GBP (use /currency)
- Address or area (for mapping to itinerary)
- Booking requirement (walk-in / book ahead / book weeks ahead)
- Kid-friendliness (check memory for who's travelling)
- Proximity to where they're staying (check trip details)
- Best time to visit (lunch vs dinner, weekday vs weekend)

## Restaurant/Activity Recommendations

Use RESEARCH.md process but with travel-specific additions:
- Minimum 3 searches across different source types (guides, reviews, local blogs)
- Structure as ranked picks with consistent detail format
- Include practical tips that save money/time/hassle
- Note seasonal considerations if relevant

## Day Planning

Use PLANNING.md format with travel additions:
- Transit details: which line/train, how long, cost, pass coverage
- Combine nearby activities to minimize travel
- Build in downtime (check memory for family composition — kids need rest)
- Weather-dependent alternatives ("if rain: X instead of Y")
- Meal slots that align with location

## Practical Logistics

When asked "how do we get from X to Y", don't just name the transport.
Include:
- Specific service/line name
- Station/stop to station/stop
- Journey time
- Cost (and whether covered by any pass they have)
- Seat reservation needed?
- Frequency (every X minutes)

## Budget Awareness

Convert prices to GBP for context using /currency.
Help estimate daily spend when asked.

## What BAD Looks Like

❌ Restaurant recommendations without prices or booking info
❌ "Take the train" without specifying which train, time, or cost
❌ Ignoring the family context (kids, ages, energy levels)
❌ Planning that doesn't account for travel time between locations

---

## Hadley API Endpoints

Base URL: `http://172.19.64.1:8100`

| Query | Endpoint | Method |
|-------|----------|--------|
| Place search | `/places/search?query=pizza+near+Tokyo` | GET |
| Place details | `/places/details?place_id=ChIJ...` | GET |
| Nearby places | `/places/nearby?type=restaurant&location=Kyoto&radius=5000` | GET |
| Autocomplete | `/places/autocomplete?input=starbucks` | GET |
| Directions | `/directions?destination=Tokyo&origin=Osaka` | GET |
| Multi-destination | `/directions/matrix?destinations=Tokyo,Kyoto,Nara` | GET |
| Geocode | `/geocode?address=10+Downing+Street` | GET |
| Reverse geocode | `/geocode?latlng=51.5074,-0.1278` | GET |
| Timezone | `/timezone?location=New+York` | GET |
| Elevation | `/elevation?location=Ben+Nevis` | GET |
| Translate | `/translate?text=Hello&target=ja` | GET |
| Currency convert | `/currency?amount=100&from=USD&to=GBP` | GET |
| Unit convert | `/units?value=5&from=miles&to=km` | GET |
| Static map | `/maps/static?center=London&zoom=12&size=400x400` | GET |
| Street view | `/maps/streetview?location=Big+Ben&size=400x400` | GET |
| Sunrise/sunset | `/sunrise?location=London` | GET |
| Moon phase | `/moon?date=2026-02-14` | GET |
| Weather forecast | `/weather/forecast` | GET |

## Trigger Phrases

- "Find pizza places nearby" → `/places/search?query=pizza`
- "Is Tesco open?" → `/places/search` then `/places/details` for hours
- "What restaurants are near X?" → `/places/nearby?type=restaurant&location=X`
- "How do I get to X?" / "How long to X?" → `/directions?destination=X`
- "How long to London vs Brighton?" → `/directions/matrix?destinations=London,Brighton`
- "What's the postcode for X?" → `/geocode?address=X`
- "What time is it in New York?" → `/timezone?location=New+York`
- "How high is Ben Nevis?" → `/elevation?location=Ben+Nevis`
- "How do you say hello in Japanese?" → `/translate?text=hello&target=ja`
- "Convert 100 dollars to pounds" → `/currency?amount=100&from=USD&to=GBP`
- "Convert 5 miles to km" → `/units?value=5&from=miles&to=km`
- "Show me a map of London" → `/maps/static?center=London&zoom=12`
- "What time is sunrise tomorrow?" → `/sunrise?location=London`

## Research Example — GOOD Format

When recommending restaurants (e.g., "recommend Kobe beef restaurants"):

```
🍖 **Kobe Beef Restaurant Recommendations**

Based on my research, here are the top spots:

**1. Kobe Beef Kaiseki 511** ⭐ Best Overall
- Address: 1-8-21 Shimoyamate-dori, Chuo-ku
- Price: ¥15,000-25,000 (~£85-140) per person
- Why: A5 wagyu with kaiseki courses, intimate 8-seat counter
- Book ahead: Usually 2-3 weeks

**2. Mouriya Honten** ⭐ Best Value
- Address: 2-1-17 Shimoyamate-dori
- Price: ¥8,000-15,000 (~£45-85) per person
- Why: Established 1885, cook-at-table teppanyaki style
- Tip: Lunch sets are 40% cheaper than dinner

**Tips:**
- Look for the Kobe Beef Marketing Association certificate
- Reservations essential for top spots

Sources:
- [Japan Starts Here](https://japanstartshere.com/...)
- [Kobe Official Guide](https://www.feel-kobe.jp/en/)
```
