---
name: meal-plan-generator
description: Generate a balanced weekly meal plan using templates, preferences, Gousto, recipes, and calendar data
trigger:
  - "plan meals"
  - "plan meals for the week"
  - "generate meal plan"
  - "what should we eat this week"
  - "sort this week's meals"
  - "meal plan for next week"
  - "plan dinners"
scheduled: false
conversational: true
channel: null
---

# Meal Plan Generator

## Purpose

Generate a balanced weekly meal plan by combining the default template, food preferences, Gousto lock-ins, calendar constraints, recipe candidates, and meal history. Uses a fast 2-message interview flow (defaults-heavy) then Claude picks optimal meals.

## Pre-fetched Data

Data fetcher: `meal-plan-generator` — pulls all of the following in parallel:

- `data.template` — Default weekly template (portions, max_prep_mins, type per day)
- `data.preferences` — Dietary rules, variety rules, cuisine preferences, disliked ingredients
- `data.current_plan` — Current week's plan (for Gousto lock-ins with source_tag='gousto')
- `data.recent_history` — Last 21 days of meal history (for recency penalty)
- `data.due_staples` — Shopping staples due this cycle
- `data.calendar_events` — This week's calendar events (detect busy evenings)
- `data.recipe_candidates` — Top 20 recipes from Second Brain (semantic search)
- `data.week_start` — Monday date for the plan week

## Workflow

### Step 1: Present Defaults & Confirm

Load the template and present it with any auto-detected overrides:

```
Right, let's sort this week's meals. Here's your default template:

**Mon** — 4 portions, 30 min | **Tue** — 4 portions, 15 min (swimming)
**Wed** — 2 portions, 45 min | **Thu** — 4 portions, 30 min
**Fri** — 4 portions, 45 min | **Sat** — 4 portions, 60 min
**Sun** — OUT

📅 Calendar flags: Thursday has "Parents Evening" until 7pm — I've dropped Thu to 15 min max.

🥘 Gousto arriving: Chicken Katsu, Pork Tacos, Veggie Curry (3 nights covered).

Any changes this week, or shall I crack on?
```

**Calendar auto-detection rules:**
- Events ending after 18:00 on a weekday → reduce that day's max_prep_mins to 15
- All-day events or events containing "out", "dinner", "restaurant" → set day type to "out"
- Events containing "away", "holiday", "trip" → set day type to "skip"

### Step 2: Generate the Plan

Once Chris confirms (or provides overrides), generate the meal plan:

1. **Lock in Gousto meals** — assign to days based on template fit (prep time, portions). Run `POST /meal-plan/import/gousto` to auto-save Gousto recipes to Family Fuel.
2. **Lock in any overrides** Chris mentioned
3. **Fill remaining slots** — for each unfilled "cook" day, select from candidates. **Every meal you add MUST have a recipe in Family Fuel** — if one doesn't exist, save it first via `POST /recipes` (with full ingredients and instructions) before adding it to the plan. This ensures recipe cards and shopping lists work.

**Scoring criteria (in priority order):**
- **Prep time fit**: MUST be ≤ day's max_prep_mins (hard constraint)
- **Portion match**: Prefer recipes matching the day's portion count
- **Recency**: Penalise meals made in last 14 days, exclude last 7 days entirely
- **Protein variety**: Track protein types across the week. Enforce variety_rules (e.g., max 2× chicken)
- **Rating**: Prefer meals rated 4-5 stars, never suggest meals rated 1-2 with would_make_again=false
- **Cuisine diversity**: Don't repeat the same cuisine on consecutive days
- **Dietary compliance**: Must match adult/kids dietary rules from preferences
- **Disliked ingredients**: Exclude recipes containing disliked ingredients
- **Batch cook**: If batch_cook_per_week >= 1, pick one freezable/batch recipe early in the week

4. **Present the draft plan:**

```
Here's this week's plan:

**Monday** — Chicken Stir-fry _(Family Fuel, 25 min, 4 portions)_
**Tuesday** — Gousto: Chicken Katsu _(quick, 15 min)_
**Wednesday** — Salmon & Veg Traybake _(Second Brain, 35 min, 2 portions)_
**Thursday** — Gousto: Pork Tacos _(quick, 15 min)_
**Friday** — Homemade Pizza Night _(Family Fuel, 40 min, 4 portions)_
**Saturday** — Gousto: Veggie Curry _(45 min, 4 portions)_
**Sunday** — OUT

Protein balance: 🐔×2 🐷×1 🐟×1 🥬×1 🍕×1
Any swaps?
```

### Step 3: Handle Swaps

If Chris says "swap Monday for something with beef" or "change Friday to that Jamie Oliver thing":
- Re-run selection for just that day with the new constraint
- Show the updated plan
- Repeat until Chris is happy

### Step 4: Save, Publish & Generate Shopping List

Once Chris approves:
1. Save the plan via existing meal plan service (`PUT /meal-plan/{plan_id}/ingredients` etc.)
2. Log all meals to `POST /meal-plan/history` (without ratings — those come later)
3. **Publish meal plan page**: call `POST /meal-plan/view/html` with the plan data. Include `cook_time_mins` and `servings` on each item, and `notes` dict for per-day notes (e.g. `{"2026-03-10": "Get chicken out of freezer at lunch"}`). Set `auto_generate_cards: true` to generate recipe cards. Deploy via `POST /deploy/surge` with `{"html": "<the HTML>", "domain": "hadley-meals.surge.sh"}`, share link. To update notes later, re-generate and re-deploy the page.

#### Step 4a: MANDATORY Ingredient Verification (DO NOT SKIP)

**Before building the shopping list, you MUST verify every non-Gousto recipe:**

For each recipe that isn't from Gousto:
1. **Fetch the FULL recipe** via `GET /recipes/{id}` (or the original URL if web recipe)
2. **List every ingredient** from the recipe, including:
   - Main proteins/carbs
   - Sauces, condiments, dressings
   - Spices and seasonings (even "pinch of salt")
   - Garnishes and toppings
   - Side components (slaws, salads, etc.)
3. **Check each ingredient** against Chris's pantry staples (assume: salt, pepper, olive oil, common dried herbs/spices are stocked)
4. **Add anything not in pantry** to the shopping list

**Verification checklist format:**
```
✅ [Recipe Name] — Ingredient Audit:
- Protein: [x] (on list)
- Carb: [x] (on list)
- Sauce/condiment: [x] (on list) or [pantry]
- Fresh veg: [x] (on list)
- Cheese/dairy: [x] (on list)
- Garnish: [x] (on list)
- Missing: NONE
```

**If you skip this step, ingredients WILL be missed and the shopping list will be incomplete.**

#### Step 4b: Build Shopping List

5. Extract ingredients from selected recipes (Family Fuel recipes have structured ingredient data)
6. Exclude Gousto ingredients (they come in the box)
7. Add due staples to the shopping list
8. Ask: "Any extra staples off-schedule? (e.g., run out of something early)"
9. Generate shopping list: PDF + interactive HTML page via `POST /meal-plan/shopping-list/html`
10. Deploy shopping list HTML via `POST /deploy/surge` with `{"html": "<the HTML>", "domain": "hadley-shop-wXX.surge.sh"}`, share link
11. Mark staples as added via `POST /meal-plan/staples/mark-added`
12. Send both links to Chris (and optionally Abby via WhatsApp)

## Recipe Sources (Priority Order)

1. **Family Fuel API** — Structured search with full ingredient data for shopping list generation. `GET http://172.19.64.1:8100/recipes/search?q=chicken&cuisine=italian&limit=20`. Preferred source because ingredients are structured (name, quantity, unit, category).
2. **Second Brain** — Semantic/fuzzy search for broader matching. `search_knowledge("recipe familyfuel [criteria]")` or `search_knowledge("[criteria]")`. Includes Gousto history and web saves.
3. **Web search** — If not enough candidates from stored recipes, search UK recipe sites (BBC Good Food, Mob Kitchen, Jamie Oliver, Joe Wicks) for new ideas. When using a web recipe, offer to save it to Family Fuel for future use.

When a Family Fuel recipe is used in a plan, call `PATCH /recipes/{id}/usage` to track usage frequency.

## Hadley API Endpoints

- `GET /meal-plan/templates/default` — Default template
- `GET /meal-plan/preferences` — Food preferences
- `GET /meal-plan/current` — Current plan (for Gousto lock-ins)
- `GET /meal-plan/history?days=21` — Recent history
- `GET /meal-plan/staples/due` — Due staples
- `GET /calendar/week` — Calendar events
- `POST /recipes/extract` — Extract + optionally save recipe from URL via Chrome CDP (body: `{url, auto_save?}`)
- `GET /recipes/search?q=&cuisine=&meal_type=&tags=&limit=` — Search Family Fuel recipes
- `GET /recipes/{id}` — Full recipe with ingredients + instructions
- `POST /recipes` — Save a new recipe to Family Fuel (manual)
- `PATCH /recipes/{id}/usage` — Track recipe usage
- `PATCH /recipes/{id}/rating` — Update recipe rating
- `POST /meal-plan/history` — Log meals to history
- `POST /meal-plan/staples/mark-added` — Mark staples as added
- `POST /meal-plan/view/html` — Generate interactive HTML meal plan page (deploy to surge.sh)
- `POST /meal-plan/shopping-list/html` — Generate interactive HTML shopping list
- `POST /meal-plan/shopping-list/generate` — Generate PDF shopping list

## Output Format

Use Discord-friendly formatting:
- **Bold** day names
- _(italics)_ for recipe source, timing, portions
- Emoji protein indicators: 🐔 chicken, 🐄 beef, 🐷 pork, 🐑 lamb, 🐟 fish, 🦐 seafood, 🥬 veggie, 🌱 vegan
- Keep compact — the full plan should fit in one Discord message

## Rules

- Maximum 2-message interview (present defaults → confirm/override → generate)
- If no template exists, redirect to `meal-plan-setup` skill first
- If no preferences exist, use sensible defaults (high-protein, varied, 3 Gousto nights)
- Always show protein balance summary
- Never suggest meals rated 1-2 with would_make_again=false
- Respect the hard constraint: prep time MUST fit the day's max
- When searching for recipes, prefer Family Fuel (has structured ingredients) over web recipes (need manual ingredient lists)
- **Every meal in the plan MUST have a Family Fuel recipe** — if you add a meal that isn't in Family Fuel, save it first via `POST /recipes` with full ingredients, instructions, and macros. This is required for recipe cards and shopping list generation to work.
- After generating the shopping list, always ask about extra staples before finalising
- UK English throughout

## Critical: Shopping List Completeness

**NEVER guess ingredients. ALWAYS verify against the actual recipe.**

Common mistakes to avoid:
- ❌ Saying "refried beans" when the recipe uses black beans
- ❌ Forgetting sauces/condiments (mayo, sour cream, hot sauce)
- ❌ Missing garnishes (lime, coriander, spring onions)
- ❌ Skipping components (slaw, salad, pickled onions)
- ❌ Assuming Chris has specialty items in stock

**Mandatory process:**
1. Fetch the full recipe (API or original URL)
2. List EVERY ingredient line-by-line
3. Cross-check against pantry assumptions
4. Add everything else to the shopping list

**If you generate a shopping list without doing this verification, you WILL miss items and Chris will have to go back to the shop.**
