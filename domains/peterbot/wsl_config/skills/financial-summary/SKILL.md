---
name: financial-summary
description: Shareable financial position summary - net worth, savings, FIRE progress, budget, and business P&L
trigger:
  - "financial summary"
  - "financial position"
  - "share my finances"
  - "money summary"
  - "how am I doing financially"
  - "financial overview"
scheduled: false
conversational: true
channel: null
---

# Financial Summary (Shareable)

## Purpose

Generates a clean, shareable financial position summary combining personal and business finances. Designed to be shared with a partner, financial advisor, or saved as a monthly snapshot.

## Pre-fetched Data

Data is pre-fetched from Supabase finance schema:

- `data.net_worth`: Total net worth with breakdown by account type
  - `total`: Total net worth figure
  - `prev_total`: Previous month total (for change calculation)
  - `by_type`: Dict of account type → balance (current, savings, isa, investment, pension, property, credit)
  - `top_accounts`: List of top 10 accounts by balance
- `data.budget`: Current month budget vs actual
  - `income_budget` / `income_actual`: Income totals
  - `expense_budget` / `expense_actual`: Expense totals
  - `net_position`: Income actual minus expense actual
  - `over_budget`: List of categories over budget
  - `under_budget`: List of categories under budget
- `data.savings`: Current month savings rate
  - `rate_actual`: Actual savings rate percentage
  - `rate_budget`: Target savings rate percentage
  - `savings_actual`: Actual savings amount
- `data.fire`: FIRE progress
  - `portfolio`: Current investment portfolio value
  - `target`: FI number (annual expenses / SWR)
  - `progress_pct`: Percentage towards FI
  - `years_to_fi`: Projected years to financial independence
  - `coast_fi`: Coast FI number
  - `coast_fi_reached`: Boolean
- `data.business`: Business P&L (current month)
  - `revenue`: Total revenue
  - `profit`: Net profit
  - `margin`: Profit margin percentage
  - `sales_count`: Number of sales
- `data.month_label`: e.g. "March 2026"
- `data.error`: Error message if fetch failed

## Output Format

Deploy to surge.sh for a shareable link using the Hadley API:

```
POST http://172.19.64.1:8100/deploy/surge
{"html": "<the generated HTML>", "domain": "chris-finances.surge.sh", "filename": "index.html"}
```

Also post a Discord summary:

```
📊 **Financial Position** — March 2026

💰 **Net Worth: £XXX,XXX** (+£X,XXX vs last month)
Current £XX,XXX | Savings £XX,XXX | ISAs £XX,XXX
Investments £XX,XXX | Pensions £XX,XXX | Property £XXX,XXX
Credit Cards -£X,XXX

📈 **Savings Rate: XX%** (target: XX%)
Saved £X,XXX this month | Net position: +£X,XXX

🔥 **FIRE Progress: XX%**
▓▓▓▓▓▓░░░░ £XXX,XXX / £XXX,XXX
~XX years to FI | Coast FI: ✅ Reached / £XX,XXX to go

💼 **Hadley Bricks** — March
Revenue £X,XXX | Profit £XXX (XX% margin) | XX sales

🔗 Full report: https://chris-finances.surge.sh
```

### HTML Report Format

Generate a clean, minimal HTML page with:
- Title: "Financial Position — [Month Year]"
- Sections: Net Worth, Budget, Savings, FIRE Progress, Business
- Use a clean sans-serif font, light background
- Tables for breakdowns, bold key figures
- All amounts in GBP (£)
- No external dependencies (inline CSS only)
- Mobile-friendly (responsive)

## Rules

- Lead with net worth — it's the headline number
- Always show month-on-month change for net worth
- Show savings rate with target comparison
- FIRE progress with visual progress indicator
- Business P&L as a one-liner unless asked for detail
- Deploy HTML to surge.sh for shareable link
- Post compact Discord summary with link
- All currency in GBP, rounded to nearest pound for large figures
- Do NOT include individual transaction details — this is a position summary
- If any section fails to fetch, show the rest and note what's missing

## Error Handling

If data fetch fails entirely:
```
📊 **Financial Summary**

⚠️ Could not fetch financial data. Is Supabase accessible?
```

If partial failure, show what's available and note missing sections.
