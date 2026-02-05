# Brickstop Traffic

## Purpose
One-time traffic update for Brickstop Cafe trip (Sunday 1st Feb 2026).

## Triggers
None (scheduled only, one-time use)

## Schedule
- Sun 09:00 UK (ONE-TIME - delete after execution)

## Data Source
Hadley API: `curl "http://172.19.64.1:8100/directions?destination=26+Godstone+Rd+Caterham+CR3+6RA"`

## Output Format

```
🚗 **Brickstop Traffic Update**

**Route:** Home → Brickstop Cafe, Caterham
**Distance:** {distance_km} km
**Current estimate:** {duration_mins} mins

Booking at 10:15 AM → Leave by {leave_time}

---
_One-time reminder - delete from SCHEDULE.md_
```

## Rules
- Fetch live directions from Hadley API
- Calculate recommended leave time (arrival 10 mins before booking)
- Post to both Discord and WhatsApp
- After this runs, mark for deletion from schedule

## Cleanup
After running, add to HEARTBEAT.md:
- [FIX] Remove brickstop-traffic from SCHEDULE.md (one-time job completed)
