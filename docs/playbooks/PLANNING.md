# Planning Playbook

READ THIS before creating any plan, itinerary, schedule, or multi-step proposal.

## The Standard

Chris is a methodical planner. When he asks you to plan something, he wants a
structured, actionable plan — not vague suggestions. Plans should account for
real constraints and use available data sources.

## Before You Start

Gather context:
- Check /calendar for existing commitments and conflicts
- Check memory context for relevant personal details (who's involved, preferences)
- Check /weather/forecast if the plan is date-specific
- Check /directions for travel times between locations if relevant

## Plan Types

### Day Plan / Itinerary
- Time-blocked format: "09:00 — Activity (location, ~Xh)"
- Include travel times between locations (use /directions)
- Account for meals and rest stops
- Weather-aware: flag rain risks or extreme temperatures
- End with "Booking/prep needed" checklist

### Week Plan / Schedule
- Day-by-day grid format
- Distinguish fixed events (from calendar) vs flexible slots
- Highlight clashes or overloaded days
- Balance intensity (don't stack every day)

### Project Plan / Multi-Step
- Numbered steps with clear dependencies
- Estimated effort per step
- Decision points clearly marked with ❓
- "Start with" recommendation

## What GOOD Looks Like

🗾 **[Location] Day Plan — [Date]**

🌤️ Forecast: [from /weather]

📍 **09:00** — [Activity] (~Xh)
[How to get there] | [Kid/family notes if relevant]

📍 **11:30** — [Lunch option]
💰 [Price range + currency] | [Booking requirement]

📍 **13:00** — [Afternoon activity]
[Practical detail: tickets, queues, alternatives]

📋 **Needs prep:**
- [ ] Actionable checklist items

## What BAD Looks Like

❌ "You could visit X, then maybe Y, and there are some good restaurants
in the area." (no times, no logistics, no detail)
❌ A plan that ignores travel time between locations
❌ Suggestions without prices or booking requirements

## Key Principle

Every plan should be actionable enough that it could be handed to someone
else and executed without further research.

---

## Hadley API Endpoints

Base URL: `http://172.19.64.1:8100`

### Calendar

| Query | Endpoint | Method |
|-------|----------|--------|
| Today's events | `/calendar/today` | GET |
| This week | `/calendar/week` | GET |
| Date range | `/calendar/range?start_date=...&end_date=...` | GET |
| Find free time | `/calendar/free?date=...&duration=60` | GET |
| Create event | `/calendar/create?summary=...&start=2026-02-05T14:00` | POST |
| Get event | `/calendar/event?id=...` | GET |
| Update event | `/calendar/event?id=...&summary=New+Title` | PUT |
| Delete event | `/calendar/event?id=...` | DELETE |
| Search events | `/calendar/search?q=dentist` | GET |
| Quick add | `/calendar/quickadd?text=Lunch+Friday+at+noon` | POST |
| Next event | `/calendar/next` | GET |
| Check conflicts | `/calendar/conflicts?start=...&end=...` | GET |
| Create recurring | `/calendar/recurring?summary=Gym&start_time=07:00&days=MO,WE,FR&end_date=2026-07-31&color_id=7&transparency=transparent&exclude_dates=2026-04-07,2026-04-14` | POST |
| Invite attendee | `/calendar/invite?event_id=...&email=...` | POST |
| List calendars | `/calendar/calendars` | GET |
| Check busy | `/calendar/busy?email=...&date=...` | GET |

### Peter Tasks (ptasks)

| Query | Endpoint | Method |
|-------|----------|--------|
| List tasks | `/ptasks?list_type=personal_todo` | GET |
| Task counts | `/ptasks/counts` | GET |
| Create task | `/ptasks` (body: `{list_type, title, priority?, description?}`) | POST |
| Update task | `/ptasks/{task_id}` | PUT |
| Change status | `/ptasks/{task_id}/status` (body: `{status}`) | POST |
| Get task | `/ptasks/{task_id}` | GET |
| Add comment | `/ptasks/{task_id}/comments` (body: `{content}`) | POST |
| Heartbeat plan | `/ptasks/heartbeat/plan` | GET |

**List types:** `personal_todo`, `peter_queue`, `idea`, `research`
**Priorities:** `critical`, `high`, `medium`, `low`, `someday`

## Trigger Phrases

- "What's on my calendar?" → `/calendar/today` or `/calendar/week`
- "What's on next week?" → `/calendar/range?start_date=...&end_date=...`
- "Add dentist at 2pm Thursday" → `/calendar/create?summary=Dentist&start=...`
- "Move that meeting to 3pm" → `/calendar/event` (PUT)
- "Cancel the appointment" → `/calendar/event` (DELETE)
- "Am I free tomorrow?" → `/calendar/free?date=...`
- "What's my next event?" → `/calendar/next`
- "Am I double-booked at 2pm?" → `/calendar/conflicts?start=...&end=...`
- "Add gym every Monday and Wednesday at 7am" → `/calendar/recurring`
- "Invite Sarah to the meeting" → `/calendar/invite`
- "What calendars do I have?" → `/calendar/calendars`
- "Is Sarah free tomorrow?" → `/calendar/busy?email=...`
- "What's on my todo list?" → `/ptasks?list_type=personal_todo`
- "What are my tasks?" → `/ptasks/counts` then `/ptasks?list_type=...`
- "Add task: call dentist" → POST `/ptasks` with `{list_type: "personal_todo", title: "Call dentist"}`
- "Mark that task as done" → POST `/ptasks/{id}/status` with `{status: "done"}`
- "Log a bug" / "Add to Peter's queue" → POST `/ptasks` with `{list_type: "peter_queue", title: "..."}`
- "I have an idea" → POST `/ptasks` with `{list_type: "idea", title: "..."}`
