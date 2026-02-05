---
name: heartbeat
description: Health check and to-do list processing
trigger: []
scheduled: true
conversational: false
channel: #peter-heartbeat
---

# Heartbeat

## Purpose

Every 30 minutes, check system health and work on to-do items.

## Process

### 1. Health Checks

Run these checks:
- **Session responsive**: Can you execute commands? (You're running, so yes)
- **Memory endpoint**: `curl http://localhost:37777/health` - should return OK

If any check fails → Include failure in status output

### 2. To-Do Processing (if healthy)

Read the file `HEARTBEAT.md` in your working directory and look for pending items.

**Path:** `./HEARTBEAT.md` (same directory as this skill)

If there's a pending item:
1. Move it to "In Progress" in the file
2. Work on it until done (search, create files, etc.)
3. When complete, move to "Done" with today's date
4. Use dual-channel output format (see below)

## Output Format

### ALWAYS output a status (never NO_REPLY)

**Heartbeat-only (no pending tasks):**
```
💚 **Heartbeat** - [time]
Health: ✅ | Memory: ✅ | No pending tasks
```

**Health issue:**
```
🔴 **Heartbeat** - [time]
Health: ✅ | Memory: ❌ | Check failed: [reason]
```

**With task completion - USE DUAL-CHANNEL FORMAT:**
```
---HEARTBEAT---
💚 **Heartbeat** - [time]
Health: ✅ | Memory: ✅ | Completed: [task name]
---PETERBOT---
[Full task output here - research results, created files, etc.]

HEARTBEAT.md updated ✓
```

## Dual-Channel Routing

When you complete a task, use the `---HEARTBEAT---` and `---PETERBOT---` markers:
- Content after `---HEARTBEAT---` goes to #peter-heartbeat (brief status)
- Content after `---PETERBOT---` goes to #peterbot (full results)

This keeps the heartbeat channel clean (status only) while delivering useful content to the main channel.

## Rules

- **ALWAYS output something** - no more NO_REPLY
- Health checks first, quick verification only
- If pending to-do items exist, pick ONE and work on it
- **TRY TO IMPLEMENT IT YOURSELF** - You have full Claude Code capabilities!
- Only punt to Chris if it genuinely requires Hadley API changes or core bot code
- Work until done, don't stop mid-task
- Update HEARTBEAT.md as you work (move items between sections)
- Use dual-channel format when completing tasks
- Keep heartbeat status brief (one line)
- Put detailed results in the PETERBOT section
- Follow PETERBOT_SOUL.md for research quality

## Implementation vs Escalation

**You CAN do:**
- Create/modify skill files
- Write documentation
- Create scripts and tools
- Research and synthesize information
- Fix bugs in skill definitions

**Needs Chris:**
- Hadley API endpoints (FastAPI code)
- Bot core code (bot.py, router.py)
- SCHEDULE.md changes
- Deployments

If escalating, explain: WHY needed, WHAT problem it solves, PROPOSED solution

## Output Cleanliness

**Your response IS what gets posted to Discord.**

- Do NOT show edit diffs, line numbers, or `Update(file)` output
- Do NOT narrate "I'll update the file now..." - just do it
- ONLY output the final formatted result (see examples above)
- The "HEARTBEAT.md updated ✓" line goes in PETERBOT section if dual-channel

## Time Format

Use 24-hour UK time: `09:30`, `14:45`, etc.
Get current time from pre-fetched data or system.

## Asking Questions

If you encounter something that needs Chris's input:
- **ASK DIRECTLY** in the PETERBOT section
- Use format: `❓ **Question:** [clear question here]?`
- Don't bury questions as statements

## Examples

**Example 1: No tasks**
```
💚 **Heartbeat** - 09:30
Health: ✅ | Memory: ✅ | No pending tasks
```

**Example 2: Task completed**
```
---HEARTBEAT---
💚 **Heartbeat** - 14:00
Health: ✅ | Memory: ✅ | Completed: Japan travel research
---PETERBOT---
🇯🇵 **Japan Travel Research**

**Best time to visit:**
- Spring (late March - early May): Cherry blossoms
- Fall (September - November): Autumn colors, mild weather

**Tips:**
- Avoid Golden Week (late April - early May)
- JR Pass: Calculate per itinerary, regional passes often better
- Book popular spots 12 months ahead

HEARTBEAT.md updated ✓
```
