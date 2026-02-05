# Spending Summary

## Purpose
Show current month's spending breakdown by category.

## Triggers
- "spending", "how much have I spent"
- "spending this month", "monthly spending"
- "where's my money going"
- "spending breakdown", "expenses"

## Schedule
- 09:00 1st of month (previous month summary)

## Data Source
Finance Tracker (Supabase)
- Tables: `transactions`, `categories`
- Query: Sum transactions by category for current month

## Pre-fetcher
`get_spending_summary_data()` - fetches:
- Total spending this month
- Breakdown by category group (Essential, Lifestyle, etc.)
- Top 5 categories by spend
- Comparison to last month

## SQL Query
```sql
SELECT 
  c.group_name,
  c.name as category,
  SUM(t.amount) as total
FROM transactions t
JOIN categories c ON t.category_id = c.id
WHERE t.date >= date_trunc('month', CURRENT_DATE)
  AND t.amount < 0  -- expenses only
  AND c.is_income = false
GROUP BY c.group_name, c.name
ORDER BY total ASC;  -- most negative first
```

## Output Format

```
💰 **Spending This Month** (January)

**Total:** £2,847.32

**By Category:**
🏠 Housing: £1,200.00
🚗 Transport: £412.50
🛒 Groceries: £387.22
🍽️ Eating Out: £156.80
🎮 Entertainment: £89.50
📱 Subscriptions: £64.30
...

**vs Last Month:** +£234 (8.9% more)

Top increase: Eating Out (+£67)
```

## Guidelines
- Show expenses as positive numbers (easier to read)
- Group by category_group for high-level view
- Highlight significant changes vs last month
- Note any unusually high categories
- For scheduled monthly summary, compare to previous month

## Conversational
Yes - follow-ups:
- "Show me groceries breakdown"
- "What about last month?"
- "Why is transport so high?"
- "Compare to same month last year"

## Category Groups (from schema)
Expect groups like:
- Essential (Housing, Utilities, Groceries)
- Transport
- Lifestyle (Eating Out, Entertainment)
- Subscriptions
- Health
- Personal
