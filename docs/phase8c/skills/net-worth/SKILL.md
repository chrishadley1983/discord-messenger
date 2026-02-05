# Net Worth

## Purpose
Calculate and track total net worth over time.

## Triggers
- "net worth", "what am I worth"
- "total wealth", "how much do I have"
- "wealth update", "financial position"

## Schedule
- 09:00 1st of month (monthly snapshot)

## Data Source
Finance Tracker (Supabase)
- Tables: `accounts`, `wealth_snapshots`
- Query: Sum of latest snapshots where `include_in_net_worth = true`

## Pre-fetcher
`get_net_worth_data()` - fetches:
- Current net worth (sum of all qualifying accounts)
- Breakdown by account type
- Historical comparison (last month, last year, all-time)
- FIRE progress (if parameters set)

## SQL Query
```sql
-- Current net worth
SELECT 
  a.type,
  SUM(ws.balance) as total
FROM accounts a
JOIN LATERAL (
  SELECT balance 
  FROM wealth_snapshots 
  WHERE account_id = a.id 
  ORDER BY date DESC 
  LIMIT 1
) ws ON true
WHERE a.is_active = true 
  AND a.include_in_net_worth = true
GROUP BY a.type;

-- Historical comparison
SELECT 
  date,
  SUM(balance) as total
FROM wealth_snapshots ws
JOIN accounts a ON ws.account_id = a.id
WHERE a.include_in_net_worth = true
  AND date IN (
    (SELECT MAX(date) FROM wealth_snapshots),  -- Latest
    (SELECT MAX(date) FROM wealth_snapshots WHERE date < date_trunc('month', CURRENT_DATE)),  -- Last month
    (SELECT MAX(date) FROM wealth_snapshots WHERE date < CURRENT_DATE - INTERVAL '1 year')  -- Last year
  )
GROUP BY date
ORDER BY date;
```

## Output Format

```
💎 **Net Worth**

**Total: £247,892.45**

**Breakdown:**
🏦 Cash & Savings: £27,583.68 (11%)
📈 Investments: £46,024.67 (19%)
🏠 Property Equity: £85,000.00 (34%)
👴 Pensions: £89,284.10 (36%)

**Trend:**
• vs Last Month: +£3,456 (+1.4%)
• vs Last Year: +£34,567 (+16.2%)
• All-time growth: +£127,892

**FIRE Progress:**
🎯 Target: £625,000 (25x £25k spend)
📊 Progress: 39.7%
📅 At current rate: ~12 years to FIRE
```

## Guidelines
- Exclude accounts marked `include_in_net_worth = false`
- Include property equity if tracked
- Show percentage allocation
- Calculate FIRE progress if parameters exist
- Note if any balances are stale (>30 days old)

## FIRE Calculation
If `fire_parameters` table has data:
```
Target = annual_spend / withdrawal_rate
Progress = current_net_worth / target * 100
Years to FIRE = (target - current) / annual_savings_rate
```

## Conversational
Yes - follow-ups:
- "Show breakdown"
- "How much have I gained this year?"
- "Update FIRE target"
- "What's my savings rate?"
- "When can I retire?"
