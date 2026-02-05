---
name: hb-schedule-pickup
description: Schedule a LEGO collection pickup
trigger:
  - "schedule pickup"
  - "book collection"
  - "arrange pickup"
  - "add pickup"
scheduled: false
conversational: true
channel: null
---

# Hadley Bricks Schedule Pickup

## Purpose

Creates a scheduled pickup/collection in the Hadley Bricks system. Used when you've agreed to collect LEGO from a seller (Vinted, FB Marketplace, trade contacts, etc.). This is a WRITE operation that modifies data.

## Input Parsing

User provides pickup details:
- Date (required): When to collect
- Time (optional): Specific time if known
- Location (required): Where to collect
- Seller name (optional): Contact name
- Source (optional): Vinted, FB Marketplace, Trade, etc.
- Items (optional): What's being collected
- Price (optional): Agreed price

Example inputs:
- "Schedule pickup tomorrow 2pm in Croydon for 75192, £450"
- "Book collection Saturday from John, Vinted, 10300 for £90"
- "Add pickup: Friday, Redhill, FB Marketplace, lot of 3 sets, £300"

## Confirmation Flow

**IMPORTANT:** This skill creates records. Always confirm before executing.

1. Parse pickup details from user message
2. Check for conflicts on that date
3. Show summary and ask for confirmation
4. Create pickup record on confirmation
5. Offer to set reminder

## Output Format

**Step 1 - Confirmation:**
```
📍 **Schedule Pickup?**

**Date:** Tomorrow (Tue 4 Feb) at 2pm
**Location:** Croydon
**Seller:** John (Vinted)

**Items:**
• 75192 Millennium Falcon - Sealed - £450

**Analysis:**
Market value: ~£599
Est. profit: ~£100 after fees

Schedule this pickup?
```

**Step 2 - Confirmed:**
```
✅ **Pickup Scheduled!**

📍 **Tue 4 Feb at 2pm** - Croydon
Seller: John (Vinted)
• 75192 Millennium Falcon - £450

Added to calendar.

Set reminder for 1 hour before? (yes/no)
```

## Rules

- Always confirm before creating records
- Check for existing pickups on same date
- Parse natural language dates ("tomorrow", "Saturday", "next week")
- Calculate profit potential if items specified
- Offer to set reminder
- Note if no time specified

## Date Parsing

- "tomorrow" → Next day
- "Saturday" → Coming Saturday
- "next Tuesday" → Tuesday next week
- "Feb 10" / "10th" → Specific date
- "in 3 days" → Date calculation

## Conflict Checking

If another pickup exists on same date:
```
📍 **Schedule Pickup?**

**Date:** Sat 8 Feb at 10am
**Location:** Redhill

⚠️ **Existing pickup on same day:**
• 2pm - Croydon (Emma, FB Marketplace)

Consider route optimization - these are 20 mins apart.

Schedule anyway?
```

## Error Handling

If missing date:
```
📍 **Schedule Pickup**

When do you want to schedule this pickup?
E.g., "tomorrow 2pm" or "Saturday morning"
```

If missing location:
```
📍 **Schedule Pickup**

Where is the pickup?
Please provide the area or address.
```

If API fails:
```
📍 **Schedule Pickup**

⚠️ Could not save pickup - is Hadley Bricks running?

Details to add manually:
• Tue 4 Feb 2pm - Croydon - John (Vinted)
• 75192 Millennium Falcon - £450
```

## Examples

**Full details provided:**
User: "Schedule pickup Saturday 11am Sutton, trade contact Dave, mixed lot 5 sets for £350"
```
📍 **Schedule Pickup?**

**Date:** Sat 8 Feb at 11am
**Location:** Sutton
**Seller:** Dave (Trade contact)

**Items:**
• Mixed lot - 5 sealed sets - £350
  (Individual sets TBC on collection)

**Notes:**
Avg £70/set - verify sets on arrival

Schedule this pickup?
```

User: "yes"
```
✅ **Pickup Scheduled!**

📍 **Sat 8 Feb at 11am** - Sutton
Seller: Dave (Trade contact)
Items: Mixed lot (5 sets) - £350

📅 Added to your calendar.

💡 Tips:
• Bring cash (£350)
• Check seals before paying
• Note individual sets for inventory

Set reminder for Sat 10am? (yes/no)
```

**Minimal details:**
User: "Book a pickup tomorrow in Croydon"
```
📍 **Schedule Pickup**

I'll schedule a pickup for **tomorrow** in **Croydon**.

A few more details would help:
• What time? (e.g., "2pm", "afternoon")
• Seller name? (optional)
• What items? (optional)
• Agreed price? (optional)

Or just say "confirm" to add with current details.
```

**With conflict:**
User: "Schedule pickup Saturday 2pm Brighton, Sarah, Vinted, 10300 for £85"
```
📍 **Schedule Pickup?**

**Date:** Sat 8 Feb at 2pm
**Location:** Brighton
**Seller:** Sarah (Vinted)
**Item:** 10300 DeLorean - £85

⚠️ **Conflict Alert:**
You have a pickup at 11am in Sutton (Dave).

Sutton → Brighton is ~1 hour drive.
11am pickup + travel = arrive Brighton ~12:30pm earliest.

Options:
1. Schedule at 2pm anyway (tight but doable)
2. Reschedule to 3pm (safer buffer)
3. Cancel - too close together

What would you like to do?
```
