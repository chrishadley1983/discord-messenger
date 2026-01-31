# Cron Jobs & Discord Notifications Reference

> **Last Updated:** 2026-01-29
> **Scope:** Discord-Messenger bot + Hadley Bricks inventory system

---

## Discord-Messenger Bot Jobs

### Standalone Scheduled Jobs

| # | Job | Schedule | Channel | Description |
|---|-----|----------|---------|-------------|
| 1 | **Balance Monitor** | Hourly 7am-9pm UK | #api-balances | Monitors Claude & Moonshot Kimi API credit balances; alerts if <$5 |
| 2 | **Hydration Check-in** | 9am,11am,1pm,3pm,5pm,7pm,9pm UK | #food-log | Posts water intake & step progress with Haiku motivation |
| 3 | **AI Morning Briefing** | 6:30am UTC | #ai-briefings | Two-stage AI briefing: Grok for search, Sonnet for curation (AI news, Claude Code tips) |
| 4 | **Withings Sync** | 7:55am UK | (none) | Syncs latest weight from Withings API to database before morning digest |
| 5 | **Morning Health Digest** | 8:00am UK | #food-log | Weight trend, sleep, HR, steps, yesterday's nutrition, days to Japan goal |
| 6 | **School Run (Morning)** | 8:10am Mon-Wed,Fri / 7:45am Thu UK | #traffic-reports + WhatsApp | Traffic, weather, uniform, morning activities |
| 7 | **School Pickup (Afternoon)** | 2:55pm Mon,Tue,Thu,Fri / 4:50pm Wed UK | #traffic-reports + WhatsApp | Traffic to school, evening clubs for Max & Emmie |
| 8 | **Weekly Health Summary** | Sunday 9:00am UK | #food-log | PT grade, weight/nutrition/steps/sleep/HR trends, matplotlib graphs |
| 9 | **Monthly Health Summary** | 1st of month 9:00am UK | #food-log | Month-over-month comparison, progress to 80kg goal, 30-day graphs |

### Domain-Based Schedules

| # | Job | Schedule | Channel | Description |
|---|-----|----------|---------|-------------|
| 10 | **Daily Nutrition Summary** | 9:00pm UK | #food-log | Daily totals with emoji status (calories, protein, carbs, fat, water, steps) |
| 11 | **Morning News Briefing** | 7:00am UK | #news | Tech, UK, and F1 headlines from RSS feeds (3 tech, 2 UK, 2 F1) |
| 12 | **Weekly API Usage** | Monday 9:00am UK | #api-usage | Weekly cost summary for Claude (Anthropic) and OpenAI APIs |

### Manual Discord Commands

| Command | Triggers Job |
|---------|--------------|
| `!balance` | Balance Monitor |
| `!hydration` | Hydration Check-in |
| `!briefing` | AI Morning Briefing |
| `!morning` | Morning Health Digest |
| `!schoolrun` | School Run (Morning) |
| `!schoolpickup` | School Pickup (Afternoon) |
| `!weeklyhealth` | Weekly Health Summary |
| `!monthlyhealth` | Monthly Health Summary |

---

## Hadley Bricks Cron Jobs

> **All Hadley Bricks cron jobs are triggered via Google Cloud Scheduler** (project: `gen-lang-client-0823893317`, region: `europe-west2`).
> Vercel crons require Pro/Enterprise plan, so we use GCS to call the Vercel endpoints directly.

### Google Cloud Scheduler Jobs

| # | GCS Job Name | Schedule | Endpoint | Discord Channel | Description |
|---|--------------|----------|----------|-----------------|-------------|
| 1 | `full-sync` | `45 7,13 * * *` (7:45am & 1:45pm UTC) | `/api/cron/full-sync` | #sync-status | Master sync: eBay/Amazon/BrickLink/BrickOwl orders, stuck job detection, weekly stats |
| 2 | `amazon-two-phase-sync` | `*/5 * * * *` (every 5 min) | `/api/cron/amazon-sync` | #sync-status, #alerts | Processes two-phase Amazon sync feeds (price verification, quantity submit) |
| 3 | `amazon-pricing-sync` | `0 4 * * *` (4:00am UTC) | `/api/cron/amazon-pricing` | #sync-status | Daily Amazon pricing sync for tracked ASINs (resumable, cursor-based) |
| 4 | `ebay-pricing-sync` | `0 2 * * *` (2:00am UTC) | `/api/cron/ebay-pricing` | #sync-status | Daily eBay pricing sync from watchlist (1000/day limit, resumable) |
| 5 | `bricklink-pricing-sync` | `30 2 * * *` (2:30am UTC) | `/api/cron/bricklink-pricing` | #sync-status | Daily BrickLink pricing sync from watchlist (1000/day limit, resumable) |
| 6 | `ebay-fp-cleanup` | `0 4 * * *` (4:00am UTC) | `/api/cron/ebay-fp-cleanup` | #sync-status, #alerts | False-positive detection (minifigs, keyrings, instructions) - 14 weighted signals |
| 7 | `ebay-negotiation-sync` | `0 8,12,16,20 * * *` (4x daily) | `/api/cron/negotiation` | #sync-status | Automated eBay offer sending for eligible listings |
| 8 | `vinted-cleanup` | `0 0 * * *` (midnight UTC) | `/api/cron/vinted-cleanup` | #daily-summary | Expire old opportunities, cleanup logs, send Vinted daily summary |
| 9 | `refresh-watchlist` | `0 3 * * 0` (Sundays 3:00am UTC) | `/api/cron/refresh-watchlist` | #sync-status | Weekly refresh of arbitrage_watchlist from inventory_items |

### Real-Time Notifications (Event-Driven)

| Event | Discord Channel | Description |
|-------|-----------------|-------------|
| Vinted opportunity found | #opportunities | Arbitrage opportunity with COG%, profit, Vinted link |
| CAPTCHA detected | #alerts | Scanner auto-paused, manual intervention needed |
| Consecutive scan failures | #alerts | X failures in a row, check scanner status |
| Amazon sync failure | #alerts | Two-phase sync failed (price verification, quantity rejection) |
| Amazon sync success | #sync-status | X items synced, price verified in Y time |

---

## Channel Reference (By Channel)

### Discord-Messenger Server

| Channel | Jobs That Post Here |
|---------|---------------------|
| **#food-log** | Hydration Check-in, Morning Health Digest, Daily Nutrition Summary, Weekly Health Summary, Monthly Health Summary |
| **#api-balances** | Balance Monitor |
| **#ai-briefings** | AI Morning Briefing |
| **#traffic-reports** | School Run (Morning), School Pickup (Afternoon) |
| **#news** | Morning News Briefing |
| **#api-usage** | Weekly API Usage |
| **#peter-chat** | (Interactive chat with Claude - not scheduled) |

### Hadley Bricks Server

| Channel | Jobs That Post Here |
|---------|---------------------|
| **#sync-status** | Full Sync, Amazon Sync, Amazon Pricing, eBay Pricing, BrickLink Pricing, eBay FP Cleanup, Negotiation, Amazon sync success |
| **#alerts** | Amazon Sync failures, eBay FP Cleanup failures, CAPTCHA warnings, Consecutive scan failures |
| **#opportunities** | Vinted arbitrage opportunities (COG <30% green, 30-40% yellow, >40% orange) |
| **#daily-summary** | Vinted Cleanup (daily scanner stats) |
| **#hb-app-health** | (Not currently used by cron jobs - available for future use) |

### WhatsApp Recipients

| Recipient | Jobs |
|-----------|------|
| Abby (+447856182831) | School Run (Morning), School Pickup (Afternoon) |
| Chris (+447855620978) | School Run (Morning), School Pickup (Afternoon) |

---

## Environment Variables Required

### Discord-Messenger (.env)

```bash
# Discord
DISCORD_TOKEN=                      # Bot token

# Supabase
SUPABASE_URL=                       # For health data
SUPABASE_KEY=                       # Service role key

# APIs
ANTHROPIC_API_KEY=                  # Claude (Haiku, Sonnet)
GROK_API_KEY=                       # xAI Grok for morning briefing
MOONSHOT_API_KEY=                   # Kimi balance monitoring
GOOGLE_MAPS_API_KEY=                # Traffic/directions

# WhatsApp
TWILIO_ACCOUNT_SID=                 # Twilio account
TWILIO_AUTH_TOKEN=                  # Twilio auth
TWILIO_WHATSAPP_FROM=               # Twilio sandbox number
```

### Hadley Bricks (.env.local)

```bash
# Discord Webhooks
DISCORD_WEBHOOK_ALERTS=             # #alerts channel
DISCORD_WEBHOOK_OPPORTUNITIES=      # #opportunities channel
DISCORD_WEBHOOK_SYNC_STATUS=        # #sync-status channel
DISCORD_WEBHOOK_DAILY_SUMMARY=      # #daily-summary channel

# Cron Auth
CRON_SECRET=                        # Bearer token for cron endpoints
```

---

## Daily Timeline (UK Time)

| Time | Job | System |
|------|-----|--------|
| 00:00 | Vinted Cleanup | Hadley Bricks |
| 02:00 | eBay Pricing Sync | Hadley Bricks |
| 02:30 | BrickLink Pricing Sync | Hadley Bricks |
| 04:00 | Amazon Pricing Sync | Hadley Bricks |
| 04:00 | eBay FP Cleanup | Hadley Bricks |
| 06:30 | AI Morning Briefing | Discord-Messenger |
| 07:00 | Morning News Briefing | Discord-Messenger |
| 07:45 (Thu) | School Run Report | Discord-Messenger |
| 07:55 | Withings Sync | Discord-Messenger |
| 08:00 | Morning Health Digest | Discord-Messenger |
| 08:10 | School Run Report (Mon-Wed,Fri) | Discord-Messenger |
| 08:00 | Negotiation Run 1 | Hadley Bricks |
| 08:45 | Full Sync Run 1 | Hadley Bricks |
| 09:00 | Hydration Check-in | Discord-Messenger |
| 11:00 | Hydration Check-in | Discord-Messenger |
| 12:00 | Negotiation Run 2 | Hadley Bricks |
| 13:00 | Hydration Check-in | Discord-Messenger |
| 14:45 | Full Sync Run 2 | Hadley Bricks |
| 14:55 | School Pickup Report (Mon,Tue,Thu,Fri) | Discord-Messenger |
| 15:00 | Hydration Check-in | Discord-Messenger |
| 16:00 | Negotiation Run 3 | Hadley Bricks |
| 16:50 | School Pickup Report (Wed) | Discord-Messenger |
| 17:00 | Hydration Check-in | Discord-Messenger |
| 19:00 | Hydration Check-in | Discord-Messenger |
| 20:00 | Negotiation Run 4 | Hadley Bricks |
| 21:00 | Hydration Check-in | Discord-Messenger |
| 21:00 | Daily Nutrition Summary | Discord-Messenger |
| Hourly 7am-9pm | Balance Monitor | Discord-Messenger |
| Every 1-2 min | Amazon Sync (business hours) | Hadley Bricks |

### Weekly Events

| Day | Time | Job |
|-----|------|-----|
| Sunday | 9:00am UK | Weekly Health Summary |
| Monday | 9:00am UK | Weekly API Usage |

### Monthly Events

| Day | Time | Job |
|-----|------|-----|
| 1st | 9:00am UK | Monthly Health Summary |

---

---

## Auto-Startup Configuration

### Discord-Messenger Bot (Windows)

The bot is configured to auto-start on Windows login:

| File | Purpose |
|------|---------|
| `start-bot.bat` | Main startup script (activates venv, runs bot.py) |
| `start-bot-hidden.vbs` | VBS wrapper to run silently (no console window) |
| `Startup\Discord-Messenger-Bot.lnk` | Shortcut in Windows Startup folder |

**Startup folder location:**
```
C:\Users\Chris Hadley\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\
```

**Manual start:**
```batch
cd "C:\Users\Chris Hadley\Discord-Messenger"
python bot.py
```

**Check if running:**
```batch
tasklist | findstr python
```

**Stop the bot:**
```batch
taskkill /f /im python.exe
```

### Hadley Bricks (Vercel)

Cron jobs are managed by Vercel. See `vercel.json` for configured schedules.

---

## TODO

- [ ] **Reverse audit**: Verify each Discord channel actually receives the messages documented above
- [ ] Verify all Hadley Bricks cron jobs are properly scheduled (currently only full-sync is in vercel.json)
- [ ] Consider adding #hb-app-health for Hadley Bricks health monitoring
- [ ] Document Vinted scanner real-time notifications more thoroughly
