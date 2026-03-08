---
name: meal-plan
description: View, import, and manage weekly meal plans with shopping list generation
trigger:
  - "meal plan"
  - "what's for dinner"
  - "what are we eating"
  - "import meal plan"
  - "shopping list from meal plan"
  - "this week's meals"
  - "gousto recipes"
  - "what's for tea"
scheduled: false
conversational: true
channel: null
---

# Meal Plan

## Purpose

View, import, and manage Chris's weekly meal plans. Integrates with Google Sheets (the master source), Gousto email imports, and shopping list PDF generation.

## Hadley API Endpoints

Base URL: `http://172.19.64.1:8100`

**View:**
- `GET /meal-plan/current` — Get current week's plan (items + ingredients)
- `GET /meal-plan/week?date=YYYY-MM-DD` — Get plan for week containing date

**Import:**
- `POST /meal-plan/import/sheets?spreadsheet_id=<id>` — Import from Google Sheet (default sheet ID hardcoded)
- `POST /meal-plan/import/csv` — Import from CSV (body: `{csv_data: "...", ingredients_csv: "..."}`)
- `POST /meal-plan/import/gousto` — Search Gmail for Gousto emails, extract recipes, match to plan, and auto-save to Family Fuel DB (returns `saved_to_family_fuel` with recipe IDs)

**Shopping List:**
- `GET /meal-plan/shopping-list` — Get ingredients as categorised shopping list
- `POST /meal-plan/shopping-list/generate` — Generate printable PDF from plan ingredients

**Manage:**
- `PUT /meal-plan/{plan_id}/ingredients` — Update ingredients (body: `{ingredients: [{category, item, quantity?, for_recipe?}]}`)
- `DELETE /meal-plan/{plan_id}` — Delete a plan

## Workflow

### "What's for dinner?" / "What are we eating?"
1. Call `GET /meal-plan/current`
2. If no plan exists, say "No meal plan for this week. Want me to import it from the Google Sheet?"
3. If plan exists, filter items to **today's date** and format the response
4. Show both adults and kids meals if different

### "Show me the meal plan" / "This week's meals"
1. Call `GET /meal-plan/current`
2. Format as a day-by-day list for the whole week
3. Include source tags (Gousto, homemade, etc.)

### "Import meal plan" / "Update meal plan"
1. Call `POST /meal-plan/import/sheets` (uses default spreadsheet)
2. Report how many days/meals were imported
3. If ingredients tab was found, report those too

### "Shopping list from meal plan"
1. Call `GET /meal-plan/shopping-list`
2. If no ingredients, tell Chris and suggest importing from the sheet or ask if he'd like you to infer ingredients from the recipe names
3. If ingredients exist, call `POST /meal-plan/shopping-list/generate` to create the PDF
4. Report the PDF location

### "Import Gousto recipes"
1. Call `POST /meal-plan/import/gousto`
2. Report which recipes were found in emails
3. Show matched vs unmatched recipes against the current plan
4. Report how many recipes were saved to Family Fuel (`saved_to_family_fuel`) and any errors (`save_errors`)

## Output Format

### Day-by-day view:
```
This week's meals (w/c 3 Feb):

**Monday 3 Feb**
- Adults: Chicken stir-fry
- Kids: Fish fingers & chips

**Tuesday 4 Feb**
- Adults: Gousto - Thai green curry
- Kids: Pasta bake

**Wednesday 5 Feb**
- Chris out
- Kids: Sausages & mash
```

### Today's dinner:
```
Tonight's dinner:
- Adults: Chicken stir-fry
- Kids: Fish fingers & chips
```

## Related Skills

- **meal-plan-setup** — Manage weekly templates, food preferences, and meal ratings. Triggers: "set up meal template", "food preferences", "rate dinner", etc.
- Templates define the "shape" of the week (portions, prep time, type per day)
- Preferences define dietary rules, cuisine preferences, disliked ingredients
- Meal history tracks ratings and "would make again" for learning

## Rules

- Use DD Mon format for dates (e.g. "3 Feb", not "03/02" or "February 3rd")
- Mark Gousto meals with "Gousto - " prefix
- If adults_meal is empty but kids_meal exists, show "Kids only: ..."
- If both are the same, show once without adult/kids split
- Use UK English (tea = dinner in casual context)
- When Chris says "what's for tea" he means tonight's dinner
- Keep responses concise — no need for elaborate formatting for simple "what's for dinner" queries
