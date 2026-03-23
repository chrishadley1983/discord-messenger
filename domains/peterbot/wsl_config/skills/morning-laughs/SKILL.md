---
name: morning-laughs
description: Daily dad jokes and inspirational quote to start the day
trigger:
  - "tell me a joke"
  - "dad joke"
  - "morning laughs"
scheduled: true
conversational: true
channel: #peterbot
---

# Morning Laughs

## Purpose

Deliver 3 dad jokes and an inspirational quote first thing in the morning to start the day with a smile.

## Output Format

```
**☀️ Morning Laughs**

[Dad joke 1]

[Dad joke 2]

[Dad joke 3]

---

**💭 Daily Inspiration**

*"[Quote]"* — [Attribution]
```

## Rules

- Jokes should be family-friendly dad jokes (groan-worthy puns preferred)
- Vary the joke styles: puns, one-liners, question-and-answer format
- Rotate quote sources: mix business leaders, philosophers, athletes, writers
- Keep total message under 500 characters
- If triggered conversationally, generate fresh jokes on the spot

## Repeat Prevention (CRITICAL)

**History file:** `skills/morning-laughs/HISTORY.md`

This markdown file stores all previously used jokes and quotes. Simple, human-readable, survives session restarts.

**Before generating content:**
1. Read `skills/morning-laughs/HISTORY.md`
2. Check if your planned jokes/quote appear anywhere in the file (6-month window)
3. If match found, generate different content
4. NEVER repeat a joke or quote that appears in the history file

**After sending the message:**
1. Append each joke and the quote to `HISTORY.md` with today's date
2. Prune entries older than 6 months
3. Save the file
4. **Push today's jokes to the IHD dashboard** — call `POST http://192.168.0.110:3000/api/kids/jokes` with `{"jokes": [{"text": "joke 1"}, {"text": "joke 2"}, {"text": "joke 3"}]}`. This replaces the previous day's jokes so the kids see fresh ones each morning.

**History format (HISTORY.md):**
```markdown
# Morning Laughs History

## Jokes

- 2026-02-10: Why don't eggs tell jokes? They'd crack each other up.
- 2026-02-10: I used to hate facial hair, but then it grew on me.
- 2026-02-10: What do you call a fake noodle? An impasta.

## Quotes

- 2026-02-10: "The only way to do great work is to love what you do." — Steve Jobs
- 2026-02-09: "Success is not final, failure is not fatal..." — Winston Churchill
```

**Matching rules:**
- For jokes: match on similar punchlines or setups (don't repeat "I used to hate X but it grew on me" style)
- For quotes: match on exact quote text, same author allowed with different quotes

## Examples

**Scheduled output:**

**☀️ Morning Laughs**

Why don't eggs tell jokes? They'd crack each other up.

I used to hate facial hair, but then it grew on me.

What do you call a fake noodle? An impasta.

---

**💭 Daily Inspiration**

*"The only way to do great work is to love what you do."* — Steve Jobs
