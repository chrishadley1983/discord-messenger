---
name: life-admin-compare
description: Compare prices for insurance, MOT, and other renewable obligations using web search
trigger:
  - "compare insurance"
  - "compare my car insurance"
  - "find cheaper"
  - "compare quotes"
  - "cheapest MOT"
  - "insurance comparison"
  - "find a better deal"
  - "shop around"
scheduled: false
conversational: true
channel: "#peterbot"
---

# Life Admin Compare

## Purpose

When an obligation is approaching renewal, help Chris find better deals by searching
the web for comparisons, alternative providers, and current market prices. Phase 2
skill — builds on top of the core life-admin obligation data.

## Pre-fetched Data

No pre-fetched data. The skill fetches obligations on demand:

```
GET http://172.19.64.1:8100/life-admin/obligations?status=active
```

Picks the relevant obligation based on conversation context.

## Workflow

1. **Identify the obligation** — from conversation context or ask Chris which one
2. **Gather current details** — provider, amount, reference number, due date from the obligation record
3. **Perform targeted web searches** based on category:

### Search Strategies by Category

**Insurance** (home/car/life/travel):
- "[provider] [type] insurance UK reviews 2026"
- "cheapest [type] insurance UK 2026"
- "best [type] insurance comparison UK"
- Include current amount for context

**Vehicle MOT**:
- "MOT near [postcode/area] price"
- "cheapest MOT [area] 2026"
- "MOT and service deals [area]"

**Vehicle Service**:
- "[car make model] service cost UK"
- "independent garage vs dealer service [area]"

**Domain Renewal**:
- "[registrar] .co.uk renewal price 2026"
- "cheapest domain registrar UK transfer"
- "domain transfer from [registrar]"

**Utility** (energy/broadband/mobile):
- "[provider] tariff vs alternatives 2026"
- "cheapest [utility type] UK switching"
- "Ofgem price cap [utility type]"

**Home Maintenance** (boiler service, etc.):
- "boiler service cost [area] 2026"
- "[provider] vs independent boiler service"

4. **Present findings** with comparison to current cost

## Output Format

```
**Insurance Comparison — Home Insurance**

Current: Admiral, £342/year (renews 12 Apr)
Reference: HH-123456

**Web search findings:**
• Direct Line: typically £280-320 for similar cover
• Aviva: often 10-15% cheaper for switching customers
• Compare the Market: worth running a quote — many report 20%+ savings
• MoneySupermarket: another good aggregator for home insurance

**Suggestion**: Run a quick quote on Compare the Market or GoCompare before 5 Apr. Your current excess is likely £100-250 — check before switching to ensure like-for-like cover.

Want me to set a reminder to check comparison sites by 5 Apr?
```

### MOT Example

```
**MOT Comparison — VW Polo**

Current: No preferred garage on file
Reg: AB12 CDE | Due: 15 May 2026

**Nearby options:**
• Halfords Autocentre — £35 (online booking, often has £10-off vouchers)
• Kwik Fit — £35-45 (walk-in or book online)
• Local independents — typically £30-40, check Google Maps reviews

**Suggestion**: Book Halfords online — they often have discount codes. Check if your car insurance includes free MOT (some Admiral policies do).

Want me to book a reminder for early May?
```

### Domain Example

```
**Domain Renewal — hadleybricks.co.uk**

Current: 123-reg, £12.99/year (renews 18 Apr)

**Alternatives:**
• Cloudflare Registrar: £5.98/year (.co.uk at cost)
• Namecheap: £7.16/year (first year, then £8.88)
• Transfer takes 5-7 days — start before 11 Apr

**Suggestion**: Cloudflare is cheapest long-term and includes free DNS. Transfer is straightforward — unlock at 123-reg and request transfer.

Want me to add a task to transfer the domain?
```

## Rules

- Always show current cost and provider for context
- Be honest about limitations — "I can't get live quotes, but here's what I found"
- Suggest specific comparison sites relevant to the category
- Offer to set a reminder for the action (uses the remind skill)
- Include the obligation's reference number for easy switching
- For MOT: include garage names, addresses, phone numbers where found
- For insurance: mention excess levels and coverage differences
- Keep it actionable — what should Chris do next?
- Never claim exact quotes — use "typically", "often", "many report"
- Always suggest a deadline to act by (a few days before renewal)
- If Chris asks to compare something not tracked, offer to add the obligation first
- Use web search tools (SearXNG, Brave) for current pricing data
- For energy: reference Ofgem price cap as a benchmark
- Offer to create a reminder or task for the follow-up action
