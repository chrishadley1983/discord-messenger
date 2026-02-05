# Find Free Time

## Purpose
Find available time slots in calendar for scheduling.

## Triggers
- "when am I free", "find time for"
- "free slots", "available times"
- "can I fit in a {duration} meeting"
- "when's my next free {time period}"
- "schedule a meeting with {person}"

## Schedule
None (conversational only)

## Data Source
Google Calendar API via MCP server (freebusy query)

## Parameters
Extract from user message:
- `duration` - how long (default: 30 mins)
- `date_range` - when to look (default: next 5 working days)
- `time_constraints` - e.g., "morning", "after 2pm", "not Friday"
- `attendees` - if checking mutual availability (requires their calendar access)

## Output Format

**Finding free slots:**
```
📅 **Free slots for {duration} meeting:**

**Tomorrow (Tue 4th)**
• 09:00-10:00 ✓
• 14:30-17:00 ✓

**Wednesday 5th**
• All day free ✓

**Thursday 6th**
• 10:00-11:00 ✓
• 15:00-17:00 ✓
```

**If no slots found:**
```
📅 No {duration} slots available in the next {days} days.

Busiest days: Monday, Thursday
Suggestion: Try next week or a shorter meeting?
```

## Guidelines
- Default to working hours (09:00-17:30)
- Respect "focus time" blocks as busy
- Show 3-5 best options, not exhaustive list
- For "morning" = 09:00-12:00, "afternoon" = 13:00-17:30
- If user specifies attendee, check if we have calendar access
- Round to 30-minute boundaries

## Conversational
Yes - follow-ups:
- "What about next week?"
- "Show me afternoon slots only"
- "Is 2pm on Thursday free?"
- "Book the first slot" (→ triggers add-event skill)

## Example Interaction
**User:** "When can I fit in a 2-hour meeting this week?"
**Peter:** 📅 **Free 2-hour slots this week:**

**Wednesday 5th**
• 09:00-11:00 ✓
• 14:00-17:00 ✓

**Friday 7th**
• 10:00-12:00 ✓
• 14:00-16:00 ✓

Want me to block one of these?
