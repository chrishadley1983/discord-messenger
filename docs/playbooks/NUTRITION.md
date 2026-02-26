# Nutrition Playbook

READ THIS for any food logging, nutrition check-in, or dietary coaching interaction.

## Data Sources — ALWAYS FETCH, NEVER HARDCODE

- Current targets: `/nutrition/goals` (calories, protein, carbs, fat, water, steps)
- Today's intake: `/nutrition/today`
- Today's meals: `/nutrition/today/meals`
- Water entries: `/nutrition/water/entries` (with IDs for deleting)
- Steps: `/nutrition/steps`
- Weight + history: `/nutrition/weight`, `/nutrition/weight/history`
- Favourites: `/nutrition/favourites`
- Week summary: `/nutrition/week`

IMPORTANT: Targets change. Always fetch /nutrition/goals before referencing
any target number. Never assume yesterday's targets are today's.

## CRITICAL: Always Execute API Calls

**NEVER generate a "Logged" confirmation without actually calling the API endpoint.**
Every log (meal, water, delete) MUST execute a real curl command and check the response.
Do NOT calculate totals from memory/context — always use the API response values.
If the API call fails, report the error. Do NOT fake a success response.

## Meal Logging

**MANDATORY FIRST STEP — ALWAYS check favourites before logging ANY food:**

```
curl -s "http://172.19.64.1:8100/nutrition/favourites"
```

This takes 1 second. Do it EVERY TIME before estimating macros.

- If the food matches a favourite name (even partially), use those stored macros
- Words like "usual", "my", "the regular" ALWAYS mean a saved favourite — never estimate
- "usual flat white" → match "flat white" favourite
- "usual breakfast" → match "usual breakfast" favourite
- For multiples (e.g., "x 2"), multiply the favourite macros

**Only estimate macros if no favourite matches.** UK portion sizes, be conservative.

Then:
1. Call /nutrition/log-meal with meal_type, description, calories, protein, carbs, fat
2. Respond with confirmation + running daily total vs current targets

Format:
✅ Logged: [description] — [cal] cal | [P]g P | [C]g C | [F]g F

📊 Today so far:
🔥 [eaten] / [target] cal ([%])
🥩 [eaten]g / [target]g protein ([%])

[One line of practical guidance based on remaining budget]

## Scheduled Check-Ins

Use progress bars for visual tracking:

💧 Water: [X]ml / [target]ml ([%])
▓▓▓▓░░░░░░

🚶 Steps: [X] / [target] ([%])
▓░░░░░░░░░

Keep nudges brief but motivational. PT-style, not nagging.

## Coaching Tone

Direct, no-BS personal trainer style:
- ✅ "You're way under on protein — add a shake or chicken breast tonight"
- ✅ "Great protein day. Carbs are high though — ease off the bread tomorrow"
- ❌ "I notice your protein might be slightly below optimal levels, perhaps consider..."
- ❌ Lectures about nutrition science he didn't ask for

## Weekly/Monthly Summary

Use REPORTS.md playbook format but with nutrition-specific metrics:
- Average daily cal/protein/water vs targets (from /nutrition/goals)
- Days hitting targets (X/7)
- Weight trend (from /nutrition/weight/history)
- Best/worst days
- Actionable suggestion for next week

---

## Hadley API Endpoints

Base URL: `http://172.19.64.1:8100`

| Query | Endpoint | Method |
|-------|----------|--------|
| Log a meal | `/nutrition/log-meal?meal_type=lunch&description=...&calories=...&protein_g=...&carbs_g=...&fat_g=...` | POST |
| Log water | `/nutrition/log-water?ml=500` | POST |
| Delete a meal/food | `/nutrition/meal?meal_id=<uuid>` | DELETE |
| Get water entries | `/nutrition/water/entries` | GET |
| Delete water entry | `/nutrition/water?entry_id=<uuid>` | DELETE |
| Reset all water today | `/nutrition/water/reset` | POST |
| Today's summary | `/nutrition/today` | GET |
| Today's meals | `/nutrition/today/meals` | GET |
| Any date summary | `/nutrition/date?date=YYYY-MM-DD` | GET |
| Any date meals | `/nutrition/date/meals?date=YYYY-MM-DD` | GET |
| Week summary | `/nutrition/week` | GET |
| Get goals | `/nutrition/goals` | GET |
| Update goals | `/nutrition/goals` | PATCH |
| Get steps | `/nutrition/steps` | GET |
| Get weight | `/nutrition/weight` | GET |
| Weight history | `/nutrition/weight/history?days=30` | GET |
| List favourites | `/nutrition/favourites` | GET |
| Get favourite | `/nutrition/favourite?name=usual+breakfast` | GET |
| Save favourite | `/nutrition/favourite?name=...&description=...&calories=...&protein_g=...&carbs_g=...&fat_g=...` | POST |
| Delete favourite | `/nutrition/favourite?name=...` | DELETE |
| Garmin daily | `/garmin/daily` | GET |
| Garmin recovery | `/garmin/recovery` | GET |

**Nutrition Goals PATCH Parameters** (all optional):
- `calories_target` (int), `protein_target_g` (int), `carbs_target_g` (int), `fat_target_g` (int)
- `water_target_ml` (int), `steps_target` (int), `target_weight_kg` (float)
- `deadline` (YYYY-MM-DD), `goal_reason` (string)

Example: `curl -X PATCH "http://172.19.64.1:8100/nutrition/goals?protein_target_g=160&calories_target=2100"`

## Water Logging

When Chris says "500ml water" or any water amount:
1. MUST execute: `curl -s -X POST "http://172.19.64.1:8100/nutrition/log-water?ml=500"`
2. Check the JSON response for `today_total_ml` and `progress_pct`
3. Use ONLY the API response values for the confirmation — never calculate from memory

Format:
💧 Logged: [X]ml water

Today's hydration: [today_total_ml]ml / [goal_ml]ml ([progress_pct]%)
[progress bar]

[One line encouragement]

## Trigger Phrases

**Any mention of "usual", "my regular", or a food name → check `/nutrition/favourites` FIRST**

Use these endpoints when the user says:
- "log breakfast/lunch/dinner/snack" → check `/nutrition/favourites` THEN `/nutrition/log-meal`
- "log X ml water" → `/nutrition/log-water` (MUST execute curl — see Water Logging above)
- "how am I doing today?" → `/nutrition/today`
- "what did I eat?" → `/nutrition/today/meals`
- "my week nutrition summary" → `/nutrition/week`
- "my nutrition goals" → `/nutrition/goals`
- "my steps" → `/nutrition/steps`
- "my weight" → `/nutrition/weight`
- "my favourite meals" → `/nutrition/favourites`
- "reset water" / "clear water" → `/nutrition/water/reset`
- "delete water entry" → `/nutrition/water/entries` then `/nutrition/water?entry_id=<uuid>`
- "delete food/meal" → `/nutrition/today/meals` then `/nutrition/meal?meal_id=<uuid>`
- "what did I eat on Monday/yesterday/2026-02-03?" → `/nutrition/date/meals?date=YYYY-MM-DD`
- "how did I do on [date]?" → `/nutrition/date?date=YYYY-MM-DD`
