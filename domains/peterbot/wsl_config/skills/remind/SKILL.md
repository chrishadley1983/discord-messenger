---
name: remind
description: Set, list, update, and cancel reminders via Hadley API
trigger:
  - "remind me"
  - "set a reminder"
  - "list reminders"
  - "cancel reminder"
  - "my reminders"
  - "update reminder"
  - "delete reminder"
  - "/remind"
scheduled: false
conversational: true
channel: "#peterbot"
---

# Reminders

## Purpose

Manage one-off reminders for Chris. Reminders are stored in Supabase and delivered
by the Discord bot at the scheduled time.

**Important**: Only create reminders when Chris explicitly asks for a reminder.
Messages about diary events, calendar entries, or tasks are NOT reminders — route
those to the appropriate skill (calendar, tasks, etc.).

## API Endpoints

Use the Hadley API at `http://172.19.64.1:8100`:

- `GET /reminders?user_id=<id>` — List pending reminders
- `POST /reminders` — Create reminder (body: `{task, run_at, user_id, channel_id}`)
- `PATCH /reminders/<id>` — Update reminder (body: `{task?, run_at?}`)
- `DELETE /reminders/<id>` — Cancel reminder

**User/Channel IDs for Chris:**
- `user_id`: 141574217869243200
- `channel_id`: 1415741789758816369 (peterbot channel)

## Workflow

### Creating Reminders

1. **Parse the request** — Extract time, date, and task from natural language
2. **ALWAYS confirm before creating** — Show what you understood and ask for approval:
   ```
   I'll set this reminder:
   - **When:** Thu 12 Feb 18:00 UK
   - **Task:** Check traffic to Brickstop

   Shall I go ahead?
   ```
3. **Only after Chris confirms** → Call `POST /reminders` with parsed data
4. **Respond** with confirmation

### Listing Reminders

1. Call `GET /reminders?user_id=141574217869243200`
2. Format response showing date/time and task for each

### Updating Reminders

1. List reminders so Chris can identify which one
2. Confirm the change before applying
3. Call `PATCH /reminders/<id>` with updated fields

### Cancelling Reminders

1. If user specifies task text, search reminders by task
2. If user specifies ID, use that directly
3. Call `DELETE /reminders/<id>`
4. Confirm deletion

## Time Parsing Rules

| Input | Interpretation |
|-------|----------------|
| "9am tomorrow" | Tomorrow at 09:00 UK |
| "at 2pm" | Today at 14:00 if future, else tomorrow |
| "Monday 8am" | Next Monday at 08:00 |
| "in 2 hours" | Current time + 2 hours |
| "15th Feb 10am" | 15th February at 10:00 |

Always use UK timezone (Europe/London).

## Output Formats

### Confirm before creating:
```
I'll set this reminder:
- **When:** Sun 9 Feb 09:00 UK
- **Task:** Check traffic to Brickstop

Shall I go ahead?
```

### After creation confirmed:
```
Reminder set for Sun 9 Feb 09:00 UK — Check traffic to Brickstop
```

### List Reminders:
```
**Your Reminders:**

- Sun 9 Feb 09:00 — Check traffic to Brickstop
- Mon 10 Feb 08:00 — Submit tax return

To cancel: "cancel reminder [task description]"
```

### Cancelled:
```
Cancelled reminder: Check traffic to Brickstop
```

### No Reminders:
```
No pending reminders. Say "remind me at [time] to [task]" to set one.
```

## Distinguishing Reminders from Other Requests

**IS a reminder request:**
- "Remind me at 9am to check traffic"
- "Set a reminder for Monday"
- "/remind 2pm take meds"

**Is NOT a reminder request (route to correct skill):**
- "Add dinner to my diary for Thursday" → calendar skill
- "Put X on my to-do list" → task skill
- "Book a meeting for 3pm" → calendar skill

When in doubt, ask Chris: "Would you like this as a reminder, or added to your calendar/tasks?"

## Rules

1. Always use UK timezone for display and storage
2. **ALWAYS confirm before creating** — never auto-create from ambiguous messages
3. For uncertain requests, ask for missing information
4. Never create a reminder without Chris's explicit approval
5. When listing, sort by run_at (soonest first)
6. Include cancel instructions when listing reminders
7. Use short date format: "Sun 9 Feb 09:00"
