# Account Balances

## Purpose
Show current balances across all financial accounts.

## Triggers
- "account balances", "balances"
- "how much in my accounts"
- "bank balance", "savings", "ISA", "SIPP", "pension"
- "what's in my {account}?"
- "investments", "portfolio", "how are my investments"

## Schedule
- Part of monthly net worth update

## Data Source
Finance Tracker (Supabase)
- Tables: `accounts`, `wealth_snapshots`
- Query: Latest snapshot for each active account

## Pre-fetcher
`get_account_balances_data()` - fetches:
- All active accounts with latest balance
- Grouped by account type
- Change since last snapshot (if available)

## SQL Query
```sql
SELECT 
  a.id,
  a.name,
  a.type,
  a.provider,
  a.icon,
  ws.balance,
  ws.date as snapshot_date,
  LAG(ws.balance) OVER (PARTITION BY a.id ORDER BY ws.date) as prev_balance
FROM accounts a
LEFT JOIN LATERAL (
  SELECT balance, date 
  FROM wealth_snapshots 
  WHERE account_id = a.id 
  ORDER BY date DESC 
  LIMIT 1
) ws ON true
WHERE a.is_active = true 
  AND a.is_archived = false
ORDER BY a.type, a.sort_order;
```

## Output Format

```
🏦 **Account Balances**

**Current Accounts**
• HSBC Current: £3,456.78
• Monzo: £892.34

**Savings**
• Marcus: £15,000.00
• HSBC ISA: £8,234.56

**Investments**
• Vanguard ISA: £42,567.89 (+£1,234 this month)
• Trading 212: £3,456.78

**Pensions**
• Work Pension: £67,890.12
• SIPP: £12,345.67

**Total: £154,844.14**
```

## Account Types (from schema)
- `current` - Day-to-day accounts
- `savings` - Savings accounts
- `isa` - ISA accounts
- `investment` - Investment accounts
- `pension` - Pension accounts
- `property` - Property equity
- `credit` - Credit cards (negative)
- `other` - Other

## Guidelines
- Group by account type
- Show change if significant (>£100 or >5%)
- Credit accounts show as debt (negative)
- Note stale data (snapshot >7 days old)
- Respect `include_in_net_worth` for totals

## Conversational
Yes - follow-ups:
- "What about pensions?"
- "Show change this month"
- "How much in ISAs?"
- "Update Marcus balance to £15,500"
