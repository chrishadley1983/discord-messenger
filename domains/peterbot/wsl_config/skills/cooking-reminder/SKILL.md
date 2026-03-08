---
name: cooking-reminder
description: Proactive cooking prep reminders for marinating, defrosting, and advance prep
trigger:
  - "cooking reminders"
  - "any prep needed"
  - "do I need to prep anything"
  - "what needs defrosting"
  - "anything to prep tonight"
scheduled: true
conversational: true
channel: "#food-log"
---

# Cooking Reminder

## Purpose

Send proactive reminders about cooking prep that needs advance action — marinating overnight, defrosting from freezer, soaking beans, starting the slow cooker. Runs twice daily (evening for tomorrow's prep, morning for today's defrost) and responds to conversational queries.

## Pre-fetched Data

Single data fetcher `cooking-reminder` that auto-detects timing based on time of day:

- `data.reminder_type` — `"morning"` or `"evening"` (set by the fetcher)
- `data.reminders` — List of prep actions needed
- `data.count` — Number of reminders

## Workflow

### Scheduled — Evening (20:45 UK)

`data.reminder_type` will be `"evening"`. Check `data.reminders` for night_before actions:

If reminders exist:
```
🍳 **Prep reminder for tomorrow**

Tomorrow you're making **Chicken Shawarma Wraps** — marinate the chicken tonight so it's ready to go.
```

Multiple reminders:
```
🍳 **Prep reminders for tomorrow**

- **Chicken Shawarma Wraps** — Marinate the chicken overnight
- **Slow-Cook Beef Stew** — Soak the beans tonight
```

If no reminders: respond with `NO_REPLY`

### Scheduled — Morning (07:30 UK)

`data.reminder_type` will be `"morning"`. Check `data.reminders` for morning actions:

If reminders exist:
```
🧊 **Defrost reminder**

Take the **mince** out of the freezer for tonight's **Bolognese**. Leave it in the fridge to thaw.
```

If no reminders: respond with `NO_REPLY`

### Conversational

When Chris asks "any prep needed?" or "what needs defrosting?":
1. Fetch both evening and morning reminders via `GET http://172.19.64.1:8100/meal-plan/reminders`
2. Present all active reminders
3. If none: "Nothing to prep — tonight's meal is ready to go as-is."

## Hadley API Endpoints

- `GET /meal-plan/reminders` — All reminders (today morning + tomorrow evening)
- `GET /meal-plan/reminders?timing=night_before` — Evening prep for tomorrow
- `GET /meal-plan/reminders?timing=morning` — Morning prep for today
- `GET /meal-plan/reminders?date=YYYY-MM-DD` — All reminders for a specific date

## Rules

- Keep reminders brief — one line per action
- `NO_REPLY` should be returned when there are no reminders (don't spam)
- Skip Gousto meals (ingredients come prepped in the box)
- Skip leftovers days (nothing to prep)
- If the recipe has no instructions in Family Fuel, skip it (can't analyse what we don't have)
- Evening reminder runs at 20:45 — after meal rating (20:30) and before nutrition summary (21:00)
- Morning reminder runs at 07:30 — early enough to defrost before work
- UK English, casual tone
