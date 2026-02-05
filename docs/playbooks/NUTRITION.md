# Nutrition Playbook

READ THIS for any food logging, nutrition check-in, or dietary coaching interaction.

## Data Sources — ALWAYS FETCH, NEVER HARDCODE

- Current targets: `/nutrition/goals` (calories, protein, carbs, fat, water, steps)
- Today's intake: `/nutrition/today`
- Today's meals: `/nutrition/today/meals`
- Water logged: `/nutrition/water/today`
- Steps: `/nutrition/steps`
- Weight + history: `/nutrition/weight`, `/nutrition/weight/history`
- Favourites: `/nutrition/favourites`
- Week summary: `/nutrition/week`

IMPORTANT: Targets change. Always fetch /nutrition/goals before referencing
any target number. Never assume yesterday's targets are today's.

## Meal Logging

When Chris says "log lunch, chicken salad":
1. Check /nutrition/favourites first — if it's a known meal, use stored macros
2. Otherwise, estimate macros using UK portion sizes, be conservative
3. Call /nutrition/log-meal with meal_type, description, calories, protein, carbs, fat
4. Respond with confirmation + running daily total vs current targets

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
| Delete a meal | `/nutrition/meal?meal_id=<uuid>` | DELETE |
| Get water entries | `/nutrition/water/entries` | GET |
| Delete water entry | `/nutrition/water?entry_id=<uuid>` | DELETE |
| Today's summary | `/nutrition/today` | GET |
| Today's meals | `/nutrition/today/meals` | GET |
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

## Trigger Phrases

Use these endpoints when the user says:
- "log breakfast/lunch/dinner/snack" → `/nutrition/log-meal`
- "log X ml water" → `/nutrition/log-water`
- "how am I doing today?" → `/nutrition/today`
- "what did I eat?" → `/nutrition/today/meals`
- "my week nutrition summary" → `/nutrition/week`
- "my nutrition goals" → `/nutrition/goals`
- "my steps" → `/nutrition/steps`
- "my weight" → `/nutrition/weight`
- "my favourite meals" → `/nutrition/favourites`
