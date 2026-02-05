---
name: daily-recipes
description: Daily recipe recommendations matching health targets
trigger:
  - "recipe ideas"
  - "what should I cook"
  - "recipe recommendations"
scheduled: true
conversational: true
channel: #food-log
---

# Daily Recipe Recommendations

## Purpose

Every morning at 06:30 UK, search for 5 tasty recipes that fit Chris's current nutrition targets. Focus on high-protein, calorie-appropriate meals that are practical and appealing.

## Data Requirements

### 1. Fetch Current Targets First

```bash
curl http://172.19.64.1:8100/nutrition/goals
```

Expected response:
```json
{
  "calories_target": 2100,
  "protein_target_g": 160,
  "carbs_target_g": 260,
  "fat_target_g": 70,
  "target_weight_kg": 77
}
```

### 2. Search Strategy

Search across multiple sources for variety:
- **UK Sources (REQUIRE 2+ of 5)**: BBC Good Food, Tesco Real Food, Gousto, Joe Wicks/Lean in 15, Mob Kitchen, Jamie Oliver
- **Reddit**: r/fitmeals, r/mealprep, r/EatCheapAndHealthy, r/1500isplenty
- **X (Twitter)**: #mealprep, #highprotein, #fitfood, fitness food accounts
- **YouTube**: Meal prep channels, fitness cooking
- **Web**: Recipe sites with macro info (MyFitnessPal recipes, Skinnytaste, etc.)

### 3. Recipe Criteria

Filter for recipes that:
- **Protein**: ≥30g per serving (high priority - Chris targets 160g/day)
- **Calories**: 400-700 per serving (practical for meal planning)
- **Practical**: <45 min prep, common ingredients
- **Appealing**: Looks good, positive reviews/engagement

## Output Format

```
🍳 **Daily Recipe Ideas** - [Date]

Based on your targets: 2,100 cal | 160g protein

**1. [Recipe Name]** ⭐
[One-line description of the dish]
📊 ~[cal] cal | [P]g protein | [C]g carbs | [F]g fat
⏱️ [prep time]
🔗 [Source Name](url)

**2. [Recipe Name]**
[One-line description]
📊 ~[cal] cal | [P]g protein | [C]g carbs | [F]g fat
⏱️ [prep time]
🔗 [Source Name](url)

**3. [Recipe Name]**
...

**4. [Recipe Name]**
...

**5. [Recipe Name]**
...

💡 **Today's pick:** [Brief recommendation of which one suits today - e.g., "The Greek chicken bowl is quick for a busy weeknight"]
```

## Search Process

1. **Fetch nutrition goals** from Hadley API
2. **Run 3-4 web searches** with varied queries:
   - "high protein meal prep [protein]g"
   - "fitness recipes [calorie range] calories"
   - "Reddit fitmeals high protein easy"
   - "YouTube meal prep [current month] 2026"
3. **Fetch promising pages** with WebFetch to verify macros
4. **Select 5 diverse recipes** (avoid all chicken/all similar dishes)
5. **Format with actual macro data** (don't guess - find real numbers)

## Quality Standards

- **Real recipes only**: Must have actual source links that work
- **Accurate macros**: From the recipe source, not estimated
- **Variety**: Mix of proteins (chicken, beef, fish, eggs, vegetarian)
- **Practical**: Ingredients available in UK supermarkets
- **Seasonal awareness**: Consider what's in season

## Rules

- Always fetch current goals - don't assume targets
- Link to actual recipe pages, not search results
- If a recipe doesn't have macro info, skip it
- Prioritize protein density (g protein per 100 cal)
- Include at least one quick option (<20 min)
- Include at least one meal prep friendly option
- **MUST include at least 2 UK-based sources** (BBC Good Food, Tesco, Gousto, Joe Wicks, Mob Kitchen, Jamie Oliver)
- Never recommend the same recipe two days in a row (check recent posts if possible)

## Conversational Use

When triggered conversationally ("what should I cook tonight?"):
- Same format but can be more focused (e.g., "dinner ideas" = focus on dinner-appropriate recipes)
- Can ask clarifying questions: "Quick weeknight dinner or something more elaborate?"
- Reference recent meals if context available

## Example Output

```
🍳 **Daily Recipe Ideas** - Wed 5 Feb

Based on your targets: 2,100 cal | 160g protein

**1. Greek Chicken Power Bowl** ⭐
Grilled chicken, quinoa, cucumber, feta, olives, tzatziki
📊 ~520 cal | 45g protein | 38g carbs | 18g fat
⏱️ 25 min
🔗 [Skinnytaste](https://skinnytaste.com/greek-chicken-bowl)

**2. Cottage Cheese Protein Pancakes**
Fluffy pancakes with cottage cheese base, berries, maple
📊 ~380 cal | 32g protein | 42g carbs | 8g fat
⏱️ 15 min
🔗 [r/fitmeals](https://reddit.com/r/fitmeals/...)

**3. Beef & Broccoli Stir Fry**
Lean beef strips, broccoli, garlic soy sauce, served with rice
📊 ~580 cal | 42g protein | 48g carbs | 16g fat
⏱️ 20 min
🔗 [YouTube - Joshua Weissman](https://youtube.com/...)

**4. Tuna Pasta Bake** 🇬🇧
High protein pasta bake with tuna, sweetcorn, light cheese sauce
📊 ~620 cal | 48g protein | 62g carbs | 14g fat
⏱️ 35 min
🔗 [BBC Good Food](https://bbcgoodfood.com/...)

**5. Joe Wicks Chicken Stir Fry** 🇬🇧
Lean in 15 style - quick chicken with veg and soy
📊 ~480 cal | 38g protein | 28g carbs | 16g fat
⏱️ 15 min
🔗 [The Body Coach](https://thebodycoach.com/...)

💡 **Today's pick:** The Greek chicken bowl is perfect for a midweek dinner - 25 mins and you'll smash your protein target.
```
