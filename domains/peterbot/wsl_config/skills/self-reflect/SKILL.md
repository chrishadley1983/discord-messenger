---
name: self-reflect
description: Scheduled self-improvement review - add items to HEARTBEAT.md
trigger: []
scheduled: true
conversational: false
channel: "#alerts"
---

# Self-Reflect

## Purpose

3x daily (12:00, 18:00, 23:00 UK), review recent activity and add improvement items to HEARTBEAT.md.

## Context Sources

Think about what you've observed since the last reflection:

1. **Recent conversations**
   - What did people ask that you couldn't handle well?
   - What took longer than it should have?
   - What questions came up repeatedly?

2. **Errors & failures**
   - Tool calls that failed
   - APIs that timed out
   - Skills that produced poor output

3. **Patterns**
   - Requests that could become skills
   - Information you had to search for repeatedly
   - Workflows that could be automated

4. **Memory observations**
   - Info that seems outdated
   - Missing context that would have helped
   - Things worth remembering for next time

## Categories

Tag items with their type:

- `[SKILL]` - New skill or skill improvement (you can implement these!)
- `[INTEGRATION]` - New Hadley API endpoint needed (requires Chris - explain WHY)
- `[IDEAS]` - Speculative improvements worth exploring
- `[FIX]` - Bug or issue to address (try to fix it yourself first!)
- `[MEMORY]` - Observation to add/update in memory

**IMPORTANT:** You have full Claude Code capabilities. Most items you can implement yourself!
Only use `[INTEGRATION]` for Hadley API changes (Python FastAPI code you can't access).

When adding `[INTEGRATION]` items, you MUST include:
1. **What triggered this** - What was the user trying to do?
2. **Why it's needed** - What problem does this solve?
3. **Proposed endpoint** - What should the API look like?
4. **Current workaround** - What can be done without it?

## Process

1. **Review** the context sources above
2. **Identify** actionable improvements (be selective - quality over quantity)
3. **Update HEARTBEAT.md** - Add items under Pending with appropriate tags
4. **Post summary** to Discord

## Output

### If items to add:

```
📝 **Self-Reflect** (12:00)

**Added to HEARTBEAT.md:**

**To-Do:**
- [SKILL] Add error handling to morning-briefing when Garmin API times out
- [INTEGRATION] Research Audible API - asked about audiobook progress twice

**Ideas:**
- [SKILL] "what's for dinner" skill - could use FamilyFuel integration

**Won't Do:**
- Weather skill - already covered by school-run, not worth separate skill

---
_3 items added | Next: 18:00_
```

### If nothing to add:

```
📝 **Self-Reflect** (12:00)

No items to add.

---
_Next: 18:00_
```

## Rules

- Be selective - only add genuinely useful items
- Include reasoning in the item description
- "Won't Do" shows good judgment - use it when you considered something but decided against it
- Don't add items just to have something to report
- If the last reflection was recent and nothing's changed, "No items" is fine
- Update HEARTBEAT.md BEFORE posting the summary
