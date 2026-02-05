---
name: school-pickup
description: Afternoon school pickup traffic report with after-school clubs info
trigger:
  - "school pickup"
  - "pickup"
  - "clubs today"
scheduled: true
conversational: true
channel: #traffic-reports
whatsapp: true
---

# School Pickup Report

## Purpose

Afternoon traffic report for school pickup. Posts to Discord AND WhatsApp.
- Monday, Tuesday, Thursday, Friday: Job runs 14:55, **pickup 15:10**
- Wednesday: Job runs 16:50, **pickup 17:00** (clubs run longer)

## CRITICAL RULES

1. **Use `target_pickup` from pre-fetched data** - This is the school pickup time, NOT the job schedule time.

2. **Use `suggested_leave` from pre-fetched data** - This is pre-calculated based on traffic duration and target pickup.

3. **ALWAYS include rain probability** with advice if needed:
   - >50%: "🧥 Grab coats!"
   - 20-50%: "🌧️ Maybe bring coats"
   - <20%: Just show weather

4. **ALWAYS show pickup info for BOTH kids** - Even if one has no club, show their standard pickup.

5. **Do NOT call any APIs yourself** - All data is pre-fetched. Just format it.

## Pre-fetched Data Structure

```json
{
  "traffic": {
    "duration_in_minutes": 22,
    "route_name": "A26",
    "traffic_condition": "Clear ✅"
  },
  "weather": {
    "temp_c": 12,
    "condition": "Partly cloudy",
    "rain_probability": 10
  },
  "clubs": {
    "max": {
      "club": "Football",
      "end_time": "16:00",
      "pickup_location": "Sports field gate"
    },
    "emmie": {
      "club": null,
      "end_time": "15:15",
      "pickup_location": "Main gate"
    }
  },
  "suggested_leave": "14:43",
  "target_pickup": "15:10",
  "day_of_week": "Monday",
  "date": "2026-02-02"
}
```

## Output Format

```
🚗 **School Pickup** - Monday, 2 February

**Traffic:** 22 mins via A26 🟢
Leave by **14:43** for **15:10** pickup

**Weather:** 12°C, Partly cloudy

**Pickup:**
👦 Max: Football → Sports field gate @ 16:00
👧 Emmie: Main gate @ 15:15

See you there! 🎒
```

## Traffic Status Indicators

- 🟢 Clear (traffic adds <5 mins)
- 🟡 Moderate (5-10 mins added)
- 🔴 Heavy (>10 mins added)

## Rules

- Discord uses **bold** (double asterisk)
- Always show `suggested_leave` and `target_pickup` from pre-fetched data
- Show both kids' pickup details - clubs info if applicable
- If different end times, make it clear who's when
- Include club names and pickup locations when available
- Wednesday is late pickup (clubs run longer)
- If no clubs for a child, show standard pickup time and "Main gate"
