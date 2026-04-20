---
name: log-mobility
description: Log a morning or evening mobility routine (10-min stretch protocol)
trigger:
  - "done morning stretch"
  - "done evening stretch"
  - "done mobility"
  - "finished stretching"
  - "stretched"
  - "mobility done"
scheduled: false
conversational: true
channel: null
---

# Log Mobility

## Purpose

One-line logger for the daily mobility routine. Morning and evening slots
count separately — hitting both doesn't require hitting both, one per day
satisfies the daily habit.

## Workflow

1. **Detect slot** from Chris's message:
   - "morning" / "woke up" → `morning`
   - "evening" / "before bed" / "wind down" → `evening`
   - ambiguous → infer from current hour: before 12:00 = `morning`, after = `evening`

2. **POST**:
   ```
   POST http://172.19.64.1:8100/fitness/mobility
   {"slot": "morning", "duration_min": 10, "routine": "default"}
   ```

3. **Confirm** with streak + next recommendation.

## Output Format (morning)

```
✅ **Morning mobility logged** — 10 min

Both slots done today: ❌ evening still open
Daily mobility streak: 5 days 🔥
```

Or, if it's the second slot of the day:

```
✅ **Evening mobility logged** — 10 min

Both slots done today ✨
Daily mobility streak: 5 days 🔥
```

## Rules

- **NEVER say "Logged" without a successful POST.**
- The default mobility routine is: cat-cow, world's greatest stretch, couch stretch, pigeon, thoracic twist, child's pose, neck rolls (total 10 min).
- If Chris specifies a custom routine ("did pigeon + couch stretch for hips"), pass it in the `routine` field.
- The daily `fitness_mobility_today` accountability habit auto-ticks as soon as any slot is logged.
- For streak calc, read `GET /accountability/goals` and find the mobility goal's `current_streak`.
