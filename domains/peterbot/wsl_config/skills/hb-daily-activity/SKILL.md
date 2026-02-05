---
name: hb-daily-activity
description: Daily listings and sales tracking for Hadley Bricks
trigger:
  - "daily activity"
  - "what did I list today"
  - "today's listings"
  - "what sold today"
  - "bricks activity"
scheduled: true
conversational: true
channel: #peterbot
---

# Hadley Bricks Daily Activity

## Purpose

End-of-day summary showing what was listed and sold today. Helps track daily productivity and sales performance. Scheduled for 9pm daily or triggered conversationally.

## Pre-fetched Data

Data is pre-fetched from the Hadley Bricks API:

- `data.listings_added`: Number of new listings today
- `data.listings`: Array of items listed today
  - `set_number`: LEGO set number
  - `set_name`: Set name
  - `platform`: Where listed
  - `price`: Listed price
- `data.items_sold`: Number of items sold today
- `data.sales`: Array of sales today
  - `set_number`: LEGO set number
  - `set_name`: Set name
  - `platform`: Where sold
  - `price`: Sale price
  - `profit`: Profit on sale
- `data.revenue_today`: Total revenue today
- `data.profit_today`: Total profit today
- `data.error`: Error message if fetch failed

## Output Format

```
📊 **Daily Wrap-Up** - Mon 3 Feb

**Listed Today** (5 items)
• 75192 Millennium Falcon → eBay £649
• 10300 DeLorean → Amazon £139
• 42143 Ferrari Daytona → eBay £349
• 10497 Galaxy Explorer → Amazon £89
• 21330 Home Alone → eBay £229

**Sold Today** (3 items)
• 10300 DeLorean → Amazon £129 (+£34)
• 21330 Home Alone → eBay £199 (+£52)
• 40567 Forest Hideout → eBay £24 (+£8)

💰 Revenue: £352 | Profit: £94
```

## Rules

- Show listings first, then sales
- Include platform for each item
- Show profit per sale in parentheses
- Total revenue and profit at bottom
- If nothing listed/sold, say so positively
- Keep set names concise
- Use £ for all prices

## Productivity Notes

Based on activity levels:
- 0 listings: "No new listings today"
- 1-3 listings: Normal day
- 4-7 listings: "Productive listing day!"
- 8+ listings: "Exceptional listing day! 🔥"

- 0 sales: "Quiet sales day"
- 1-2 sales: Normal day
- 3-5 sales: "Great sales day!"
- 6+ sales: "Outstanding sales! 🎉"

## Error Handling

If data fetch fails:
```
📊 **Daily Wrap-Up** - Mon 3 Feb

⚠️ Could not fetch activity data - is Hadley Bricks running?
```

## Examples

**Active day:**
```
📊 **Daily Wrap-Up** - Mon 3 Feb

**Listed Today** (6 items) - Productive day!
• 75192 Millennium Falcon → eBay £649
• 10300 DeLorean → Amazon £139
• 42143 Ferrari Daytona → eBay £349
• 10497 Galaxy Explorer → Amazon £89
• 21330 Home Alone → eBay £229
• 10303 Loop Coaster → Amazon £299

**Sold Today** (4 items) - Great sales day!
• 10300 DeLorean → Amazon £129 (+£34)
• 21330 Home Alone → eBay £199 (+£52)
• 40567 Forest Hideout → eBay £24 (+£8)
• 76240 Batmobile → eBay £89 (+£23)

💰 Revenue: £441 | Profit: £117
```

**Quiet day:**
```
📊 **Daily Wrap-Up** - Mon 3 Feb

**Listed Today**: No new listings

**Sold Today** (1 item)
• 10300 DeLorean → Amazon £129 (+£34)

💰 Revenue: £129 | Profit: £34
```

**Nothing happened:**
```
📊 **Daily Wrap-Up** - Mon 3 Feb

**Listed Today**: No new listings
**Sold Today**: No sales today

Quiet day - tomorrow's another chance! 💪
```
