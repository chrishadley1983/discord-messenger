---
name: log-workout
description: Log a completed bodyweight workout session from natural language
trigger:
  - "done push workout"
  - "done legs workout"
  - "finished workout"
  - "logged workout"
  - "just did my push session"
  - "completed push"
  - "completed legs"
  - "finished legs a"
  - "finished legs b"
  - "finished pull"
  - "finished full body"
scheduled: false
conversational: true
channel: null
---

# Log Workout

## Purpose

Log a completed strength session from conversational input like
"done push workout" or "finished legs b — felt good, RPE 7".

## Workflow

1. **Detect session type** from Chris's message:
   - "push" → `push`
   - "legs a" / "quads" → `legs_a`
   - "pull" / "pull core" → `pull_core`
   - "legs b" / "posterior" → `legs_b`
   - "full body" / "conditioning" → `full_body`

2. **Fetch today's prescription** to get the expected sets/reps:
   ```
   curl -s http://172.19.64.1:8100/fitness/today
   ```

3. **Default to the prescription**: if Chris didn't specify reps, log the prescribed
   sets/reps as the actual. If he did (e.g. "did 12 push-ups instead of 11"),
   override per-exercise.

4. **Parse optional RPE and notes**: "RPE 7", "felt strong", "struggled on dips".

5. **POST to the workout endpoint**:
   ```
   POST http://172.19.64.1:8100/fitness/workout
   {
     "session_type": "push",
     "duration_min": 20,
     "rpe": 7,
     "notes": "felt strong",
     "sets": [
       {"exercise_slug": "push-up", "set_no": 1, "reps": 11},
       {"exercise_slug": "push-up", "set_no": 2, "reps": 11},
       {"exercise_slug": "push-up", "set_no": 3, "reps": 11},
       ...
     ]
   }
   ```

6. **Confirm back**: show what was logged + the streak count + a motivator.

## Output Format

```
✅ **Push session logged** — Week 2, Day 14

3×11 push-up | 3×7 pike push-up | 3×11 chair dip | 2×7 diamond push-up | 2×50s plank
RPE 7 | 20 min

**Week 2 strength**: 3 / 5 sessions done 💪
**Streak**: 4 consecutive planned sessions ✅

[1-line nudge — progress vs the next session, or rest/recovery reminder]
```

## Rules

- **NEVER say "Logged" without executing the POST and getting a 200 back.**
- If the session type can't be confidently detected, ask before logging.
- If Chris gave exact per-exercise reps, honour them. Never pretend he hit the prescription.
- Always show the RPE if provided.
- After logging, the weekly strength accountability goal auto-updates via `fitness_strength_week`.
- For a PR (any exercise beat the previous session), call it out explicitly: `🎉 PR: push-up 3×11 (prev 3×10)`.
