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

**Every meal in the plan MUST exist in Family Fuel with a recipe ID before publishing. No exceptions.**

## Fixed Deployment URLs

| Asset | Domain | Notes |
|-------|--------|-------|
| Meal plan page | `hadley-meals.surge.sh` | Updated each week, always current |
| Shopping list | `hadley-shopping.surge.sh` | Updated each week, always current |
| Recipe cards | `hadley-recipes.surge.sh/{id}.html` | Persistent per recipe ID |

**NEVER use any other URL pattern.** No `hadley-shop-wXX`, no `hadley-meals-w12`, no custom domains.

## Pre-fetched Data

Data fetcher: `meal-plan-generator` — pulls all of the following in parallel:

- `data.template` — Default weekly template (portions, max_prep_mins, type per day)
- `data.preferences` — Dietary rules, variety rules, cuisine preferences, disliked ingredients
- `data.current_plan` — Current week's plan (for Gousto lock-ins with source_tag='gousto')
- `data.recent_history` — Last 21 days of meal history (for recency penalty)
- `data.due_staples` — Shopping staples due this cycle
- `data.calendar_context` — This week's calendar meal context (auto-detected overrides for busy evenings, eating out, guests)
- `data.recipe_candidates` — Top 20 recipes from Second Brain (semantic search)
- `data.batch_candidates` — Batch-friendly recipes (freezable or yields multiple meals) from Family Fuel
- `data.price_data` — Cached Sainsbury's prices and current deals (from weekly price scan)
- `data.week_start` — Monday date for the plan week

## Workflow

### Step 0: Import Gousto Recipes (AUTOMATIC — runs before anything else)

**This is mandatory. Do it immediately, before presenting defaults.**

1. Call `POST /meal-plan/import/gousto`
2. This searches Gmail for Gousto order confirmation emails, scrapes each recipe page, and saves to Family Fuel with full ingredients, instructions, and nutrition
3. Note the `saved_to_family_fuel` recipe IDs — these are needed later for recipe cards
4. If the import fails or finds no emails, continue (Chris may not have Gousto this week)

### Step 1: Present Defaults & Confirm

Load the template and present it with Gousto lock-ins and calendar overrides:

```
Right, let's sort this week's meals. Here's your default template:

**Mon** — 4 portions, 30 min | **Tue** — 4 portions, 15 min (swimming)
**Wed** — 2 portions, 45 min | **Thu** — 4 portions, 30 min
**Fri** — 4 portions, 45 min | **Sat** — 4 portions, 60 min
**Sun** — OUT

📅 Calendar flags: Thursday has "Parents Evening" until 7pm — I've dropped Thu to 15 min max.

🥘 Gousto arriving: Chicken Katsu, Pork Tacos, Veggie Curry (3 nights covered, all saved to Family Fuel ✅).

Any changes this week, or shall I crack on?
```

**Calendar overrides** are pre-computed in `data.calendar_context.overrides` (per-day dict with `type_override`, `max_prep_override`, `portions_override`, and `reasons`) and `data.calendar_context.summary` (one-line human-readable summary). Display these to Chris and let him confirm or adjust — no need to re-analyse raw events.

### Step 2: Generate the Plan

Once Chris confirms (or provides overrides), generate the meal plan:

1. **Lock in Gousto meals** — assign to days based on template fit (prep time, portions). Gousto recipes already have Family Fuel IDs from Step 0.
2. **Lock in any overrides** Chris mentioned
3. **Fill remaining slots** — for each unfilled "cook" day, select from candidates:

#### HARD GATE: Every Meal Must Have a Family Fuel Recipe ID

For each non-Gousto meal you want to add:
1. **Search Family Fuel first**: `GET /recipes/search?q=<name>&limit=5`
2. **If found**: use the existing recipe ID
3. **If NOT found**: you MUST create it before proceeding:
   - Fetch the full recipe (from source URL, Second Brain, or web search)
   - Call `POST /recipes` with **complete data**: recipeName, ingredients (every single one with quantity/unit), instructions (step-by-step), servings, prepTimeMinutes, cookTimeMinutes, cuisineType, dietary flags, nutrition if available
   - Use the returned recipe ID

**DO NOT add a meal to the plan without a Family Fuel recipe ID. If you cannot get one, pick a different meal.**

**Scoring criteria (in priority order):**
- **Prep time fit**: MUST be ≤ day's max_prep_mins (hard constraint)
- **Portion match**: Prefer recipes matching the day's portion count
- **Recency**: Penalise meals made in last 14 days, exclude last 7 days entirely
- **Protein variety**: Track protein types across the week. Enforce variety_rules (e.g., max 2× chicken)
- **Rating**: Prefer meals rated 4-5 stars, never suggest meals rated 1-2 with would_make_again=false
- **Cuisine diversity**: Don't repeat the same cuisine on consecutive days
- **Dietary compliance**: Must match adult/kids dietary rules from preferences
- **Price awareness**: If `data.price_data.deals` contains proteins/ingredients used by a candidate recipe, boost its score. Flag if estimated weekly spend exceeds `preferences.budget_per_week_pence`.
- **Disliked ingredients**: Exclude recipes containing disliked ingredients
- **Batch cook**: If batch_cook_per_week >= 1, pick one freezable/batch recipe early in the week (see Batch Cook Logic below)

### Batch Cook Logic

When `preferences.batch_cook_per_week >= 1`:

1. **Select a batch recipe** from `data.batch_candidates` for early in the week (Monday or Tuesday preferred)
   - Must meet the day's prep time and portion constraints
   - Prefer recipes with `mealsYielded >= 2`
   - Apply the same recency/rating/variety scoring as regular meals

2. **Auto-schedule leftovers** on a later day (within 3 days of the batch cook day)
   - The leftovers day should be a "cook" day with `max_prep_mins >= 15` (reheating)
   - Mark the leftovers day with: `adults_meal: "Leftovers: {batch recipe name}"`, `source_tag: "leftovers"`
   - Don't count leftovers toward protein variety limits (it's the same protein)

3. **Double the ingredients** for the batch recipe on the shopping list
   - If recipe serves 4 and `mealsYielded` is 2, multiply ingredients by 1.5x (extra half for leftovers)
   - If `mealsYielded` is not set, default to 2x ingredients

4. **Display in plan:**
```
**Monday** — Beef Chilli 🍲 _(batch cook, 45 min, 8 portions)_
**Wednesday** — Leftovers: Beef Chilli 🔄 _(reheat, 10 min)_
```

### Present the Draft Plan

Show the plan with Family Fuel IDs visible (so Chris can verify everything is tracked):

```
Here's this week's plan:

**Monday** — Chicken Stir-fry _(Family Fuel ✅, 25 min, 4 portions)_
**Tuesday** — Gousto: Chicken Katsu _(Family Fuel ✅, 15 min)_
**Wednesday** — Salmon & Veg Traybake _(Family Fuel ✅, 35 min, 2 portions)_
**Thursday** — Gousto: Pork Tacos _(Family Fuel ✅, 15 min)_
**Friday** — Homemade Pizza Night _(Family Fuel ✅, 40 min, 4 portions)_
**Saturday** — Gousto: Veggie Curry _(Family Fuel ✅, 45 min, 4 portions)_
**Sunday** — OUT

Protein balance: 🐔×2 🐷×1 🐟×1 🥬×1 🍕×1
All 6 recipes in Family Fuel ✅ — recipe cards will be generated.
Any swaps?
```

### Step 3: Handle Swaps

If Chris says "swap Monday for something with beef" or "change Friday to that Jamie Oliver thing":
- Re-run selection for just that day with the new constraint
- Same rule: new meal MUST have a Family Fuel recipe ID (search or create)
- Show the updated plan
- Repeat until Chris is happy

### Step 4: Save & Publish

Once Chris approves:

#### 4a. Save to database (MANDATORY)

Call `POST /meal-plan` with the full plan. This powers reminders, "what's for dinner?", and meal ratings.

**Important**: `week_start` is optional — it will be derived from the earliest item date. Each date+meal_slot combination is globally unique across all plans, so you never get overlapping meals. Use `check_overlaps: true` to detect conflicts before overwriting.

```json
POST http://172.19.64.1:8100/meal-plan
{
  "source": "generated",
  "notes": "Batch cook ricotta pasta Tuesday for Tue-Wed lunches",
  "check_overlaps": true,
  "items": [
    {"date": "2026-03-14", "meal_slot": "dinner", "adults_meal": "Sausages, Mash & Veg", "source_tag": "family_fuel", "recipe_id": "abc-123", "cook_time_mins": 45, "servings": 4},
    {"date": "2026-03-15", "meal_slot": "dinner", "adults_meal": "Chicken Katsu Curry", "source_tag": "gousto", "recipe_id": "def-456", "cook_time_mins": 35, "servings": 2}
  ]
}
```

If `check_overlaps` returns conflicts, present them to Chris and ask whether to overwrite (re-call with `check_overlaps: false`).

#### 4b. Log meal history
Call `POST /meal-plan/history` (without ratings — those come later)

#### 4c. Generate recipe cards
For every recipe in the plan, verify a recipe card exists at `hadley-recipes.surge.sh/{recipe_id}.html`. The `POST /meal-plan/view/html` endpoint with `auto_generate_cards: true` handles this — but you MUST pass recipe IDs in the plan items for it to work.

#### 4d. Publish meal plan page
Call `POST /meal-plan/view/html` with:
- Plan items including `recipe_id` on every meal
- `auto_generate_cards: true` (generates and deploys missing recipe card HTMLs)
- `notes` dict for per-day notes
- `cook_time_mins` and `servings` on each item

Deploy via `POST /deploy/surge` with `{"html": "<the HTML>", "domain": "hadley-meals.surge.sh"}`.

**All recipe links in the meal plan page MUST point to `hadley-recipes.surge.sh/{recipe_id}.html` — NEVER to external URLs like BBC Good Food or Gousto.** External source URLs go in the recipe card itself (as a "Source" link), not in the meal plan.

#### 4e. Verify recipe card deployment
For every recipe in the plan, confirm `hadley-recipes.surge.sh/{recipe_id}.html` returns 200. If any are missing, regenerate and redeploy.

### Step 5: Shopping List

#### 5a. MANDATORY Ingredient Verification (DO NOT SKIP)

**Before building the shopping list, you MUST verify every non-Gousto recipe.**

For each recipe that isn't from Gousto:
1. **Fetch the FULL recipe** via `GET /recipes/{id}` — the recipe WILL be in Family Fuel because of the Step 2 hard gate
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

#### 5b. Build Shopping List

1. Extract ingredients from Family Fuel recipes (structured ingredient data)
2. Exclude Gousto ingredients (they come in the box)
3. Add due staples to the shopping list
4. Ask: "Any extra staples off-schedule? (e.g., run out of something early)"

#### 5c. Generate & Deploy Shopping List

**You MUST use the API endpoint — DO NOT hand-build HTML.**

Call `POST /meal-plan/shopping-list/html` with:
```json
{
  "categories": {
    "Fruit & Veg": [{"item": "Cherry Tomatoes", "quantity": "1 pack", "for_recipe": "Carbonara"}],
    "Dairy & Eggs": [{"item": "Eggs", "quantity": "12", "for_recipe": "Weekly staple"}]
  },
  "staples": [{"name": "Milk", "category": "Dairy & Eggs", "quantity": "12 pints"}],
  "gousto_items": ["Chicken Katsu ingredients", "Pork Taco ingredients"],
  "title": "Weekly Shop",
  "week_start": "2026-03-14"
}
```

Deploy via `POST /deploy/surge` with `{"html": "<the HTML>", "domain": "hadley-shopping.surge.sh"}`.

Mark staples as added via `POST /meal-plan/staples/mark-added`.

Send both links to Chris (and optionally Abby via WhatsApp).

### Step 6: Offer Trolley Add

After deploying the shopping list, ask:

```
Want me to add this to the Sainsbury's trolley? I'll match everything and you can pick for any unclear items.
```

If Chris says yes:
1. Call `POST http://172.19.64.1:8100/meal-plan/shopping-list/to-trolley?store=sainsburys`
2. This auto-deduplicates against items already in the trolley
3. Present results using the same format as the `grocery-shop` skill (added / need your pick / not found)
4. Follow the same resolve flow for ambiguous items
5. After all items are added, favourite any that aren't already favourited (for faster matching next time)
6. Offer to book a delivery slot

If Chris says no or ignores, that's fine — the shopping list is still available as HTML.

## Completion Checklist (MANDATORY)

**Before sharing links with Chris, run through EVERY item. ALL must be TRUE.**

```
RECIPE DATA
[ ] Every meal in the plan has a Family Fuel recipe ID (no exceptions)
[ ] Every non-Gousto recipe was saved with FULL ingredients and instructions
[ ] Gousto import ran and saved recipes to Family Fuel
[ ] PATCH /recipes/{id}/usage called for every recipe used

MEAL PLAN PAGE
[ ] POST /meal-plan called (plan saved to database)
[ ] POST /meal-plan/history called (meals logged)
[ ] Meal plan HTML deployed to hadley-meals.surge.sh (not any other URL)
[ ] Every recipe link points to hadley-recipes.surge.sh/{id}.html (not external URLs)
[ ] auto_generate_cards was true in the HTML generation call

RECIPE CARDS
[ ] Every recipe card URL (hadley-recipes.surge.sh/{id}.html) returns 200
[ ] Cards include full ingredients, method, nutrition, and source link

SHOPPING LIST
[ ] Ingredient verification completed for every non-Gousto recipe
[ ] Shopping list generated via POST /meal-plan/shopping-list/html (not hand-built HTML)
[ ] Shopping list deployed to hadley-shopping.surge.sh (not any other URL)
[ ] Due staples included
[ ] Gousto items shown in separate section (not on main shopping list)

LINKS
[ ] hadley-meals.surge.sh loads correctly
[ ] hadley-shopping.surge.sh loads correctly
[ ] All recipe card links from meal plan page are clickable and load
```

**If ANY item is FALSE, fix it before sharing links. Do not skip items.**

## Recipe Sources (Priority Order)

1. **Family Fuel API** — Structured search with full ingredient data. `GET http://172.19.64.1:8100/recipes/search?q=chicken&cuisine=italian&limit=20`. Preferred because ingredients are structured (name, quantity, unit, category).
2. **Second Brain** — Semantic/fuzzy search for broader matching. `search_knowledge("recipe familyfuel [criteria]")`. Includes Gousto history and web saves.
3. **Web search** — If not enough candidates from stored recipes, search UK recipe sites (BBC Good Food, Mob Kitchen, Jamie Oliver, Joe Wicks). **When using a web recipe, you MUST save it to Family Fuel with full ingredients and instructions before adding it to the plan.**

When a Family Fuel recipe is used in a plan, call `PATCH /recipes/{id}/usage` to track usage frequency.

## Hadley API Endpoints

- `POST /meal-plan` — Save generated plan with items (MUST call — powers reminders, ratings, "what's for dinner?"). `week_start` is optional (derived from items). Use `check_overlaps: true` to detect date+slot clashes with existing plans.
- `GET /meal-plan/templates/default` — Default template
- `GET /meal-plan/preferences` — Food preferences
- `GET /meal-plan/current` — Current week's meals (queries by date range, not week_start)
- `GET /meal-plan/meals?start=YYYY-MM-DD&end=YYYY-MM-DD` — Get meals for any date range
- `GET /meal-plan/history?days=21` — Recent history
- `GET /meal-plan/staples/due` — Due staples
- `GET /calendar/meal-context` — Calendar meal context (pre-computed overrides)
- `POST /meal-plan/import/gousto` — Import Gousto recipes from Gmail → Family Fuel (MUST run in Step 0)
- `POST /recipes/extract` — Extract + optionally save recipe from URL via Chrome CDP (body: `{url, auto_save?}`)
- `GET /recipes/batch-friendly?limit=10` — Batch-cook-friendly recipes
- `GET /recipes/search?q=&cuisine=&meal_type=&tags=&limit=` — Search Family Fuel recipes
- `GET /recipes/{id}` — Full recipe with ingredients + instructions
- `POST /recipes` — Save a new recipe to Family Fuel (full ingredients, instructions, nutrition required)
- `PATCH /recipes/{id}/usage` — Track recipe usage
- `PATCH /recipes/{id}/rating` — Update recipe rating
- `POST /meal-plan/history` — Log meals to history
- `POST /meal-plan/staples/mark-added` — Mark staples as added
- `POST /meal-plan/view/html` — Generate interactive HTML meal plan page (deploy to hadley-meals.surge.sh)
- `POST /meal-plan/shopping-list/html` — Generate interactive HTML shopping list (deploy to hadley-shopping.surge.sh)
- `POST /meal-plan/shopping-list/to-trolley?store=sainsburys` — One-click add shopping list to trolley
- `POST /grocery/sainsburys/trolley/resolve` — Resolve ambiguous item (body: `{item_name, product_uid, quantity?}`)

## Output Format

Use Discord-friendly formatting:
- **Bold** day names
- _(italics)_ for recipe source, timing, portions
- Emoji protein indicators: 🐔 chicken, 🐄 beef, 🐷 pork, 🐑 lamb, 🐟 fish, 🦐 seafood, 🥬 veggie, 🌱 vegan
- Keep compact — the full plan should fit in one Discord message
- Show "Family Fuel ✅" next to every meal to confirm it's tracked

## Rules

- Maximum 2-message interview (present defaults → confirm/override → generate)
- If no template exists, redirect to `meal-plan-setup` skill first
- If no preferences exist, use sensible defaults (high-protein, varied, 3 Gousto nights)
- Always show protein balance summary
- Never suggest meals rated 1-2 with would_make_again=false
- Respect the hard constraint: prep time MUST fit the day's max
- **Every meal MUST have a Family Fuel recipe ID** — no exceptions, no external-URL-only meals
- **Always use the API endpoints for HTML generation** — never hand-build HTML for meal plans or shopping lists
- **Always deploy to the fixed URLs** — hadley-meals.surge.sh, hadley-shopping.surge.sh, hadley-recipes.surge.sh
- After generating the shopping list, always ask about extra staples before finalising
- UK English throughout

## Critical: Shopping List Completeness

**NEVER guess ingredients. ALWAYS verify against the actual Family Fuel recipe.**

Common mistakes to avoid:
- ❌ Saying "refried beans" when the recipe uses black beans
- ❌ Forgetting sauces/condiments (mayo, sour cream, hot sauce)
- ❌ Missing garnishes (lime, coriander, spring onions)
- ❌ Skipping components (slaw, salad, pickled onions)
- ❌ Assuming Chris has specialty items in stock
- ❌ Hand-building shopping list HTML instead of using the API
- ❌ Deploying to a custom surge URL instead of hadley-shopping.surge.sh
- ❌ Linking to BBC Good Food / Gousto website instead of recipe cards

**Mandatory process:**
1. Fetch the full recipe from Family Fuel: `GET /recipes/{id}`
2. List EVERY ingredient line-by-line
3. Cross-check against pantry assumptions
4. Add everything else to the shopping list

**If you generate a shopping list without doing this verification, you WILL miss items and Chris will have to go back to the shop.**
