---
name: shopping-list-pdf
description: Generate a printable shopping list PDF with categories and checkboxes
trigger:
  - "shopping list"
  - "grocery list"
  - "printable list"
  - "make a shopping list PDF"
  - "print shopping list"
scheduled: false
conversational: true
channel: null
---

# Shopping List PDF

## Purpose

Generate a printable A4 shopping list PDF when Chris asks. The PDF has a 2-column layout with blue category headers, underlines, and checkboxes next to each item. Saved to Google Drive (`G:\My Drive\AI Work\Shopping Lists`).

## Workflow

1. **Parse items** — Extract the shopping items from Chris's message. He may give a flat list, categorised list, or ask you to build one from a recipe/meal plan.
2. **Categorise** — Organise items into supermarket categories. If Chris already provided categories, respect them. Otherwise, assign sensible categories from the list below.
3. **Call API** — Send the categorised items to the Hadley API to generate the PDF.
4. **Respond** — Tell Chris the PDF has been saved and where to find it.

## Category Guidelines

Use these standard supermarket categories (only include categories that have items):

- **Fruit & Veg** — fresh produce, salad, herbs
- **Dairy & Eggs** — milk, cheese, yoghurt, eggs, butter
- **Meat & Fish** — fresh/frozen meat, poultry, fish, seafood
- **Bakery** — bread, rolls, wraps, pastries
- **Frozen** — frozen meals, ice cream, frozen veg
- **Drinks** — water, juice, squash, fizzy drinks, alcohol
- **Cupboard** — tinned goods, pasta, rice, sauces, spices, oil, flour
- **Snacks** — crisps, biscuits, chocolate, nuts
- **Household** — cleaning, laundry, bin bags, kitchen roll
- **Toiletries** — shampoo, toothpaste, deodorant
- **Baby & Kids** — nappies, wipes, baby food (if applicable)
- **Other** — anything that doesn't fit above

## API Call

```
POST http://172.19.64.1:8100/shopping-list/generate
Content-Type: application/json

{
  "categories": {
    "Fruit & Veg": ["Bananas", "Broccoli", "Carrots"],
    "Dairy & Eggs": ["Semi-skimmed milk", "Cheddar cheese"],
    "Meat & Fish": ["Chicken breasts"]
  },
  "title": "Weekly Shop"
}
```

**Optional parameter:**
- `output_dir` — Where to save the PDF. Defaults to `G:\My Drive\AI Work\Shopping Lists`

**Response:**
```json
{
  "status": "created",
  "filename": "shopping_list_20260207_143022.pdf",
  "path": "G:\\My Drive\\AI Work\\Shopping Lists\\shopping_list_20260207_143022.pdf"
}
```

## Output Format

After generating the PDF, respond conversationally:

```
Done! Your shopping list PDF is saved to Google Drive:
**shopping_list_20260207_143022.pdf**

X categories, Y items total. Ready to print.
```

## Rules

- If Chris gives a vague request like "make a shopping list", ask what items to include.
- If Chris gives a recipe or meal plan, extract the ingredients and categorise them.
- Combine duplicate items (e.g. "2x chicken breast" not two separate entries).
- Use UK spelling and naming (courgette not zucchini, coriander not cilantro).
- Keep item names concise but clear (e.g. "Semi-skimmed milk 2L" not just "milk").
- The title defaults to "Shopping List" — use something more specific if context suggests it (e.g. "Meal Prep - Week 7", "BBQ Shopping").
