---
name: daily-batch
description: Generate the day's hydration check-ins and cooking reminders in one batch (cost optimisation)
scheduled: true
conversational: false
channel: "#peter-heartbeat!quiet"
---

# Daily Message Batch

## Purpose

One Claude call each morning (06:55) writes ALL of today's fixed-format messages to a batch file. The scheduler then posts them through the day with **zero further LLM calls**, substituting live numbers at post time. This replaced 15 hydration calls + 2 cooking calls per day (~34% of total LLM spend).

## Pre-fetched Data

```json
{
  "date": "2026-06-10",
  "water_target": 3500,
  "steps_target": 15000,
  "cooking_morning": {"count": 1, "reminders": ["Defrost the chicken for tonight's curry"]},
  "cooking_evening": {"count": 1, "reminders": ["Soak the beans for tomorrow's chilli"]}
}
```

## Task

Write the file `/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/domains/peterbot/wsl_config/data/daily_batch.json` (use the Write tool — this EXACT absolute path; do NOT write to ~/peterbot/data/, which is a separate directory the scheduler never reads) with this exact structure, then reply `NO_REPLY`.

```json
{
  "date": "<the date from pre-fetched data>",
  "hydration": {
    "07": "<full message template>",
    "08": "...",
    "09": "...", "10": "...", "11": "...", "12": "...", "13": "...",
    "14": "...", "15": "...", "16": "...", "17": "...", "18": "...",
    "19": "...", "20": "...", "21": "..."
  },
  "cooking": {
    "morning": "<full message or null if no morning reminders>",
    "evening": "<full message or null if no evening reminders>"
  }
}
```

### Hydration message templates

Each hour's message MUST follow this structure, using these literal placeholders (the scheduler substitutes live values at post time — do NOT fill in numbers yourself):

```
{emoji} **{HH}:00 Check-in**

💧 **Water:** {water_ml} / {water_target} ({water_pct}%)
{water_bar}

🚶 **Steps:** {steps} / {steps_target} ({steps_pct}%)
{steps_bar}

---
<Motivational message — 2-3 sentences, written by YOU now>
```

Rules for the motivational lines:
- Vary all 15 — no two should feel alike. Peter's voice: warm, dry-witted, occasionally cheeky.
- Make them time-aware: 07:00 is a fresh start; 12:00-14:00 reference lunch/midday slump; 17:00-19:00 reference the home straight; 21:00 is the last call — wrap up the day.
- Pick a fitting emoji per hour instead of `{emoji}` (☀️ morning, 🌤️/💪 midday, 🌆 evening, 🌙 21:00).
- Replace `{HH}` with the actual hour (07-21). Keep every other `{placeholder}` EXACTLY as written, curly braces included.

### Cooking messages

Use the pre-fetched reminders. Write the complete message (no placeholders):
- Morning (posts 07:30): today's defrost/prep reminders, e.g. "🍳 **Cooking prep** — get the chicken out of the freezer for tonight's curry."
- Evening (posts 20:45): tomorrow's night-before prep.
- If a slot has `count: 0`, set it to `null` — the scheduler will skip that post.

## Output

After writing the file, reply with exactly `NO_REPLY`. Do not post the batch content to the channel.
