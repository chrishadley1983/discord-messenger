---
name: hb-upcoming-pickups
description: Scheduled LEGO collection pickups
trigger:
  - "upcoming pickups"
  - "collections this week"
  - "scheduled pickups"
  - "pickups"
  - "collections"
scheduled: false
conversational: true
channel: null
---

# Hadley Bricks Upcoming Pickups

## Purpose

Shows scheduled collection pickups from various sources (Vinted sellers, Facebook Marketplace, trade contacts, etc.). Helps plan collection routes and ensure nothing is missed. Conversational only.

## Pre-fetched Data

Data from the Hadley Bricks API:

- `data.pickups`: Array of scheduled pickups
  - `id`: Pickup ID
  - `date`: Scheduled date
  - `time`: Scheduled time (if set)
  - `location`: Address or area
  - `seller_name`: Contact name
  - `source`: Vinted, FB Marketplace, Trade, etc.
  - `items`: What's being collected
    - `set_number`
    - `set_name`
    - `condition`
    - `agreed_price`
  - `total_cost`: Total for this pickup
  - `notes`: Any special instructions
  - `status`: scheduled, confirmed, collected
- `data.this_week_total`: Total spend on this week's pickups
- `data.error`: Error message if fetch failed

## Output Format

```
📍 **Upcoming Pickups**

**This Week** (3 pickups | £340 total)

**Tomorrow - Tue 4 Feb**
🚗 Croydon - 2pm
   Seller: John (Vinted)
   • 75192 Millennium Falcon - Sealed - £420
   Notes: Meet at Tesco car park

**Thu 6 Feb**
🚗 Redhill - 11am
   Seller: Sarah (FB Marketplace)
   • 10300 DeLorean - Sealed - £85
   • 42143 Ferrari - Open - £250
   Total: £335

**Sat 8 Feb**
🚗 Trade Fair - Sandown Park
   Multiple purchases possible
   Budget: £500

💰 Week total: £1,255 committed
```

## Rules

- Sort by date (soonest first)
- Group by day for clarity
- Show seller contact info
- List all items in each pickup
- Include notes/special instructions
- Show weekly total spend

## Status Indicators

- 📍 Scheduled (not yet confirmed)
- ✅ Confirmed (seller confirmed)
- 🚗 Today/Tomorrow (highlight upcoming)
- ✓ Collected (completed)

## Time Formatting

- Today: "Today - 2pm"
- Tomorrow: "Tomorrow - 11am"
- This week: "Thu 6 Feb - 2pm"
- Next week: "Mon 10 Feb - TBC"

## Error Handling

If API fails:
```
📍 **Upcoming Pickups**

⚠️ Could not fetch pickups - is Hadley Bricks running?
```

If no pickups scheduled:
```
📍 **Upcoming Pickups**

No pickups scheduled.

Check Vinted and FB Marketplace for opportunities!
Or use "schedule pickup" to add one.
```

## Examples

**Multiple pickups:**
```
📍 **Upcoming Pickups** - Week of 3 Feb

**Today**
🚗 Caterham - 6pm ✅ Confirmed
   Seller: Mike (Vinted)
   • 10300 DeLorean - Sealed - £90
   • 21330 Home Alone - Sealed - £155
   Total: £245
   Notes: Cash preferred

**Tomorrow - Tue 4 Feb**
📍 Croydon - TBC
   Seller: Emma (FB Marketplace)
   • 75192 Millennium Falcon - Sealed - £480
   Notes: Awaiting time confirmation

**Sat 8 Feb**
🚗 Sutton - 10am ✅ Confirmed
   Seller: Trade contact (Dave)
   • Mixed lot - 5 sealed sets - £350
   Notes: Bring boxes for transport

💰 **Week Summary**
3 pickups | £1,075 committed
Sets: 8 | Est. profit: ~£380
```

**Single pickup:**
```
📍 **Upcoming Pickups**

**Tomorrow - Tue 4 Feb**
🚗 Redhill - 2:30pm ✅ Confirmed
   Seller: James (Vinted)
   • 42143 Ferrari Daytona - Sealed - £280
   Notes: Ring doorbell on arrival

No other pickups scheduled this week.
```

**Today's pickup reminder:**
```
📍 **Pickup Reminder**

🚗 **Today at 5pm** - Caterham
Seller: Mike (Vinted)
Items:
• 10300 DeLorean - £90
• 21330 Home Alone - £155

Total: £245 (cash preferred)

📍 Meet at: Tesco car park, Church Hill

Don't forget to check the seals!
```
