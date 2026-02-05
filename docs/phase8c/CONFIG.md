# Phase 8c Configuration

## Overview

All account balances (current, savings, ISA, SIPP, pensions) come from **Finance Tracker (Supabase)**.

Live crypto prices come from **CoinGecko** (free API).

## .env additions

```bash
# Finance Tracker (Supabase) - covers ALL accounts
FINANCE_TRACKER_URL=https://vkezoyhjoufvsjopjbrr.supabase.co
FINANCE_TRACKER_KEY=your_supabase_anon_key
```

## config.py additions

```python
# === PHASE 8c: Finance ===

# Finance Tracker (Supabase) - ALL account balances
FINANCE_TRACKER_URL = os.getenv("FINANCE_TRACKER_URL")
FINANCE_TRACKER_KEY = os.getenv("FINANCE_TRACKER_KEY")

# Crypto holdings for live price lookup via CoinGecko
CRYPTO_HOLDINGS = {
    "bitcoin": {"amount": 0.97573468},      # ~0.98 BTC
    "ethereum": {"amount": 6.08688041},     # ~6.09 ETH
    "polkadot": {"amount": 130.76816858},   # ~131 DOT
}
```

## Data Sources

| Data | Source | Notes |
|------|--------|-------|
| Current accounts | Finance Tracker | HSBC, Monzo, etc. |
| Savings | Finance Tracker | Marcus, etc. |
| ISA balances | Finance Tracker | Vanguard LS funds |
| SIPP balances | Finance Tracker | Vanguard pension |
| Old pension | Finance Tracker | Workplace pension |
| Credit cards | Finance Tracker | Shown as negative |
| Transactions | Finance Tracker | For spending/budget |
| **Crypto (live)** | CoinGecko | BTC, ETH, DOT prices |

## Skills → Data Source

| Skill | Source |
|-------|--------|
| `spending-summary` | Finance Tracker |
| `budget-check` | Finance Tracker |
| `account-balances` | Finance Tracker |
| `net-worth` | Finance Tracker |
| `crypto-check` | CoinGecko |

## API Notes

### Finance Tracker (Supabase)
- **Auth:** Supabase anon key
- **Tables:** `accounts`, `wealth_snapshots`, `transactions`, `categories`, `budgets`
- **Updates:** Via Finance Tracker app

### CoinGecko (Crypto)
- **Free:** No API key required
- **Rate limit:** 10-30 calls/min
- **Endpoint:** `https://api.coingecko.com/api/v3/simple/price`
