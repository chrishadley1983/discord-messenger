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
scheduled: false
conversational: true
channel: "#peterbot"
---

# Reminders

## Purpose

Manage one-off reminders for Chris. Reminders are stored in Supabase and delivered
by the Discord bot at the scheduled time.

## API Endpoints

Use the Hadley API at `http://172.19.64.1:8100`:

- `GET /reminders?user_id=<id>` - List pending reminders
- `POST /reminders` - Create reminder (body: `{task, run_at, user_id, channel_id}`)
- `PATCH /reminders/<id>` - Update reminder
- `DELETE /reminders/<id>` - Cancel reminder

**User/Channel IDs for Chris:**
- `user_id`: 141574217869243200
- `channel_id`: 1415741789758816369 (peterbot channel)

## Workflow

### Creating Reminders

1. **Parse the request** - Extract time, date, and task from natural language
2. **Smart confirmation:**
   - **Clear request** (specific time + recognizable task): Create immediately, confirm after
   - **Uncertain request** (missing time, vague task): Ask for clarification first
3. **Call POST /reminders** with parsed data
4. **Respond** with confirmation

### Listing Reminders

1. Call `GET /reminders?user_id=141574217869243200`
2. Format response showing date/time and task for each

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

### Clear Request (create immediately):
```
✅ **Reminder Set**

**When:** Sun 9 Feb 09:00 UK
**Task:** Check traffic to Brickstop
```

### Uncertain Request (ask first):
```
I'd like to set a reminder for you. Can you tell me:
- **When?** (e.g., "tomorrow at 9am", "Monday 2pm")
- **What?** (the task or message)
```

### List Reminders:
```
**Your Reminders:**

• Sun 9 Feb 09:00 — Check traffic to Brickstop
• Mon 10 Feb 08:00 — Submit tax return

To cancel: "cancel reminder [task description]"
```

### Cancelled:
```
✅ Cancelled reminder: Check traffic to Brickstop
```

### No Reminders:
```
No pending reminders. Say "remind me at [time] to [task]" to set one.
```

## Proactive Suggestions

Peter CAN suggest setting reminders when appropriate:
```
Would you like me to set a reminder for that? Just say "remind me at [time]"
```

But MUST wait for explicit confirmation before creating.

## Rules

1. Always use UK timezone for display and storage
2. For clear requests, create immediately - don't ask "is this correct?"
3. For uncertain requests, ask for missing information
4. Never create a reminder for proactive suggestions without user confirmation
5. When listing, sort by run_at (soonest first)
6. Include cancel instructions when listing reminders
7. Use short date format: "Sun 9 Feb 09:00"
