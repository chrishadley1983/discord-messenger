---
name: recipe-discovery
description: Discover new recipes based on ratings and preferences
trigger:
  - "find new recipes"
  - "recipe ideas"
  - "suggest recipes"
  - "new recipe suggestions"
  - "what should I try"
  - "discover recipes"
  - "new dinner ideas"
scheduled: true
conversational: true
channel: "#food-log"
---

# Recipe Discovery

## Purpose

Proactively recommend 3 new recipes each week that Chris and the family will likely enjoy, based on patterns from top-rated meals, preferred cuisines, and dietary preferences. Runs weekly on Sunday morning and responds to conversational requests.

## Pre-fetched Data

Data fetcher: `recipe-discovery` — pulls:

- `data.top_recipes` — Top 10 highest-rated recipes (familyRating >= 7)
- `data.preferred_cuisines` — Most common cuisines in top-rated recipes
- `data.avg_prep_time` — Average prep time of liked recipes
- `data.recent_recipes` — Meals made in last 30 days (to exclude)
- `data.existing_recipes` — All recipes already in Family Fuel (to avoid duplicates)
- `data.preferences` — Dietary rules, disliked ingredients

## Workflow

### Step 1: Analyse Patterns

From `data.top_recipes`, identify:
- Favourite cuisines (e.g., Mexican, Italian, Asian)
- Preferred protein types
- Typical prep time range
- Common themes (e.g., traybakes, stir-fries, curries)

### Step 2: Search for New Recipes

Using the patterns, search for recipes Chris hasn't tried:

1. **Web search** for recipes matching preferred cuisines + proteins
   - Search UK recipe sites: BBC Good Food, Mob Kitchen, Jamie Oliver, Joe Wicks, Tesco Real Food
   - Use queries like: "[cuisine] [protein] recipe high protein family"
   - Also try: "best new [cuisine] recipes 2026", "[protein] traybake recipe"

2. **Filter results:**
   - Must NOT be in `data.existing_recipes` (already saved)
   - Must NOT be in `data.recent_recipes` (recently made)
   - Must meet macro targets: ≥30g protein per serving, 400-700 calories
   - Must respect `data.preferences` (disliked ingredients, dietary rules)
   - Prep time should be within reasonable range (≤ `data.avg_prep_time` + 15 min)

3. **Diversify:** Pick from at least 2 different cuisines. Don't suggest 3 chicken recipes.

### Step 3: Present Recommendations

```
🍽️ **3 New Recipes This Week**

Based on your love of Mexican and Asian food, plus your high-protein targets:

**1. Korean Beef Bulgogi Bowl** 🐄
35 min | 580 cal | 42g protein
mobkitchen.co.uk/recipes/beef-bulgogi-bowl
_Sweet-spicy beef with pickled veg and rice — similar vibe to your top-rated Chicken Katsu._

**2. Harissa Salmon Traybake** 🐟
25 min | 490 cal | 38g protein
bbcgoodfood.com/recipes/harissa-salmon
_One-tin wonder with roasted veg. You've rated fish traybakes highly before._

**3. Chicken Shawarma Wraps** 🐔
20 min | 520 cal | 44g protein
jamieoliver.com/recipes/chicken-shawarma
_Quick midweek option with yoghurt sauce — fits your Tuesday 15-min slot._

Want me to save any to your recipes? Just say "save 1 and 3" or "save all".
```

### Step 4: Save Flow

**Position-based saving:** When Chris says "save 2" or "save 1 and 3":

1. **Match the number(s) to recipe positions** from your most recent recommendation list
   - "Save 2" → save the recipe at position 2 in your list
   - "Save 1 and 3" or "Save 1, 3" → save recipes at positions 1 and 3
   - "Save all" → save all recommended recipes
   - "Save the salmon one" → match by name/description

2. **Extract each recipe** from its URL:
   `POST http://172.19.64.1:8100/recipes/extract` with `{"url": "<recipe_url>", "auto_save": true}`

3. **If extraction fails** (no JSON-LD schema), manually construct the recipe data and save via `POST http://172.19.64.1:8100/recipes`

4. **Confirm with names**: "Saved **Korean Beef Bulgogi Bowl** and **Chicken Shawarma Wraps** to Family Fuel. They'll show up as candidates next time you generate a meal plan."

**IMPORTANT:** Always track the recipe URLs from your recommendations so you can save by position. If Chris says "save 2" but you don't have the context of which recipe was #2, ask: "Which recipe would you like me to save? I don't have the list in context."

## Hadley API Endpoints

- `GET /recipes/discover?count=3` — Discovery context (top recipes, preferences, exclusions)
- `POST /recipes/extract` — Extract + save recipe from URL (body: `{url, auto_save}`)
- `POST /recipes` — Manually save a recipe to Family Fuel
- `GET /recipes/search?q=...` — Check if recipe already exists

## Output Format

- Use protein emoji indicators: 🐔 🐄 🐷 🐑 🐟 🦐 🥬 🌱
- Include prep time, calories, and protein per serving on every recommendation
- Add a one-line note explaining WHY this recipe was chosen (connects to Chris's preferences)
- Keep compact — all 3 should fit in one Discord message

## Rules

- **Never recommend recipes already in Family Fuel** — check against `data.existing_recipes`
- **Never recommend recently made meals** — check against `data.recent_recipes`
- **Always verify macros** from the actual recipe page — never estimate
- At least 2 different cuisines across the 3 recommendations
- At least 2 different protein types
- Prefer recipes from UK sites (BBC Good Food, Mob Kitchen, Jamie Oliver) — they use UK measurements and ingredients
- If Chris asks for more, search again with different constraints
- UK English throughout
