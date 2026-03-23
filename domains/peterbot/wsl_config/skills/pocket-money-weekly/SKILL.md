---
name: pocket-money-weekly
description: Sunday pocket money calculation — present grid to Chris for approval, then credit balances
trigger:
  - "pocket money"
  - "pocket money update"
  - "kids pocket money"
scheduled: true
conversational: true
channel: "#peterbot"
---

# Weekly Pocket Money Calculation

## Purpose

Every Sunday morning, calculate each child's pocket money for the week based on their daily grid (room tidy, behaviour, homework, special boost). Present the grid to Chris for approval or adjustment, then credit the approved amounts.

## Pre-fetched Data

The data fetcher calls the IHD dashboard API at `http://192.168.0.110:3000/api/kids/pocket-money/calculate` and returns:

```json
{
  "week": "2026-03-09",
  "message": "Pocket Money Summary for week of 2026-03-09\n\nEmmie's Pocket Money Grid:\n         Mon  Tue  Wed  Thu  Fri  Sat  Sun\nRoom Tidy ✓   ✓   ✓   ✗   ✓   ✓   ✓  (6 × 40p = £2.40)\nBehaviour ✓   ✓   ✓   ✓   ✓   ✓   ✓  (7 × 20p = £1.40)\nHomework  ✓   ✓   ✗   ✓   ✓   -   -  (4 × 20p = £0.80)\nBoost     ✗   ✗   ✗   ✗   ✗   ✗   ✗  (0 × £2.00 = £0.00)\nTotal: £4.60\n\nMax's Pocket Money Grid:\n...",
  "emmie": { "total": 460, "formatted": "£4.60" },
  "max": { "total": 380, "formatted": "£3.80" }
}
```

## Rates

- Room Tidy: 40p per day
- Behaviour: 20p per day
- Homework: 20p per day
- Special Boost: £2.00 per day (rare — only for exceptional days)

## Output Format

Present the grid clearly to Chris and ask for approval:

```
💰 POCKET MONEY — Week of 9 Mar

EMMIE 🦄
         Mon  Tue  Wed  Thu  Fri  Sat  Sun
Room     ✓    ✓    ✓    ✗    ✓    ✓    ✓   (6 × 40p = £2.40)
Behav    ✓    ✓    ✓    ✓    ✓    ✓    ✓   (7 × 20p = £1.40)
HW       ✓    ✓    ✗    ✓    ✓    -    -   (4 × 20p = £0.80)
Boost    ✗    ✗    ✗    ✗    ✗    ✗    ✗   (0 × £2 = £0.00)
➡️ Emmie earns: £4.60

MAX 🦈
         Mon  Tue  Wed  Thu  Fri  Sat  Sun
Room     ✓    ✓    ✓    ✓    ✓    ✓    ✗   (6 × 40p = £2.40)
Behav    ✓    ✓    ✓    ✓    ✓    ✓    ✓   (7 × 20p = £1.40)
HW       ✓    ✗    ✓    ✓    ✗    -    -   (3 × 20p = £0.60)
Boost    ✗    ✗    ✗    ✗    ✗    ✗    ✗   (0 × £2 = £0.00)
➡️ Max earns: £4.40

💷 Total this week: £9.00

Chris — shall I credit these amounts? Reply:
• "approve" — credit as shown
• "emmie 500 max 400" — override with custom amounts (in pence)
• Or tell me what to adjust
```

## Approval Flow

After Chris responds:

### If "approve"
POST to `http://192.168.0.110:3000/api/kids/pocket-money` for each child:

```bash
curl -X POST http://192.168.0.110:3000/api/kids/pocket-money \
  -H "Content-Type: application/json" \
  -d '{"child": "emmie", "amount": 460, "category": "pocket_money", "description": "Week of 9 Mar — pocket money", "source": "peter"}'
```

Then confirm: "✅ Credited £4.60 to Emmie and £4.40 to Max. New balances: Emmie £38.60, Max £41.40"

### If custom amounts
Parse the amounts and POST with those instead.

### If adjustment request
Adjust the grid or amounts as instructed and re-present for approval.

## Rules

- Always show the full grid — Chris needs to see what each tick/cross represents
- Format amounts in pounds with 2 decimal places
- Use the `message` field from pre-fetched data as the basis — it has the formatted grid
- The `total` fields are in pence — convert for display
- After crediting, always confirm new balances
- If the grid is empty (no ticks at all), mention that the grid needs filling in first
- This is a fun family thing — keep the tone warm and encouraging
- If data fetch fails, tell Chris and suggest checking the dashboard
