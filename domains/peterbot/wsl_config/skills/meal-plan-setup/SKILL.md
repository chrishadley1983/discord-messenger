---
name: meal-plan-setup
description: Set up and manage weekly meal plan templates, food preferences, and meal ratings
trigger:
  - "set up meal template"
  - "update meal template"
  - "meal plan template"
  - "food preferences"
  - "update food preferences"
  - "disliked ingredients"
  - "meal preferences"
  - "weekly meal shape"
  - "add staple"
  - "shopping staples"
  - "manage staples"
scheduled: false
conversational: true
channel: null
---

# Meal Plan Setup

## Purpose

Manage the building blocks for intelligent meal planning: weekly templates (the "shape" of the week), food preferences, and meal ratings/history. These feed into the meal plan generator (Phase 2).

## Related Skills

- **meal-plan-generator** — Uses templates and preferences to generate weekly meal plans. Triggers: "plan meals", "what should we eat this week"
- **meal-rating** — Evening prompts to rate meals. Triggers: "rate dinner", "how was dinner"

## Hadley API Endpoints

Base URL: `http://172.19.64.1:8100`

**Templates:**
- `GET /meal-plan/templates` — List all templates
- `GET /meal-plan/templates/default` — Get the default template
- `GET /meal-plan/templates/{name}` — Get a template by name
- `PUT /meal-plan/templates/{name}` — Create/update a template (body: `{days: {...}, is_default: bool}`)
- `DELETE /meal-plan/templates/{name}` — Delete a template

**Preferences:**
- `GET /meal-plan/preferences` — Get current preferences
- `PUT /meal-plan/preferences` — Update preferences (body: partial update, only provided fields change)

**Meal History:**
- `POST /meal-plan/history` — Log a meal (body: `{date, meal_name, recipe_source?, protein_type?, rating?, would_make_again?, notes?}`)
- `GET /meal-plan/history?days=14` — Get recent meal history
- `PATCH /meal-plan/history/{meal_id}/rating` — Update a meal's rating (body: `{rating, would_make_again?, notes?}`)

**Shopping Staples:**
- `GET /meal-plan/staples` — List all staples
- `GET /meal-plan/staples/due` — Get staples due this cycle
- `POST /meal-plan/staples` — **Bulk add/update** (body: `{staples: [{name, category, quantity?, frequency?, notes?}]}`) — use this when adding multiple staples at once
- `PUT /meal-plan/staples/{name}` — Add/update a single staple (body: `{category, quantity?, frequency?, notes?}`)
- `DELETE /meal-plan/staples/{name}` — Remove a staple
- `POST /meal-plan/staples/mark-added` — Mark staples as added (body: `{names: [...]}`)

## Workflows

### Initial Setup Interview (first time only)

When Chris says "set up meal template" or similar and no default template exists:

1. **Build the week shape** — Ask about each day briefly:
   - "Let's build your default week. For each day, tell me: portions (2 or 4), max prep time, and any notes. What does Monday look like?"
   - Batch days where possible: "And Tuesday through Thursday?"
   - Use `type` values: `cook`, `out`, `takeaway`, `leftovers`, `skip`

2. **Food preferences** — Quick-fire round:
   - "Any dietary requirements for adults? Kids?"
   - "Cuisines you love?"
   - "Ingredients you or the kids hate?"
   - "How many Gousto nights per week?"
   - "Want a batch cook meal each week?"
   - Protein variety rules (default: max 2 of same protein, 1 veggie, 1 fish per week)

3. **Save both** — `PUT /meal-plan/templates/{name}` + `PUT /meal-plan/preferences`

4. **Confirm** — Show the template back in a readable format

### Quick Template Edit

When Chris says "change Tuesday to out" or "make Friday a quick meal":
1. `GET /meal-plan/templates/default`
2. Modify the specific day(s)
3. `PUT /meal-plan/templates/default`
4. Confirm the change

### Create Alternative Template

When Chris says "create a school holidays template":
1. Start from default template as a base
2. Ask what's different (e.g., "kids home all day, need lunch too")
3. `PUT /meal-plan/templates/school-holidays`

### Manage Shopping Staples

When Chris says "add staple", "manage staples", "shopping staples":
1. `GET /meal-plan/staples` to show current staples
2. For adding multiple: use `POST /meal-plan/staples` with `{staples: [...]}` in one call (don't call PUT per item)
3. For adding a single item: `PUT /meal-plan/staples/{name}`
4. For removing: `DELETE /meal-plan/staples/{name}`

**Quick add:** "Add milk as a weekly staple" → extract name=milk, infer category=Dairy & Eggs, frequency=weekly, then save.

**Categories:** Fruit & Veg, Dairy & Eggs, Meat & Fish, Bakery, Frozen, Drinks, Cupboard, Snacks, Household, Toiletries, Baby & Kids, Other

### Rate a Meal / "How was dinner?"

**Note: Ratings are now handled by the `meal-rating` skill.** If Chris asks to rate a meal via this skill, redirect: "I've got a dedicated rating flow — just say 'rate dinner' or tell me how it was!"

When Chris says "rate dinner", "that was great", "rate that meal":
1. Check `GET /meal-plan/history?days=1` for today's meal
2. If no history entry for today, check `GET /meal-plan/current` for tonight's planned meal
3. Ask: "How was the [meal name]? Quick 1-5?" (if not already given)
4. Ask: "Would you make it again?" (yes/no)
5. Log or update via `POST /meal-plan/history` or `PATCH /meal-plan/history/{id}/rating`

### Proactive Rating Prompt (for future scheduled use)

When triggered by scheduler in the evening:
1. Check today's meal plan
2. If a meal was planned: "How was the [Chicken Katsu] tonight? Quick rate 1-5, and would you make it again?"
3. If Chris responds with just a number, treat as rating
4. Log to history

## Template Day Schema

```json
{
  "monday": {
    "portions": 4,
    "max_prep_mins": 30,
    "type": "cook",
    "notes": ""
  },
  "tuesday": {
    "portions": 4,
    "max_prep_mins": 15,
    "type": "cook",
    "notes": "Swimming — quick meal"
  },
  "sunday": {
    "portions": 0,
    "type": "out",
    "notes": "Usually out or takeaway"
  }
}
```

**Type values:**
- `cook` — Normal cooking night (default)
- `out` — Eating out, no cooking needed
- `takeaway` — Takeaway night
- `leftovers` — Eating leftovers from batch cook
- `skip` — No meal needed (e.g., fasting, late lunch)

## Output Format

### Template display:
```
Your default meal template:

**Monday** — 4 portions, 30 min max
**Tuesday** — 4 portions, 15 min max _(swimming — quick meal)_
**Wednesday** — 2 portions, 45 min max _(kids at nan's)_
**Thursday** — 4 portions, 30 min max
**Friday** — 4 portions, 45 min max _(treat night OK)_
**Saturday** — 4 portions, 60 min max _(more time to cook)_
**Sunday** — OUT
```

### Preferences display:
```
Your meal preferences:

**Dietary:** Adults: high-protein, low-sugar | Kids: no spicy
**Cuisines:** Italian, Mexican, Asian, British
**Avoid:** aubergine, olives
**Variety:** Max 2× same protein, 1× veggie, 1× fish per week
**Gousto:** 3 nights/week
**Batch cook:** 1/week
```

## Rules

- Keep the interview conversational, not interrogative — batch questions where natural
- For the initial setup, aim for 3-4 messages max from Chris
- Default to sensible values (30 min prep, 4 portions, cook type) if Chris skips
- Always confirm changes back to Chris
- When rating meals, accept casual responses ("loved it" = 5, "meh" = 3, "awful" = 1)
- Protein types: chicken, beef, pork, lamb, fish, seafood, veggie, vegan, mixed
- Recipe sources: gousto, familyfuel, second_brain, manual, takeaway
- Use UK English throughout
