# Reports & Summaries Playbook

READ THIS before producing any report, summary, dashboard, or status overview.

## The Standard

Reports should feel like a personal briefing from a trusted advisor — not raw data,
not a database dump. Lead with insight, support with data, end with actions.

## Structure: The Inverted Pyramid

1. **Headline verdict** — one line, the most important thing (emoji + bold)
2. **Key metrics** — 3-5 numbers that matter, formatted for scanning
3. **Context/trend** — how this compares to previous period or target
4. **Detail** — supporting data, broken down by category if needed
5. **Actions/recommendations** — what to do about it (if applicable)

## What GOOD Looks Like

📊 **Weekly Business Summary** — w/c [date]

📈 **[Verdict]** — £X revenue (+/-Y% vs last week)

🛒 **Orders:** X shipped | Y pending | Z returns
💰 **Revenue:** £X (eBay £X | Amazon £X | BrickLink £X)
📦 **Listings:** X new | Y sold | Net +/-Z
📊 **Margin:** X% avg (target: fetch from business_targets) [✅/⚠️/❌]

**vs Last Week:**
📈📉 Revenue [direction] £X (+/-Y%)
📈📉 Orders [direction] X (+/-Y%)

💡 **Notes**
- 2-3 observations: what's driving performance, anomalies, opportunities
- Actionable suggestions based on the data

## What BAD Looks Like

❌ Raw numbers with no context: "Revenue: £1,247. Orders: 112."
❌ Data without comparison: numbers mean nothing without a baseline
❌ No verdict: make Chris figure out if the period was good or bad
❌ Everything same weight: not distinguishing headlines from detail

## Report Types and Expectations

**Daily summary** — 5-10 lines, headline + key metrics + one insight
**Weekly summary** — 15-25 lines, full structure above
**Status check** ("how's my X?") — 5-8 lines, verdict + metrics + trend
**Comparison** ("X vs Y") — structured side-by-side, verdict first

## Numbers Formatting
- Always include units: £, kg, %, km, etc.
- Round appropriately: £1,247 not £1,247.23
- Use ↑↓ or 📈📉 for trends
- Percentages for change: "+18%" not "went up"
- Bold the most important number in each section

## List/Itemized Output Format

For lists of items (purchases, orders, search results, inventory):

**Use this format:**
```
🛍 4 Jan — C2G 5m UK Power Cable (kettle lead) — £11.99
🛍 20 Jan — Unibond AERO 360° Moisture Absorber Refills (4x450g) — £12.99
🛍 21 Jan — Anker iPhone Lightning Cable 6ft ×2 — £25.80
🛍 30 Jan — Sunnylinn R39 E14 Lava Lamp Bulbs (2 pack) — £6.37

💰 Total: £57.15 (4 orders) 📦 All delivered to Tonbridge
```

**Rules:**
- One line per item: emoji + date/ref + description + price/value
- Use em dash (—) as separator, not hyphen
- Quantity: use × symbol (×2, ×3)
- Summary line at bottom with total and count
- Context note if relevant (delivery location, status, etc.)

**NEVER use vertical format:**
```
❌ Date: 4 Jan
❌ Item: C2G 5m UK Power Cable
❌ Qty: 1
❌ Price: £11.99
❌ [blank line]
❌ Date: 20 Jan...
```

This wastes space and is hard to scan. Keep it horizontal and compact.

---

## Discord Format Examples

**Discord does NOT render markdown tables.** Use bullet lists with inline formatting.

### Daily Summary / Nutrition Check-in
```
📊 **Daily Summary** - Thursday 29 Jan

✅ Calories: 1,786 / 2,100
❌ Protein: 45g / 160g
✅ Carbs: 153g / 263g
✅ Fat: 68g / 70g
❌ Water: 300ml / 3,500ml
❌ Steps: 2,506 / 15,000

⚖️ 88.0kg → 80kg. 8.0kg to go.
```

### Hydration/Steps Check-in
```
🕐 **17:00 Check-in**

💧 Water: 1,300ml / 3,500ml (37%)
▓▓▓▓░░░░░░

🚶 Steps: 218 / 15,000 (1%)
░░░░░░░░░░

---
Hey champ! You're only at 218 steps and 1300ml of water - we've got some serious ground to cover before bedtime. Let's crush those targets! 💧💪
```

### Weekly/Monthly Health Summary
```
⚖️ **Weight**
📉 88.0kg → 87.5kg (-0.5kg)
Range: 87.2 - 88.4kg | Avg: 87.8kg

🍎 **Nutrition**
🔥 1866 cal/day avg | 5 days tracked
🥩 92g protein avg | Hit target: 2/5 days
C: 196g | F: 87g | 💧 2,100ml avg

🏃 **Activity**
👟 108,786 total steps (12,087/day)
🎯 Hit 15,000 goal: 6/9 days (67%)
📊 Best: 15,360 | Worst: 4,027

😴 **Sleep**
💤 6h 42m avg | Best: 7h 30m
```

### Meal Logging Response
```
✅ Logged: Chicken salad - 450 cals, 35g protein

📊 Today so far:
• Calories: 1,250 / 2,100 (60%)
• Protein: 85g / 160g (53%)

Room for ~850 cals. Aim for 75g more protein!
```

### Water Logging Response
```
💧 +500ml logged

▓▓▓▓▓▓░░░░ 2,250ml / 3,500ml (64%)
1,250ml to go!
```

## Key Formatting Rules

- Use ✅ for targets HIT, ❌ for targets MISSED
- Use progress bars: `▓▓▓▓░░░░░░` (▓ filled, ░ empty, ~10 chars)
- Use `|` pipe separators for compact inline stats on ONE line
- Section headers: emoji + **bold title**
- Keep it compact — no excessive blank lines
