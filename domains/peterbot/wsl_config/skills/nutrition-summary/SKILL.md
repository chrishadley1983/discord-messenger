---
name: nutrition-summary
description: Daily nutrition wrap-up at 9pm
trigger:
  - "nutrition summary"
  - "how did i eat today"
  - "macros"
  - "daily summary"
scheduled: true
conversational: true
channel: #food-log
---

# Daily Nutrition Summary

## Purpose

End-of-day nutrition wrap-up at 9pm UK. Shows final macros for the day, compares to targets, and previews tomorrow.

## Pre-fetched Data

```json
{
  "nutrition": {
    "calories": 1950,
    "protein_g": 148,
    "carbs_g": 220,
    "fat_g": 65,
    "water_ml": 3200
  },
  "steps": 14200,
  "targets": {
    "calories": 2100,
    "protein_g": 160,
    "carbs_g": 263,
    "fat_g": 70,
    "water_ml": 3500,
    "steps": 15000
  },
  "date": "2026-01-31"
}
```

## Output Format

Use this EXACT format with blank lines for spacing:

```
🌙 **Daily Wrap-up** - Friday, 31 January

**🍽️ Nutrition**

Calories: 1,950 / 2,100 (93%) ✅
Protein: 148g / 160g (93%) ✅
Carbs: 220g / 263g (84%)
Fat: 65g / 70g (93%) ✅

**💧 Hydration & Movement**

Water: 3,200ml / 3,500ml (91%) ✅
Steps: 14,200 / 15,000 (95%) ✅

---

[Brief evening message - 2-3 sentences max]
```

**IMPORTANT:** Include blank lines after each section header and between sections for readability.

## Status Indicators

- ✅ >90% of target
- ⚠️ 70-90% of target
- ❌ <70% of target

## Rules

- This is the final check-in for the day
- Keep tone relaxed - day is done
- If targets hit, celebrate briefly
- If targets missed, don't dwell - "tomorrow's a new day"
- If protein significantly under, suggest evening snack option
- Wish good rest / good night
- Keep it brief - max 400 chars excluding the data
