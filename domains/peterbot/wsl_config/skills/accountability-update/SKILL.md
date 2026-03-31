---
name: accountability-update
description: Log progress or check status on accountability goals via conversation
trigger:
  - "update my goal"
  - "update goal"
  - "goal status"
  - "goal progress"
  - "how are my goals"
  - "accountability"
  - "log progress"
scheduled: false
conversational: true
channel: null
---

# Accountability Update

## Purpose

Conversational interface for Chris to log progress against his goals or check status.
Handles natural language like "I did 12k steps today" or "saved another £200".

## Workflow

1. **Fetch active goals:**
   ```
   GET http://172.19.64.1:8100/accountability/goals
   ```

2. **Match Chris's input to a goal:**
   - Parse the value and unit from his message
   - Match to the most likely goal by metric/category
   - If ambiguous (multiple possible matches), ask which goal

3. **Log the progress:**
   ```
   POST http://172.19.64.1:8100/accountability/goals/{id}/progress
   {"value": 12000, "source": "peter_chat", "note": "Chris reported via chat"}
   ```

4. **Show updated status** in the reply with progress bar and streak info

## Status Check (no value given)

If Chris asks "how are my goals" or "goal status" without a value:

```
GET http://172.19.64.1:8100/accountability/summary
```

Show a compact overview of all active goals.

## Output Format

After logging:
```
Logged! 12,000 steps today

🏃 **10k Steps Daily**
▓▓▓▓▓▓▓▓▓▓ 120% | Streak: 14 days 🔥
```

For status check:
```
🎯 **Your Goals**

🏃 10k Steps — 11,200 today | ▓▓▓▓▓▓▓▓░░ 112% | 🔥 14 days
⚖️ Hit 80kg — 81.8kg | ▓▓▓▓▓▓▓▓░░ 76% | ↓ on track
💧 2L Water — 1,400ml | ▓▓▓▓▓▓▓░░░ 70%
```

## Boolean Habits

For goals with `metric: "boolean"` (e.g. "No Doom Scrolling"):
- "done with no doom scrolling" / "yes on meditation" → log value=1
- "missed meditation" / "failed no doom scrolling" → log value=0

```
POST http://172.19.64.1:8100/accountability/goals/{id}/progress
{"value": 1, "source": "peter_chat"}
```

After logging:
```
✓ No Doom Scrolling — done! Streak: 4 days 🔥
```

## Rules

- Always confirm what was logged with the actual value
- Use the goal's metric for formatting (steps = comma-separated, kg = 1dp, ml = no dp, £ = currency)
- Show streak with fire emoji if 3+ days
- If a milestone is newly reached, celebrate it
- Keep responses compact — this is chat, not a report
- If Chris says "I ran 5k" match to a running/steps goal, not a savings goal
