---
name: meal-rating
description: Prompt for meal ratings and log feedback to meal history
trigger:
  - "rate dinner"
  - "rate that meal"
  - "how was dinner"
  - "dinner was"
  - "meal was"
  - "that was delicious"
  - "that was awful"
scheduled: true
conversational: true
channel: null
---

# Meal Rating

## Purpose

Collect meal ratings after dinner to build a feedback loop for the meal plan generator. Runs as a light-touch evening prompt (scheduled) and responds to conversational triggers.

## Pre-fetched Data

Data fetcher: `meal-rating` — pulls:

- `data.todays_meals` — Today's planned meals from the current meal plan (adults_meal, kids_meal, source_tag)
- `data.already_rated` — Meal names already rated today (to avoid double-prompting)
- `data.date` — Today's date

## Workflow

### Scheduled Prompt (20:30 UK)

1. Check `data.todays_meals` for tonight's planned meal
2. If no meal planned today, respond with `NO_REPLY`
3. If already rated today, respond with `NO_REPLY`
4. Otherwise, send a casual prompt:

```
How was the **Chicken Katsu** tonight? Quick 1-5 and would you make it again?
```

### Conversational Rating

When Chris says something like "rate dinner", "that was great", "dinner was amazing":

1. If Chris includes a rating naturally ("dinner was a solid 4"), extract it
2. If not, check today's meal plan and ask: "The [meal name] — what would you give it, 1-5?"
3. Ask: "Would you make it again?"
4. Log via `POST http://172.19.64.1:8100/meal-plan/history`

### Casual Response Mapping

Accept natural language and map to ratings:

| Chris says | Rating | Would make again |
|---|---|---|
| "amazing", "incredible", "loved it", "best ever" | 5 | true |
| "really good", "great", "delicious" | 4 | true |
| "good", "solid", "fine", "decent" | 3 | true |
| "meh", "okay", "nothing special", "average" | 3 | null (don't assume) |
| "not great", "didn't love it", "bit bland" | 2 | false |
| "awful", "terrible", "hated it", "horrible" | 1 | false |

### Logging

```
POST http://172.19.64.1:8100/meal-plan/history
{
  "date": "2026-03-08",
  "meal_name": "Chicken Katsu",
  "recipe_source": "gousto",
  "protein_type": "chicken",
  "rating": 4,
  "would_make_again": true,
  "notes": "Chris said 'really good'"
}
```

If updating an existing entry (already logged by generator):
```
PATCH http://172.19.64.1:8100/meal-plan/history/{meal_id}/rating
{
  "rating": 4,
  "would_make_again": true,
  "notes": "Chris said 'really good'"
}
```

## Output Format

### Scheduled prompt:
```
How was the **Chicken Katsu** tonight? Quick 1-5 and would you make it again?
```

### After rating:
```
Logged — **Chicken Katsu** gets a 4/5 ⭐ and it's a keeper. Nice one.
```

### If no meal planned:
```
NO_REPLY
```

## Rules

- Keep it brief — one question, one confirmation. Don't interrogate.
- If Chris gives a rating and "would make again" in one message, log both without follow-up
- If Chris just says a number, that's the rating — ask about "make again" only if rating is 3 (ambiguous)
- For ratings 4-5, default would_make_again to true. For 1-2, default to false.
- Don't prompt on days where type is "out", "takeaway", or "skip"
- For takeaway nights, still accept ratings if Chris offers them voluntarily
- The scheduled prompt should NOT fire if Chris already rated today (check data.already_rated)
- Infer protein_type from the meal name where obvious (chicken katsu → chicken, fish pie → fish, veggie curry → veggie)
- Infer recipe_source from the meal plan's source_tag if available
- UK English, casual tone
