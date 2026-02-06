---
name: daily-thoughts
description: Sends end-of-day email digest of captured thoughts throughout the day
trigger:
  - "daily thoughts email"
  - "send daily thoughts"
scheduled: true
conversational: false
channel: #peterbot!quiet
---

# Daily Thoughts Email

## Purpose

Sends an email digest at 21:45 containing all thoughts Chris captured throughout the day. These are items he wants to address the next day.

## How It Works

1. **During the day**: Chris says "put that in the email" (or similar triggers)
2. **Skill adds bullet**: Appends a brief summary to `daily-thoughts-buffer.md`
3. **At 21:45**: Scheduler runs this skill, which:
   - Reads the buffer
   - Sends email via `/gmail/send`
   - Clears the buffer for next day

## Buffer Location

`/home/chris_hadley/peterbot/skills/daily-thoughts/daily-thoughts-buffer.md`

## Capture Triggers (handled by conversation)

When Chris says any of these, add a bullet to the buffer:
- "put that in the email"
- "add that to the email"
- "email that"
- "note that for tomorrow"
- "add to daily thoughts"

## Scheduled Execution (21:45)

1. Read buffer file
2. If empty: return `NO_REPLY`
3. If has content:
   - Format bullets nicely
   - Send email to Chris via `/gmail/send`
   - Clear buffer file
   - Confirm in channel (quietly)

## Email Format

```
Subject: Daily Thoughts - {date}

Hi Chris,

Here are the thoughts you captured today to address tomorrow:

{bullets}

— Peter
```

## Output Format (Discord)

On successful send:
```
NO_REPLY
```
(Silent operation — Chris gets the email, no Discord noise)

On empty buffer:
```
NO_REPLY
```

## Rules

- Always send to Chris's email (chrishadley1983@gmail.com)
- Keep bullets exactly as captured — don't over-summarize
- Clear buffer after sending
- Run silently (!quiet channel)
