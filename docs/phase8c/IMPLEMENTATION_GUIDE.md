# Phase 8c Implementation Guide

## Overview

Phase 8c adds Finance integrations: spending tracking, budgets, account balances, net worth, stocks, and crypto.

**Skills Added:** 6 new skills
**APIs:** Supabase (Finance Tracker), Yahoo Finance (free), CoinGecko (free)
**Scheduled Jobs:** 2-3 new entries

---

## Skills Summary

| Skill | Type | Data Source | Cost |
|-------|------|-------------|------|
| `spending-summary` | Scheduled + Conv | Finance Tracker | FREE |
| `budget-check` | Scheduled + Conv | Finance Tracker | FREE |
| `account-balances` | Conversational | Finance Tracker | FREE |
| `net-worth` | Scheduled + Conv | Finance Tracker | FREE |
| `crypto-check` | Conversational | CoinGecko | FREE |

**Note:** All account balances (current, savings, ISA, SIPP, pensions) come from Finance Tracker. No external stock APIs needed.

---

## Setup Steps

### Step 1: Finance Tracker Connection

Add to `.env`:
```bash
FINANCE_TRACKER_URL=https://your-project.supabase.co
FINANCE_TRACKER_KEY=your_supabase_anon_key
```

This should be your existing Finance Tracker Supabase project.

### Step 2: Copy Skills

Copy skill files to:
```
skills/
├── spending-summary/SKILL.md
├── budget-check/SKILL.md
├── account-balances/SKILL.md
├── net-worth/SKILL.md
├── crypto-check/SKILL.md
```

### Step 3: Add Data Fetchers

Add the functions from `DATA_FETCHERS.md` to `data_fetchers.py`.

### Step 4: Crypto Holdings

For live crypto prices, configure holdings in `config.py`:

```python
CRYPTO_HOLDINGS = {
    "bitcoin": {"amount": 0.97573468},
    "ethereum": {"amount": 6.08688041},
    "polkadot": {"amount": 130.76816858},
}
```

Or tell Peter conversationally - he'll remember them.

### Step 5: Update CLAUDE.md

Add the guidance from `CLAUDE_MD_ADDITIONS.md`.

### Step 6: Schedule Entries

```markdown
| Job Name | Skill | Schedule | Channel | Needs Data |
|----------|-------|----------|---------|------------|
| Monthly Spending | spending-summary | 09:00 1st | #general | yes |
| Weekly Budget | budget-check | 09:00 Mon | #general | yes |
| Monthly Net Worth | net-worth | 09:00 1st | #general | yes |
```

---

## Testing

```bash
# Test Finance Tracker connection
!skill spending-summary
!skill budget-check
!skill account-balances
!skill net-worth

# Test live crypto prices
!skill crypto-check
```

Conversational tests:
- "How much have I spent this month?"
- "Am I on budget?"
- "What's my net worth?"
- "How are my investments?" (uses account-balances)
- "What's Bitcoin at?" (uses crypto-check)

---

## Database Requirements

Your Finance Tracker needs these tables (from schema):
- ✅ `accounts` - Financial accounts
- ✅ `transactions` - Transaction records
- ✅ `categories` - Transaction categories
- ✅ `budgets` - Monthly budget targets
- ✅ `wealth_snapshots` - Balance snapshots
- ✅ `fire_parameters` - FIRE calculation settings

If any are missing, Peter will gracefully handle with "not configured" messages.

---

## Data Flow

```
User: "How's my spending?"
    ↓
Peter matches → spending-summary skill
    ↓
Data fetcher queries Supabase
    ↓
Returns: {total, by_category, by_group}
    ↓
Peter formats response
```

For stocks/crypto:
```
User: "How are my investments?"
    ↓
Peter matches → stock-check + crypto-check
    ↓
Data fetchers query Yahoo Finance + CoinGecko
    ↓
Holdings from config/memory × prices
    ↓
Peter formats portfolio summary
```

---

## Notes

### Supabase RLS
Ensure Row Level Security allows reads with the anon key, or use a service role key.

### CoinGecko
- Free tier: 10-30 calls/min
- Use coin IDs not symbols (e.g., `bitcoin` not `BTC`)
- Cache responses to avoid rate limits

### Privacy
Finance data is sensitive. Peter should:
- Not volunteer detailed finance info unprompted
- Keep scheduled summaries high-level
- Only share specifics when directly asked
