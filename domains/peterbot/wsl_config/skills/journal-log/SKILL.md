---
name: journal-log
description: Save a daily journal entry (thoughts for the day)
trigger:
  - "journal:"
  - "journal entry"
  - "diary:"
  - "today I"
  - "thoughts for today"
scheduled: false
conversational: true
channel: null
---

# Journal Log

## Purpose

Daily journal capture via conversation. Chris types a few lines and Peter
saves them as today's journal entry.

## Workflow

1. Extract the journal content from Chris's message:
   - "journal: Had a productive day, finished the tracker" → content after "journal:"
   - "diary: Feeling good about progress" → content after "diary:"
   - If Chris just says "journal entry", ask what he wants to write

2. Save it:
   ```
   POST http://172.19.64.1:8100/accountability/journal
   {"content": "Had a productive day, finished the tracker"}
   ```

3. Confirm briefly

## Output Format

```
Journal saved for today ✏️
```

## Rules

- One entry per day — writing again replaces the previous
- Don't summarise or edit Chris's words — save verbatim
- If the message is very short (<10 chars), ask if he wants to expand
- Keep confirmation to 1 line
