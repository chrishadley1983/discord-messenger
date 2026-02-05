# Budget Check

## Purpose
Compare actual spending against budget targets.

## Triggers
- "budget", "how's my budget"
- "am I on budget", "budget check"
- "over budget", "under budget"
- "budget status"

## Schedule
- 09:00 Mon (weekly budget check)
- 09:00 15th of month (mid-month review)

## Data Source
Finance Tracker (Supabase)
- Tables: `transactions`, `categories`, `budgets`
- Query: Actual vs budget by category for current month

## Pre-fetcher
`get_budget_check_data()` - fetches:
- Budget per category (current month)
- Actual spend per category
- Variance (under/over)
- Days remaining in month
- Projected month-end (at current pace)

## SQL Query
```sql
SELECT 
  c.name as category,
  c.group_name,
  b.amount as budget,
  COALESCE(SUM(ABS(t.amount)), 0) as spent,
  b.amount - COALESCE(SUM(ABS(t.amount)), 0) as remaining
FROM budgets b
JOIN categories c ON b.category_id = c.id
LEFT JOIN transactions t ON t.category_id = c.id 
  AND t.date >= date_trunc('month', CURRENT_DATE)
  AND t.amount < 0
WHERE b.year = EXTRACT(YEAR FROM CURRENT_DATE)
  AND b.month = EXTRACT(MONTH FROM CURRENT_DATE)
GROUP BY c.name, c.group_name, b.amount
ORDER BY (COALESCE(SUM(ABS(t.amount)), 0) / b.amount) DESC;
```

## Output Format

```
📊 **Budget Check** (January - Day 18 of 31)

**Overall:** £2,847 of £4,200 (68%)
📈 On track - £1,353 remaining

**By Category:**
🔴 Eating Out: £156 / £120 (130%) ⚠️ OVER
🟡 Groceries: £387 / £450 (86%) - £63 left
🟢 Transport: £412 / £500 (82%) - £88 left
🟢 Entertainment: £89 / £150 (59%) - £61 left
⚪ Subscriptions: £64 / £65 (98%) - £1 left

**At Current Pace:**
Projected total: £4,890 (£690 over budget)
Adjust: Reduce daily spend by £25
```

## Status Indicators
- 🔴 Over budget (>100%)
- 🟡 Warning (>80%)
- 🟢 On track (<80%)
- ⚪ Near limit (95-100%)

## Guidelines
- Calculate days remaining for "pace" projection
- Highlight categories over budget
- Show actionable insight ("reduce daily spend by £X")
- For weekly check, focus on problem areas
- Include projected month-end total

## Conversational
Yes - follow-ups:
- "What's causing the overspend?"
- "Show me eating out transactions"
- "What if I stop eating out?"
- "Adjust groceries budget to £500"
