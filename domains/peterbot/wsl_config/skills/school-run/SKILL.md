---
name: school-run
description: Morning school run traffic report with weather and uniform requirements
trigger:
  - "school run"
  - "traffic"
  - "school traffic"
scheduled: true
conversational: true
channel: #traffic-reports
whatsapp: true
---

# School Run Report

## Purpose

Morning traffic report for school run. Posts to Discord AND WhatsApp.
- Monday, Tuesday, Wednesday, Friday: Job runs 8:10am, **arrive 8:38**
- Thursday: Job runs 7:45am, **arrive 7:58** (earlier start)

## CRITICAL RULES

1. **Use `target_arrival` from pre-fetched data** - This is the school arrival time (08:38 or 07:58), NOT the job schedule time (08:10 or 07:45). The job runs early to give warning time.

2. **Use `suggested_leave` from pre-fetched data** - This is pre-calculated based on traffic duration and target arrival.

3. **ALWAYS include rain section** - Show `rain_probability` from weather data with advice:
   - >50%: "🧥 Coats needed!"
   - 20-50%: "🌧️ Maybe grab coats"
   - <20%: "☀️ Should be dry"

4. **ALWAYS include uniform for BOTH kids** - Max and Emmie uniform info is in pre-fetched data.

5. **ALWAYS check `activities` array** - If not empty, show "Today's Activities" section listing each child's activity with club_name and notes.

6. **Do NOT call any APIs yourself** - All data is pre-fetched. Just format it.

## Pre-fetched Data Structure

```json
{
  "traffic": {
    "duration_in_minutes": 25,
    "route_name": "A26",
    "traffic_condition": "Moderate 🟡"
  },
  "weather": {
    "temp_c": 8,
    "condition": "Cloudy",
    "rain_probability": 30
  },
  "uniform": {
    "max": "🏃 PE day – PE kit needed",
    "emmie": "School uniform ✅"
  },
  "activities": [
    {"child_name": "Max", "club_name": "Piano", "pickup_time": null, "notes": "During school day"},
    {"child_name": "Emmie", "club_name": "Piano", "pickup_time": null, "notes": "During school day"}
  ],
  "target_arrival": "08:38",
  "suggested_leave": "08:11",
  "day_of_week": "Monday",
  "date": "2026-02-02"
}
```

## Output Format

```
🚗 **School Run** - Monday, 2 February

**Traffic:** 25 mins via A26 🟡
Leave by **08:11** to arrive **08:38**

**Weather:** 8°C, Cloudy
🌧️ 30% chance of rain - maybe grab coats

**Uniform:**
👦 Max: 🏃 PE day – PE kit needed
👧 Emmie: School uniform ✅

**Today's Activities:**
🎹 Max: Piano (During school day)
🎹 Emmie: Piano (During school day)

Have a good day! 🎒
```

**If no activities:** Omit the "Today's Activities" section entirely.

**School Events Today** (from `school_events_today` in pre-fetched data):
If events exist, add after activities:
```
**School Events Today:**
World Book Day - costumes needed!
Science Workshop (Year 2 + Year 4)
```

**INSET Day Detection** (from `is_inset_day` in pre-fetched data):
If `is_inset_day` is true, replace the ENTIRE report with:
```
**INSET DAY - No School Today!**
Enjoy the day off!
```

## Traffic Status Indicators

- 🟢 Clear (traffic adds <5 mins)
- 🟡 Moderate (5-10 mins added)
- 🔴 Heavy (>10 mins added)

## Rain Advice Thresholds

| Rain % | Advice |
|--------|--------|
| >50% | 🧥 Coats needed! |
| 20-50% | 🌧️ Maybe grab coats |
| <20% | ☀️ Should be dry |

## Rules

- Discord uses **bold** (double asterisk)
- Always show `suggested_leave` and `target_arrival` from pre-fetched data
- Always show `rain_probability` with appropriate advice
- Always show uniform for BOTH Max and Emmie
- **If `activities` array is not empty**, show "Today's Activities" section with each activity
- Keep it scannable - parents are rushed in the morning
- If traffic is heavy (🔴), make the leave time prominent
