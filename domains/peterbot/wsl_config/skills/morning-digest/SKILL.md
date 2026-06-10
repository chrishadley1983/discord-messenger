---
name: morning-digest
description: Consolidated 07:00 morning digest — day ahead, weather, inbox, todos, GitHub
trigger:
  - "morning digest"
  - "what's my morning look like"
  - "daily digest"
scheduled: true
conversational: true
channel: "#peterbot"
---

# Morning Digest

## Purpose

ONE well-composed morning message replacing four separate jobs (email summary, schedule today, Notion todos, GitHub activity). Part of the 2026-06 morning consolidation: Chris gets 3–4 curated messages instead of a ~18-message flood.

## Pre-fetched Data

`data` contains five sections (each may carry an `error` key — degrade gracefully, never show raw errors):
- `schedule` — today's calendar events
- `email` — unread inbox summary
- `todos` — open personal todos (ptasks `personal_todo` list)
- `github` — yesterday's GitHub activity
- `weather` — current conditions for Tonbridge

## Output Format

**CRITICAL RULES:**
1. Output ONLY the formatted message — no preamble, no reasoning.
2. ONE message. Keep it scannable — this replaces four messages, not concatenates them.
3. Omit any section with nothing meaningful to say (no "no emails" filler). An empty section is silence, not a line.
4. Lead with what matters most TODAY (an early meeting beats inbox count).

```
☀️ **Morning, Chris** — {weather one-liner: temp, condition, umbrella/coat hint if relevant}

📅 **Today**
{calendar events as bullet lines with times — flag the first/most important one}

📧 **Inbox** — {unread_count} unread, {n} worth a look
{only emails that actually need attention, one line each}

✅ **Todos**
{top 3-5 open personal todos (ptasks), most urgent first}

🐙 **GitHub** — {one-line summary of yesterday's commits/PRs across repos, only if there was activity}
```

## Guidelines

- Total length: aim under 25 lines. Brutal prioritisation beats completeness — everything is queryable on demand.
- Weather is one line woven into the greeting, not a section.
- If the calendar is empty on a weekday, say so in one relaxed line ("Clear calendar today").
- Peter's voice: warm, succinct, slightly dry. No corporate briefing tone.
