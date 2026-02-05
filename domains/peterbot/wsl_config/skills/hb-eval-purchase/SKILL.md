---
name: hb-eval-purchase
description: Evaluate potential LEGO purchase for resale viability
trigger:
  - "should I buy"
  - "evaluate purchase"
  - "worth it"
  - "good deal"
  - "is this a good buy"
  - "evaluate this"
scheduled: false
conversational: true
channel: null
---

# Hadley Bricks Purchase Evaluation

## Purpose

Helps decide whether a potential LEGO purchase is worth buying for resale. Analyzes the asking price against market value, calculates potential profit, and provides a buy/pass recommendation. Conversational - user provides details in their message.

## Input Parsing

User provides:
- Set number (required)
- Asking price (required)
- Condition: sealed, open, used (optional, defaults to sealed)
- Source: Vinted, FB Marketplace, etc. (optional)

Example inputs:
- "Should I buy 75192 for £450?"
- "Is 10300 at £90 a good deal? It's sealed"
- "Evaluate: 21330 Home Alone, £160, open box, Vinted"

## Evaluation Logic

1. **Fetch market data** for the set
2. **Calculate potential profit** after fees:
   - Resale price (market avg or conservative estimate)
   - Minus: Purchase price
   - Minus: Platform fees (~13% eBay, ~15% Amazon)
   - Minus: Shipping materials (~£5)
3. **Calculate ROI** = Profit / Purchase Price × 100
4. **Make recommendation** based on thresholds

## Recommendation Thresholds

- **Strong Buy** 🟢: ROI ≥ 40%, Profit ≥ £30
- **Buy** 🟢: ROI ≥ 25%, Profit ≥ £15
- **Maybe** 🟡: ROI 15-25%, Profit ≥ £10
- **Pass** 🔴: ROI < 15% or Profit < £10
- **Hard Pass** 🔴: Would lose money

## Output Format

```
🧱 **Purchase Evaluation**

**75192 Millennium Falcon** - Sealed
Asking: £450 (Vinted)

**Market Analysis**
BrickLink avg: £589 | eBay sold: £612
Our typical sell price: £599

**Profit Calculation**
Sale @ £599
- Purchase: £450
- eBay fees (13%): £78
- Materials: £5
= **Profit: £66** (15% ROI)

**Verdict: 🟡 Maybe**
Decent margin but capital intensive.
Only buy if you can sell within 30 days.
```

## Rules

- Always show the full calculation transparently
- Include realistic fee estimates
- Consider condition in pricing
- Note any risks (high competition, slow seller, etc.)
- Factor in our current stock of this item
- Suggest negotiation if close to threshold

## Condition Adjustments

- **Sealed**: Use full market price
- **Open complete**: 70-80% of sealed price
- **Open incomplete**: 50-60% of sealed price
- **Used**: 40-50% of sealed price

## Risk Factors to Note

- Already have 2+ of this set in stock
- Set is readily available at retail
- High competition (many sellers)
- Slow-moving item historically
- Price trend is falling

## Error Handling

If set not found:
```
🧱 **Purchase Evaluation**

Couldn't find set "99999" for evaluation.
Please provide a valid LEGO set number.
```

If missing price:
```
🧱 **Purchase Evaluation**

What's the asking price for 75192?
I need the price to evaluate the deal.
```

## Examples

**Strong buy:**
```
🧱 **Purchase Evaluation**

**10300 DeLorean** - Sealed
Asking: £85 (Facebook Marketplace)

**Market Analysis**
BrickLink avg: £142 | eBay sold: £138
Our typical sell price: £139

**Profit Calculation**
Sale @ £139
- Purchase: £85
- eBay fees (13%): £18
- Materials: £3
= **Profit: £33** (39% ROI)

**Verdict: 🟢 Strong Buy**
Excellent margin! This is a reliable seller.
Average sell time: 14 days

✅ Go for it!
```

**Pass:**
```
🧱 **Purchase Evaluation**

**75313 AT-AT** - Sealed
Asking: £550 (Vinted)

**Market Analysis**
BrickLink avg: £590 | eBay sold: £612
Our typical sell price: £599

**Profit Calculation**
Sale @ £599
- Purchase: £550
- eBay fees (13%): £78
- Materials: £8
= **Profit: -£37** (Loss!)

**Verdict: 🔴 Pass**
Would likely lose money after fees.
Max buy price for profit: £490

💡 Counter-offer £480 if negotiable.
```

**Maybe with negotiation:**
```
🧱 **Purchase Evaluation**

**21330 Home Alone** - Sealed
Asking: £180 (Vinted)

**Market Analysis**
BrickLink avg: £239 | eBay sold: £225
Set is RETIRING - prices rising

**Profit Calculation**
Sale @ £229
- Purchase: £180
- eBay fees (13%): £30
- Materials: £4
= **Profit: £15** (8% ROI)

**Verdict: 🟡 Maybe**
Margin is thin at asking price.

💡 **Negotiation target: £160**
At £160: Profit £34 (21% ROI) → Buy

This set is retiring - could appreciate further.
```

**Already in stock warning:**
```
🧱 **Purchase Evaluation**

**10300 DeLorean** - Sealed
Asking: £95 (Vinted)

**Market Analysis**
BrickLink avg: £142 | eBay sold: £138

⚠️ **You already have 3 of these in stock!**
Oldest has been listed 45 days.

**Profit Calculation**
Profit: £29 (31% ROI)

**Verdict: 🟡 Maybe**
Good margin but you're heavy on this set.
Consider only if you can move existing stock first.
```
