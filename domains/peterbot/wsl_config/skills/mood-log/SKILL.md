---
name: mood-log
description: Log daily mood score (1-10) with optional note
trigger:
  - "mood"
  - "feeling"
  - "how I feel"
  - "mood score"
scheduled: false
conversational: true
channel: null
---

# Mood Log

## Purpose

Quick mood logging via conversation. Chris says "mood 7" or "feeling great, 8"
and Peter logs it to the accountability tracker.

## Workflow

1. Parse the score (1-10) and optional note from Chris's message:
   - "mood 7" → score=7, no note
   - "mood 7 — feeling productive" → score=7, note="feeling productive"
   - "feeling great, 8" → score=8, note="feeling great"
   - "feeling rough" → ask for a number

2. Log it:
   ```
   POST http://172.19.64.1:8100/accountability/mood
   {"score": 7, "note": "feeling productive"}
   ```

3. Show confirmation with week context:
   ```
   GET http://172.19.64.1:8100/accountability/mood
   ```

## Output Format

```
Logged: 7/10 — feeling productive

This week: avg 6.8 ↑ | ● ● ● ○ ● ● ●
```

## Rules

- Score must be 1-10. If Chris gives a number outside range, ask to clarify
- If no number given but a feeling word, suggest a score and confirm
- One entry per day — logging again updates (doesn't duplicate)
- Keep response to 2-3 lines max
