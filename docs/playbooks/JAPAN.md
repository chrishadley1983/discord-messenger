# Japan Trip Playbook

READ THIS for any Japan-related question — before, during, and after the trip.

## Trip Summary

**This trip is FULLY PLANNED.** Do not ask "are dates locked in?" — everything below is confirmed.

- **Dates:** Apr 3-19, 2026 (17 days, family of 4: Chris, Abby, Emmie 9, Max 7)
- **Route:** Tokyo (3 nights) -> Osaka (4 nights) -> Himeji day trip -> Kyoto (4 nights) -> Tokyo (5 nights) -> Depart
- **Guide site:** https://hadley-japan-2026.surge.sh (day pages, food map, restaurant database, activity guides)
- **Standalone repo:** `C:/Users/Chris Hadley/claude-projects/japan-family-guide`

### Accommodation (all booked)

| Days | City | Stay | Host |
|------|------|------|------|
| 1-3 (Apr 3-5) | Tokyo | Kitashinjuku Apartment, 2-9-9 Kitashinjuku | Tokyo Look In |
| 4-7 (Apr 6-9) | Osaka | Dotonbori Apartment, 2-8-29 Nishishinsaibashi | Yoko & Nobu |
| 8-11 (Apr 10-13) | Kyoto | Kyoto Machiya, Shimogyo Ward | Team LUX |
| 12-16 (Apr 14-18) | Tokyo | Nezu Apartment, near Nezu Station | Toshiko |
| 17 (Apr 19) | Departure | Haneda Airport red-eye 01:30 | |

### Booked Anchors

- 3 Shinkansen tickets (Tokyo->Osaka, Himeji->Kyoto, Kyoto->Tokyo)
- teamLab BioVortex — Apr 13, 9am
- Shibuya Sky — planned but not yet booked

### Key Events by Day

| Day | Date | City | Highlights |
|-----|------|------|------------|
| 1 | Apr 3 | Tokyo | Arrival day |
| 2 | Apr 4 | Tokyo | Tohoku Food Festival near accommodation |
| 3 | Apr 5 | Tokyo | Chidorigafuchi Illuminations (evening) |
| 4 | Apr 6 | Travel | Shinkansen to Osaka |
| 5 | Apr 7 | Osaka | USJ Cool Japan 2026 |
| 6 | Apr 8 | Nara | Day trip — Hana Matsuri at temples |
| 7 | Apr 9 | Osaka | Mint Bureau cherry blossom (if open) |
| 8 | Apr 10 | Himeji->Kyoto | HIRANO SHRINE OKA-SAI |
| 9 | Apr 11 | Kyoto | Miyako Odori evening show |
| 10 | Apr 12 | Kyoto | Kyoto exploring |
| 11 | Apr 13 | Kyoto | teamLab 9am + Yasurai Festival noon |
| 12 | Apr 14 | Travel | Shinkansen to Tokyo |
| 13 | Apr 15 | Tokyo | DisneySea 25th Sparkling Jubilee |
| 14 | Apr 16 | Tokyo | Nezu Shrine azaleas |
| 15 | Apr 17 | Tokyo | Craft Sake Week opens |
| 16 | Apr 18 | Tokyo | LAST FULL DAY — Tohoku Food Festival |
| 17 | Apr 19 | Depart | Red-eye 01:30 |

---

## Data Sources

### Supabase Tables (japan schema)

All queries need `Accept-Profile: japan` header.

| Table | What it holds |
|-------|--------------|
| `japan_day_plans` | Daily schedule per date (city, stay, plan_data JSON array, notes) |
| `japan_bookings` | Booking confirmations (activity, ref, status, links) |
| `japan_photos` | Photo book images by day |
| `japan_highlights` | One-liner memorable moments by day |
| `japan_diary` | Diary entries / voice note transcriptions by day |
| `japan_expenses` | Spending log (amount, category, payment method, day) |

**To query a day plan:**
```bash
curl -s "http://172.19.64.1:8100/japan/day-plans/2026-04-08"
```

### Restaurant Database

380+ restaurants with Tabelog scores, coordinates, cuisine, price range, kid-friendliness:
- Source file: `C:/Users/Chris Hadley/claude-projects/japan-family-guide/site/restaurants.json`
- Live on guide site: https://hadley-japan-2026.surge.sh/food-map.html
- Loaded automatically by `japan_context.py` during trip for proximity search

### Food Picks

Pre-curated meals by trip day (breakfast/lunch/dinner per day):
- Source: `C:/Users/Chris Hadley/claude-projects/japan-family-guide/site/food-picks.json`
- Includes status (booked/planned/pending), cash-only flags, notes

---

## Hadley API — Japan Endpoints

Base URL: `http://172.19.64.1:8100`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/japan/day-plans` | GET | All day plans |
| `/japan/day-plans/{date}` | GET | Single day plan |
| `/japan/day-plans/{date}` | PUT | Update day plan |
| `/japan/trains?city=CITY` | GET | Live JR train status (tokyo/osaka/kyoto/all) |
| `/japan/expenses` | POST | Log spending (amount, category, description, payment_method) |
| `/japan/expenses/today` | GET | Today's expense summary |
| `/japan/photobook/upload` | POST | Upload photo from WhatsApp |
| `/japan/photobook/highlight` | POST | Save highlight moment |
| `/japan/photobook/diary` | POST | Save diary entry |
| `/japan/photobook/coverage/{day}` | GET | Photo/highlight/diary counts for a day |
| `/japan/digest/send` | POST | Generate & email HTML daily digest |
| `/japan/sim` | GET/POST | Get/set sim date for testing |
| `/japan/alerts/test` | POST | Generate test alerts (dry run) |

---

## During Trip (Apr 3-19)

**You don't need to do anything special.** The system auto-activates:

1. `japan_context.py` injects rich context into every WhatsApp conversation:
   - Today's schedule, bookings, food picks, nearby restaurants, festivals
   - Expense logging instructions, photo book pipeline, train status
   - Location-aware restaurant finder (GPS coordinates -> nearest restaurants)

2. `japan_alerts.py` sends proactive WhatsApp alerts every 15 minutes:
   - 07:00 JST: Morning briefing (schedule, weather, sakura status, food picks)
   - 30 min before booked items: Reminder with confirmation ref, QR codes, links
   - 60 min before cash-only restaurants: Cash warning
   - 20:00 JST: Pack reminder (if moving accommodation tomorrow)
   - 20:00 JST: Booking confirmation nudge (pending items for tomorrow)
   - 08:00 JST: Photo book coverage nudge (yesterday's photo/diary count)

### During-Trip Behaviours

- "Where should we eat?" -> Check today's food picks first, then nearest restaurants from DB
- "How do we get to X?" -> Use `/directions` with transit mode, mention specific line/station
- "Spent Y3200 at Kushikatsu" -> Log via `/japan/expenses`
- "Add to Japan Drive" (with photo) -> Upload via `/japan/photobook/upload`
- Memorable moment shared -> Save via `/japan/photobook/highlight`
- "Any train delays?" -> Check via `/japan/trains?city=CITY`
- "What's happening today?" -> Fetch day plan from Supabase + festival calendar

---

## Pre-Trip (NOW — before Apr 3)

When Chris asks about Japan before the trip:

1. **Itinerary questions** -> Query Supabase `japan_day_plans` or check the guide site
2. **Restaurant questions** -> Search the restaurant DB (380+ entries with ratings)
3. **Booking status** -> Search Second Brain for "japan booking" or "shinkansen" or "airbnb japan"
4. **What's left to do?** -> Check `japan_bookings` for status=pending, check food-picks for unconfirmed meals
5. **Packing / prep** -> Web search for Japan family travel tips, weather forecast for early April
6. **"Tell me about Day X"** -> Fetch the day plan: `curl -s "http://172.19.64.1:8100/japan/day-plans/2026-04-{X+2}"`

**NEVER ask "are dates locked in?" or "still in research phase?" — this trip has been planned for months with a full day-by-day itinerary, 380+ researched restaurants, and a published guide website.**

---

## Post-Trip

- Photo book compilation from `japan_photos`, `japan_highlights`, `japan_diary` tables
- Expense summary from `japan_expenses`
- Guide site remains live as a reference

---

## Trigger Phrases

Any of these should activate this playbook:
- "japan", "tokyo", "osaka", "kyoto", "shinkansen"
- "the trip", "our trip", "family trip"
- "day 1", "day 2", etc. (in trip context)
- "what's the plan for", "what are we doing"
- "restaurant", "where to eat" (when Japan context active)
- "train delay", "jr status"
