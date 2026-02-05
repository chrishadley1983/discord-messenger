---
name: skill-name
description: Brief description of what this skill does
trigger:
  - "trigger phrase"
  - "another trigger"
scheduled: true
conversational: true
channel: #channel-name
---

# Skill Name

## Purpose

What this skill accomplishes and when it runs.

## Pre-fetched Data

Data injected by the scheduler before execution:
- `data.field1`: Description
- `data.field2`: Description

If no data is pre-fetched, use web search tools.

## Output Format

Expected format for Discord:

```
**Title** - Date

Content here with **bold** for emphasis.
Use bullet points for lists.

[Source links](url) if applicable.
```

## Rules

- Keep Discord-friendly (under 2000 chars unless splitting)
- Use emoji sparingly and appropriately
- Bold for emphasis, not headers
- If nothing to report, respond with just: `NO_REPLY`

## Examples

Example input and expected output.
