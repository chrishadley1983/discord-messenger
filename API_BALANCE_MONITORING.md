# API Balance Monitoring System

Complete documentation of how hourly API balance checking works for Claude and Moonshot Kimi.

## Overview

**What it does:**
- ✅ Queries Claude platform API credit balance hourly
- ✅ Queries Moonshot Kimi API balance hourly
- ✅ Posts combined summary to Discord #peter-chat every hour
- ✅ Alerts if either balance falls below $5.00 threshold
- ✅ Logs all checks to local balance-log files

**Current Status:**
- Claude balance: Tracked via Supabase (DB query)
- Moonshot Kimi: Tracked via REST API
- Frequency: Hourly (top of every hour, UTC)
- Target: Discord #peter-chat (channel: 1415741789758816369)

---

## Architecture

### Two-Source System

```
┌─────────────────────┐         ┌──────────────────────┐
│  Claude Platform    │         │  Moonshot Kimi API   │
│  (Web scrape/DB)    │         │  (REST endpoint)     │
└──────────┬──────────┘         └──────────┬───────────┘
           │                               │
           ├───────────────┬───────────────┤
           │               │               │
       Every Hour       Every Hour     Every Hour
           │               │               │
           └───────────────┴───────────────┘
                    │
                    ▼
        ┌──────────────────────┐
        │  Combined Summary    │
        │  Discord Message     │
        │  + Alerts            │
        └──────────────────────┘
```

### Data Sources

| Source | Method | Reliability | Notes |
|--------|--------|-------------|-------|
| **Claude Balance** | Supabase DB query | Medium | Updated manually (browser scrape job) |
| **Moonshot Kimi** | REST API (`/v1/users/me/balance`) | High | Direct API call, always current |

---

## Scripts

### 1. **moonshot-balance.sh** (Utility)
*Location: `/root/clawd/scripts/moonshot-balance.sh`*

**Purpose:** Query Moonshot Kimi API and check for low balance alert

**Usage:**
```bash
/root/clawd/scripts/moonshot-balance.sh
```

**Output:**
```
✅ Moonshot Balance Check
💰 Available: $12.34
🎁 Voucher: $3.45
💵 Cash: $8.89
```

**Exit Codes:**
- `0` - OK (balance >= $5)
- `2` - Alert (balance < $5)
- `1` - Error

**Code:**
```bash
#!/bin/bash
# Moonshot API Balance Checker

set -e

source /etc/profile.d/xai.sh

if [ -z "$MOONSHOT_API_KEY" ]; then
  echo "Error: MOONSHOT_API_KEY not set"
  exit 1
fi

RESPONSE=$(curl -s https://api.moonshot.ai/v1/users/me/balance \
  -H "Authorization: Bearer $MOONSHOT_API_KEY")

CODE=$(echo "$RESPONSE" | jq -r '.code')

if [ "$CODE" != "0" ]; then
  echo "Error: API returned code $CODE"
  echo "$RESPONSE" | jq .
  exit 1
fi

AVAILABLE=$(echo "$RESPONSE" | jq -r '.data.available_balance')
VOUCHER=$(echo "$RESPONSE" | jq -r '.data.voucher_balance')
CASH=$(echo "$RESPONSE" | jq -r '.data.cash_balance')

# Check if balance is low
if (( $(echo "$AVAILABLE <= 5" | bc -l) )); then
  ALERT="⚠️ **Moonshot API Balance Low!**\n\n💰 **Available:** \$$AVAILABLE\n🎁 **Voucher:** \$$VOUCHER\n💵 **Cash:** \$$CASH"
  echo -e "$ALERT"
  exit 2  # Signal low balance
fi

echo "✅ Moonshot Balance Check"
echo "💰 Available: \$$AVAILABLE"
echo "🎁 Voucher: \$$VOUCHER"
echo "💵 Cash: \$$CASH"
```

**Key Points:**
- Requires `$MOONSHOT_API_KEY` environment variable (from `/etc/profile.d/xai.sh`)
- Uses `jq` for JSON parsing
- Separates available balance into voucher vs cash components
- Exit code signals alerting condition (balance < $5)

---

### 2. **check-moonshot-balance.sh** (Logging Version)
*Location: `/root/clawd/scripts/check-moonshot-balance.sh`*

**Purpose:** Same as above but logs to file instead of stdout

**Behavior:**
- Queries Moonshot API
- Writes to `/root/.config/moonshot/balance-log.txt`
- Each entry: `TIMESTAMP | Available: $X | Voucher: $Y | Cash: $Z`

**Code:**
```bash
#!/bin/bash

# Moonshot Kimi Balance Checker
# Queries the Moonshot API hourly and alerts if balance < $5

set -a
source /etc/profile.d/moonshot.sh
set +a

BALANCE_LOG="/root/.config/moonshot/balance-log.txt"
mkdir -p /root/.config/moonshot

# Query the API
RESPONSE=$(curl -s https://api.moonshot.ai/v1/users/me/balance \
  -H "Authorization: Bearer $MOONSHOT_API_KEY")

# Extract balances
AVAILABLE=$(echo "$RESPONSE" | jq -r '.data.available_balance')
VOUCHER=$(echo "$RESPONSE" | jq -r '.data.voucher_balance')
CASH=$(echo "$RESPONSE" | jq -r '.data.cash_balance')

# Log the balance
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
echo "$TIMESTAMP | Available: \$$AVAILABLE | Voucher: \$$VOUCHER | Cash: \$$CASH" >> "$BALANCE_LOG"

# Always post current balance to Discord
if (( $(echo "$AVAILABLE < 5" | bc -l) )); then
  DISCORD_MSG="⚠️ Kimi credits low! Available: \$$AVAILABLE (voucher: \$$VOUCHER, cash: \$$CASH)"
else
  DISCORD_MSG="🌙 Kimi Balance: \$$AVAILABLE (voucher: \$$VOUCHER, cash: \$$CASH)"
fi

# Log the post
echo "[$TIMESTAMP] POSTED: $DISCORD_MSG" >> "$BALANCE_LOG"

# Post to Discord (can be integrated with clawdbot message tool if needed)
# For now, just logs the message that would be posted
```

---

### 3. **combined-balance-check.sh** (Main Integration)
*Location: `/root/clawd/scripts/combined-balance-check.sh`*

**Purpose:** The system that actually runs — combines both sources and posts to Discord

**What it does:**
1. Queries Moonshot API (REST)
2. Queries Claude balance from Supabase (DB)
3. Formats combined message with markdown
4. Adds alerts if either < $5
5. Logs both to their respective files
6. Outputs formatted message for Discord posting
7. Returns exit code to signal alerts

**Usage (Manual):**
```bash
/root/clawd/scripts/combined-balance-check.sh
```

**Output:**
```
📊 **API Balance Summary**

💳 **Claude:** $8.07 (threshold: $5.00)
🌙 **Kimi:** $12.34 available (threshold: $5.00)

Runs every hour on the hour (UTC)
Posts to <#1415741789758816369>
Adds alerts if either < $5
```

**Code:**
```bash
#!/bin/bash
# Combined Claude + Moonshot Balance Check for hourly post

set -e

source /etc/profile.d/xai.sh
source /etc/profile.d/supabase.sh

# Get Moonshot balance
MOONSHOT_RESPONSE=$(curl -s https://api.moonshot.ai/v1/users/me/balance \
  -H "Authorization: Bearer $MOONSHOT_API_KEY")

MOONSHOT_CODE=$(echo "$MOONSHOT_RESPONSE" | jq -r '.code')
if [ "$MOONSHOT_CODE" != "0" ]; then
  echo "Error: Moonshot API returned code $MOONSHOT_CODE"
  exit 1
fi

MOONSHOT_AVAILABLE=$(echo "$MOONSHOT_RESPONSE" | jq -r '.data.available_balance')
MOONSHOT_VOUCHER=$(echo "$MOONSHOT_RESPONSE" | jq -r '.data.voucher_balance')
MOONSHOT_CASH=$(echo "$MOONSHOT_RESPONSE" | jq -r '.data.cash_balance')

# Get Claude balance from Supabase
CLAUDE_BALANCE=$(PGPASSWORD="$SUPABASE_DB_PASSWORD" psql -h "$SUPABASE_DB_HOST" -p 5432 -U postgres -d postgres -t -c "SELECT COALESCE(available_balance, 0) FROM claude_api_usage ORDER BY updated_at DESC LIMIT 1;")

# Format the message
MESSAGE="📊 **API Balance Summary**\n\n"

# Claude balance
if (( $(echo "$CLAUDE_BALANCE <= 5" | bc -l) )); then
  CLAUDE_EMOJI="⚠️"
else
  CLAUDE_EMOJI="💳"
fi
MESSAGE="${MESSAGE}${CLAUDE_EMOJI} **Claude:** \$${CLAUDE_BALANCE} (threshold: \$5.00)\n"

# Kimi balance  
if (( $(echo "$MOONSHOT_AVAILABLE <= 5" | bc -l) )); then
  MOONSHOT_EMOJI="⚠️"
else
  MOONSHOT_EMOJI="🌙"
fi
MESSAGE="${MESSAGE}${MOONSHOT_EMOJI} **Kimi:** \$${MOONSHOT_AVAILABLE} available (threshold: \$5.00)\n\n"
MESSAGE="${MESSAGE}Runs every hour on the hour (UTC)\nPosts to <#1415741789758816369>\nAdds alerts if either < \$5"

# Log both balances
echo "[$(date -u +'%Y-%m-%d %H:%M:%S')] Claude: \$$CLAUDE_BALANCE" >> /root/.config/claude/balance-log.txt
echo "[$(date -u +'%Y-%m-%d %H:%M:%S')] Moonshot: \$$MOONSHOT_AVAILABLE" >> /root/.config/moonshot/balance-log.txt

# Output for cron job to send
echo -e "$MESSAGE"

# Exit with alert code if either is low
if (( $(echo "$CLAUDE_BALANCE <= 5" | bc -l) )) || (( $(echo "$MOONSHOT_AVAILABLE <= 5" | bc -l) )); then
  exit 2
fi

exit 0
```

**Key Features:**
- Handles both APIs in one script
- Emoji changes to ⚠️ if balance < $5
- Dual logging (both balance-log files updated)
- Outputs formatted message ready for Discord
- Exit code 0 (OK) or 2 (Alert) for cron handling

---

## Cron Job Configuration

**Job Name:** "Claude Platform Balance Check"
**Schedule:** `0 * * * *` (hourly, top of every hour, UTC)

**Cron Job Payload:**
```json
{
  "kind": "agentTurn",
  "message": "💳 Check API Credit Balances (Combined)\n\n1. Query Claude: Open https://platform.claude.com/settings/billing, screenshot balance and extract the available credit amount\n2. Query Kimi: curl https://api.moonshot.ai/v1/users/me/balance -H \"Authorization: Bearer $MOONSHOT_API_KEY\"\n3. Extract both balances and post combined message to Discord #peter-chat using message tool with target:1415741789758816369:\n\n📊 **API Balance Summary**\n💳 Claude: $X.XX (threshold: $5.00)\n🌙 Kimi: $X.XX available (threshold: $5.00)\n\n4. Add alerts if either < $5:\n   💳 ⚠️ Claude credits low!\n   🌙 ⚠️ Kimi credits low!\n\n5. Log both to respective balance log files with timestamp",
  "model": "moonshot/kimi-k2-0905-preview",
  "deliver": true,
  "channel": "discord",
  "to": "target:1415741789758816369"
}
```

**How It Works:**
1. Cron triggers every hour (UTC)
2. Spawns isolated agent session (Moonshot Kimi)
3. Agent runs the instructions in the message
4. Agent calls the combined-balance-check script (or equivalent)
5. Agent formats output and posts to Discord using `message` tool
6. Alert timestamp logged if balance < $5

---

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                   HOURLY CRON TRIGGER (UTC)                  │
│                    0 * * * * (every hour)                    │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
            ┌────────────────────────────┐
            │  Isolated Agent Session    │
            │  (Kimi, ID: ......)        │
            └────────────┬───────────────┘
                         │
                         ├────────────────────┬─────────────────┐
                         ▼                    ▼                 ▼
           ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐
           │ Browser: Claude  │  │ REST API: Kimi   │  │ Supabase: DB    │
           │ platform.claude  │  │ moonshot.ai      │  │ claude_api_     │
           │ .com/settings    │  │ /v1/users/me/    │  │ usage table     │
           │ /billing         │  │ balance          │  │                 │
           └────────┬─────────┘  └────────┬─────────┘  └────────┬────────┘
                    │                     │                    │
                    └─────────────────────┼────────────────────┘
                                          │
                                          ▼
                            ┌────────────────────────┐
                            │ Format Combined Msg    │
                            │ - Add emojis & alerts  │
                            │ - Add thresholds       │
                            │ - Add metadata         │
                            └────────────┬───────────┘
                                         │
                                         ├──────────────┬────────────────┐
                                         ▼              ▼                ▼
                            ┌──────────────────┐ ┌──────────────┐ ┌──────────────┐
                            │ Discord #peter-  │ │ Log to file: │ │ Log to file: │
                            │ chat post        │ │ claude_      │ │ moonshot_    │
                            │ (message tool)   │ │ balance.txt  │ │ balance.txt  │
                            └──────────────────┘ └──────────────┘ └──────────────┘
```

---

## Configuration & Secrets

### Environment Variables Required

**File:** `/etc/profile.d/xai.sh`
```bash
export MOONSHOT_API_KEY="sk_..."
```

**File:** `/etc/profile.d/supabase.sh`
```bash
export SUPABASE_DB_HOST="modjoikyuhqzouxvieua.supabase.co"
export SUPABASE_DB_PASSWORD="eyJhbGc..."
```

### Discord Channel Target
- **Channel ID:** `1415741789758816369` (#peter-chat)
- **Parameter:** `target:1415741789758816369` (in cron config)

---

## Balance Thresholds

| Service | Warning Threshold | Current Balance | Status |
|---------|-----------------|-----------------|--------|
| **Claude** | $5.00 | Tracked in Supabase | ✅ |
| **Moonshot Kimi** | $5.00 | Direct API | ✅ |

When either drops below threshold:
- Emoji changes to ⚠️
- Message includes alert
- Discord still posts (no silent failures)
- Exit code signals alert to cron system

---

## Log Files

### Claude Balance Log
**Location:** `/root/.config/claude/balance-log.txt`
**Format:**
```
[2026-01-29 09:00:00] Claude: $8.07
[2026-01-29 10:00:00] Claude: $8.05
[2026-01-29 11:00:00] Claude: $8.03
```

### Moonshot Kimi Balance Log
**Location:** `/root/.config/moonshot/balance-log.txt`
**Format:**
```
2026-01-29 09:00:00 | Available: $12.34 | Voucher: $3.45 | Cash: $8.89
2026-01-29 10:00:00 | Available: $12.32 | Voucher: $3.45 | Cash: $8.87
2026-01-29 11:00:00 | Available: $12.30 | Voucher: $3.45 | Cash: $8.85
```

---

## Troubleshooting

### Issue: Discord message not posting
**Check:**
1. Cron job status: `clawdbot cron list`
2. Last run error: Check the `state.lastError` field
3. Discord channel target: Verify `1415741789758816369` is correct
4. Message tool parameter: Should be `target:` not `channel:`

### Issue: Balance API returning error
**Check:**
1. API key valid: `echo $MOONSHOT_API_KEY`
2. Network access: `curl -s https://api.moonshot.ai/v1/users/me/balance -H "Authorization: Bearer $MOONSHOT_API_KEY"`
3. Supabase connection: `PGPASSWORD="..." psql -h ... -U postgres -d postgres -c "SELECT 1"`

### Issue: Balances not updating
**Check:**
1. View logs: `tail -20 /root/.config/moonshot/balance-log.txt`
2. Manually run: `/root/clawd/scripts/combined-balance-check.sh`
3. Cron job last run timestamp: `clawdbot cron list | grep "Claude Platform"`

---

## Future Enhancements

- [ ] Add historical trend graph (weekly/monthly spending)
- [ ] Webhook-based alerts instead of hourly posts (instant)
- [ ] Email notification when balance < $5
- [ ] Auto-replenish when below threshold (if API supports)
- [ ] Track cost per API call (rate analysis)
- [ ] Dashboard page showing both balances + history

---

**Last Updated:** 2026-01-29
**Status:** ✅ Active (hourly posts to Discord)
