---
name: hydration
description: Post water intake and step progress with motivation
trigger:
  - "water"
  - "hydration"
  - "how much water"
  - "steps"
scheduled: true
conversational: true
channel: #food-log
---

# Hydration Check-in

## Purpose

Hourly check-in (7am-9pm UK) with water intake and step progress. Target: 250ml per hour. Provide contextual motivation based on time of day and progress.

## Pre-fetched Data

```json
{
  "water_ml": 1500,
  "water_target": 3500,
  "water_pct": 42.8,
  "steps": 6500,
  "steps_target": 15000,
  "steps_pct": 43.3,
  "hour": 13,
  "time_of_day": "afternoon",
  "hours_until_9pm": 8
}
```

## Output Format

**CRITICAL RULES - MUST FOLLOW:**
1. Output ONLY the formatted message below
2. NO chain-of-thought reasoning (never start with "Looking at...", "I should...", etc.)
3. NO preamble or explanations before the response
4. NO analysis of the data visible to the user
5. Just output the formatted response directly

```
☀️ **13:00 Check-in**

💧 **Water:** 1,500ml / 3,500ml (43%)
▓▓▓▓░░░░░░

🚶 **Steps:** 6,500 / 15,000 (43%)
▓▓▓▓░░░░░░

---
[Motivational message - 2-3 sentences, context-aware]
```

## Progress Bar Calculation

**MUST include progress bars.** Use ▓ for filled, ░ for empty. Always 10 characters total.

Formula: `filled = round(percentage / 10)`

Examples:
- 14% → 1 filled → `▓░░░░░░░░░`
- 43% → 4 filled → `▓▓▓▓░░░░░░`
- 80% → 8 filled → `▓▓▓▓▓▓▓▓░░`
- 0% → 0 filled → `░░░░░░░░░░`

## Rules

- Match energy to time of day:
  - Morning (9am-12pm): Encouraging start
  - Afternoon (12pm-5pm): Progress check, keep momentum
  - Evening (5pm-9pm): Final push or celebration

- Emoji for time: 🌅 morning, ☀️ afternoon, 🌆 evening

- Progress status:
  - ✅ >80% - celebrate
  - ⚠️ 50-80% - encourage
  - 🚨 <50% and afternoon/evening - urgent nudge

- Be specific about numbers in motivation
- Keep total response under 500 chars
- Be cheeky but supportive (Pete the PT voice)
