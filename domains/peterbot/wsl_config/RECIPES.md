# Recipes & Meal Planning — Reference

## Finding Recipes (Priority Order)

1. **Family Fuel API** (structured data) — `GET http://172.19.64.1:8100/recipes/search?q=chicken&cuisine=italian&limit=20`. Returns recipes with full ingredients, macros, ratings. Use for shopping list generation.
2. **Second Brain** (semantic/fuzzy) — `search_knowledge("recipe familyfuel [criteria]")` or `search_knowledge("[criteria]")`. Includes Gousto history and web saves.
3. **Web search** (for new ideas or specific requests) — Search BBC Good Food, Mob Kitchen, Jamie Oliver, Joe Wicks, Tesco Real Food, Skinnytaste. Always verify macros from the actual recipe page, never estimate.

## When Chris Asks for a Specific Recipe

E.g. "find me a burrito recipe", "good chilli recipe":
1. Search Family Fuel API first: `GET /recipes/search?q=burrito`
2. Then search Second Brain for saved recipes
3. Then do 2-3 web searches across UK recipe sites
4. Present top 3-5 options with macros, prep time, and source links
5. If Chris likes one, offer to save it to Family Fuel

## Quick Save from URL (Preferred Method)

If Chris shares a recipe URL or you find one online, use the extractor:
```
POST http://172.19.64.1:8100/recipes/extract
{"url": "https://cooking.nytimes.com/recipes/...", "auto_save": true}
```
Connects to Chrome via CDP (port 9222), extracts JSON-LD recipe schema, parses ingredients/macros/instructions, and saves to Family Fuel. Works with paywalled sites (NYT Cooking, etc.) using Chris's logged-in Chrome session.

Supported sites: NYT Cooking, BBC Good Food, Jamie Oliver, Mob Kitchen, AllRecipes, Delicious Magazine, and any site with Schema.org Recipe markup.

To extract without saving (for review first): `{"url": "...", "auto_save": false}`

## Manual Save (When URL Extraction Isn't Possible)

Extract structured data, then save:
```json
POST http://172.19.64.1:8100/recipes
{
  "recipeName": "Chicken Burrito Bowl",
  "description": "Quick high-protein burrito bowl",
  "servings": 4,
  "prepTimeMinutes": 10,
  "cookTimeMinutes": 20,
  "cuisineType": "Mexican",
  "mealType": ["dinner"],
  "caloriesPerServing": 520,
  "proteinPerServing": 38,
  "carbsPerServing": 45,
  "fatPerServing": 18,
  "containsMeat": true,
  "tags": ["high-protein", "quick", "family-friendly"],
  "recipeSource": "BBC Good Food",
  "sourceUrl": "https://...",
  "ingredients": [
    {"ingredientName": "chicken breast", "quantity": 500, "unit": "g", "category": "meat"},
    {"ingredientName": "rice", "quantity": 300, "unit": "g", "category": "carbs"}
  ],
  "instructions": [
    {"stepNumber": 1, "instruction": "Cook the rice according to packet instructions"},
    {"stepNumber": 2, "instruction": "Dice chicken and fry for 8 mins", "timerMinutes": 8}
  ]
}
```
Also save to Second Brain for semantic search: `POST /brain/save` with full text + tags.

## Recipe API Endpoints

- **Get full recipe:** `GET http://172.19.64.1:8100/recipes/{id}` — returns recipe with all ingredients and instructions
- **Track usage:** `PATCH http://172.19.64.1:8100/recipes/{id}/usage` — increments timesUsed, sets lastUsedDate
- **Update rating:** `PATCH http://172.19.64.1:8100/recipes/{id}/rating` — body: `{"rating": 8}` (1-10 scale)
- **Delete recipe:** `DELETE http://172.19.64.1:8100/recipes/{id}` — soft-deletes (archives)

## Meal Planning Skills

See the individual skill files for detailed behaviour:
- `skills/meal-plan/SKILL.md` — View/import plans
- `skills/meal-plan-setup/SKILL.md` — Templates, preferences, staples
- `skills/meal-plan-generator/SKILL.md` — Generate balanced weekly plans
- `skills/meal-rating/SKILL.md` — Evening rating prompt
- `skills/grocery-shop/SKILL.md` — Sainsbury's trolley automation
- `skills/price-scanner/SKILL.md` — Weekly price scan
- `skills/recipe-discovery/SKILL.md` — Weekly recipe recommendations
- `skills/cooking-reminder/SKILL.md` — Proactive prep reminders

## Meal Planning API Endpoints

See the Hadley API section in CLAUDE.md for the full list of `/meal-plan/*` endpoints. Key ones:
- `/meal-plan/current` — current week's plan
- `/meal-plan/import/sheets` — import from Google Sheets
- `/meal-plan/import/gousto` — import from Gousto (also scrapes+saves recipes)
- `/meal-plan/templates/*` — weekly templates
- `/meal-plan/preferences` — food preferences
- `/meal-plan/staples/*` — recurring shopping items
- `/meal-plan/shopping-list/html` — interactive shopping list for surge.sh
- `/meal-plan/shopping-list/to-trolley` — one-click meal plan → Sainsbury's trolley
- `/grocery/sainsburys/trolley/add-list` — batch add to trolley
- `/grocery/sainsburys/slots` — delivery slots
- `/calendar/meal-context` — auto-detect busy evenings, eating out, guests
