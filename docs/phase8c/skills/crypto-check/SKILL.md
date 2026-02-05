# Crypto Check

## Purpose
Check cryptocurrency prices and portfolio value.

## Triggers
- "crypto", "bitcoin", "ethereum"
- "crypto portfolio", "how are my coins"
- "what's {coin} at"
- "BTC price", "ETH price"

## Schedule
None (conversational only - crypto is 24/7)

## Data Source
CoinGecko API (free)
- Endpoint: `https://api.coingecko.com/api/v3/simple/price`
- No API key required (rate limited)
- Docs: https://www.coingecko.com/en/api

## Holdings Configuration
Store in memory or config:
```python
CRYPTO_HOLDINGS = {
    "bitcoin": {"amount": 0.97573468, "cost_basis": 0},      # ~£60k
    "ethereum": {"amount": 6.08688041, "cost_basis": 0},     # ~£11.5k
    "polkadot": {"amount": 130.76816858, "cost_basis": 0},   # ~£156
}
# Total: ~£72k
```

## Pre-fetcher
`get_crypto_data()` - fetches:
- Current prices (in GBP)
- 24h change (%)
- 7d change (%)
- Portfolio value
- Gain/loss vs cost basis

## API Call
```
GET https://api.coingecko.com/api/v3/simple/price
  ?ids=bitcoin,ethereum
  &vs_currencies=gbp
  &include_24hr_change=true
  &include_7d_change=true
```

## Output Format

**Portfolio Summary:**
```
🪙 **Crypto Portfolio**

**Total Value: £72,156** 

**Holdings:**
• Bitcoin (BTC)
  0.9757 BTC @ £61,200 = £59,713
  24h: +2.3% | 7d: +8.5%

• Ethereum (ETH)
  6.0869 ETH @ £1,890 = £11,504
  24h: -0.8% | 7d: +3.2%

• Polkadot (DOT)
  130.77 DOT @ £1.19 = £156
  24h: +1.5% | 7d: -2.1%

**Market:**
• BTC Dominance: 52.4%
• Total Crypto Market: $1.8T
```

**Single Coin Query:**
```
🪙 **Bitcoin (BTC)**

Price: £61,200
24h Change: +£1,420 (+2.3%)
7d Change: +£4,890 (+8.5%)

You own: 0.9757 BTC (£59,713)
```

## Guidelines
- Always show GBP values
- Include 24h and 7d change for volatility context
- Note if prices are from cache (CoinGecko rate limits)
- Don't give trading advice
- Warn about volatility if asked about buying

## Conversational
Yes - follow-ups:
- "Just Bitcoin"
- "What about Solana?" (even if not held)
- "Add 0.5 ETH at £2000"
- "What's the crypto market doing?"
- "Convert my BTC value to USD"

## Supported Coins (CoinGecko IDs)
- `bitcoin` - BTC ✅ (held)
- `ethereum` - ETH ✅ (held)
- `polkadot` - DOT ✅ (held)
- `solana` - SOL
- `cardano` - ADA
- `ripple` - XRP
- `dogecoin` - DOGE
- Full list: https://api.coingecko.com/api/v3/coins/list

## Notes
- CoinGecko free tier: 10-30 calls/min
- Cache prices for 5 mins to avoid rate limits
- Holdings stored in Peter's memory
- Can query any coin, not just held ones
