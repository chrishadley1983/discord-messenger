---
name: hb-set-lookup
description: Look up LEGO set information and pricing
trigger:
  - "look up"
  - "set info"
  - "price check"
  - "what's the price of"
  - "tell me about set"
  - "set details"
scheduled: false
conversational: true
channel: null
---

# Hadley Bricks Set Lookup

## Purpose

Looks up detailed information about any LEGO set including Brickset data, current market pricing, and whether we have it in stock. Conversational - user provides set number in their message.

## Pre-fetched Data

**Note:** This skill requires parsing a set number from the user's message. The data fetcher needs the set number passed from context.

Data from the Hadley Bricks API:

- `data.set_info`: Brickset information
  - `set_number`: e.g., "75192-1"
  - `name`: Set name
  - `year`: Release year
  - `theme`: LEGO theme
  - `subtheme`: Subtheme if applicable
  - `pieces`: Piece count
  - `minifigs`: Minifigure count
  - `rrp`: Recommended retail price
  - `retired`: Whether set is retired
  - `retired_date`: When it retired
  - `availability`: Current availability status
  - `rating`: Brickset community rating
- `data.pricing`: Market pricing data
  - `bricklink_avg`: BrickLink 6-month average
  - `bricklink_min`: BrickLink minimum
  - `ebay_sold_avg`: eBay sold average (last 90 days)
  - `amazon_price`: Current Amazon price
  - `price_trend`: "rising", "stable", "falling"
- `data.current_stock`: Our inventory
  - `in_stock`: Boolean
  - `quantity`: How many we have
  - `conditions`: Array of conditions we have
  - `our_cost`: What we paid
  - `listed_price`: What we're selling for
  - `platform`: Where it's listed
- `data.error`: Error message if fetch failed

## Set Number Parsing

Extract set number from user message:
- "look up 75192" → 75192
- "what's the price of 10300" → 10300
- "tell me about the millennium falcon" → Search by name (if supported)
- "75192-1" → 75192-1 (with variant)

## Output Format

```
🧱 **75192 Millennium Falcon**

**Set Info**
Theme: Star Wars UCS | Year: 2017
Pieces: 7,541 | Minifigs: 8
RRP: £649.99 | Status: Available

**Market Pricing**
BrickLink avg: £589 (min £520)
eBay sold avg: £612
Amazon: £649 (RRP)
📈 Trend: Rising

**Your Stock**
✅ 2 in stock (1 sealed, 1 open complete)
Cost: £480 | Listed: £599 on eBay
Margin: £119 (25%)
```

## Rules

- Always identify the set number first
- Show comprehensive set information
- Include multiple pricing sources
- Show our stock status prominently
- Calculate potential margin if we have it
- Note if set is retired (affects pricing)
- If set number not found, suggest alternatives

## Stock Status Indicators

- ✅ In stock: Show quantity and conditions
- ❌ Not in stock: "Not currently in inventory"
- 📦 Listed: Show where and at what price
- ⬜ Unlisted: Note if in stock but not listed

## Error Handling

If set number not found:
```
🧱 **Set Lookup**

Couldn't find set "99999".

Did you mean:
• 9999 Bucket Wheel Excavator
• 99999-1 doesn't exist

Try with the full set number (e.g., 75192).
```

If API fails:
```
🧱 **Set Lookup**

⚠️ Could not fetch set data - is Hadley Bricks running?

Try: https://brickset.com/sets/75192-1
```

## Examples

**Full lookup:**
```
🧱 **10300 Back to the Future DeLorean**

**Set Info**
Theme: Icons | Year: 2022
Pieces: 1,872 | Minifigs: 1 (Doc Brown)
RRP: £159.99 | Status: Available

**Market Pricing**
BrickLink avg: £142 (min £125)
eBay sold avg: £138
Amazon: £144.99 (9% off RRP)
📉 Trend: Falling (high availability)

**Your Stock**
✅ 3 in stock (all sealed)
Cost: £105 avg | Listed: £139 on Amazon, £145 on eBay
Margin: ~£34 (32%)
```

**Retired set:**
```
🧱 **21325 Medieval Blacksmith**

**Set Info**
Theme: Ideas | Year: 2021
Pieces: 2,164 | Minifigs: 4
RRP: £134.99 | ⚠️ RETIRED (Jan 2024)

**Market Pricing**
BrickLink avg: £189 (min £165)
eBay sold avg: £195
Amazon: £219 (3rd party)
📈 Trend: Rising (retired, popular)

**Your Stock**
❌ Not in inventory

💡 Good arbitrage target if found under £140.
```

**Quick price check:**
User: "Price of 75313?"
```
🧱 **75313 AT-AT** (Star Wars)

RRP: £699.99 | Status: Available
Market: £580-650 (BrickLink) | eBay avg: £612

We have: 1 sealed @ £599 (cost £490)
```
