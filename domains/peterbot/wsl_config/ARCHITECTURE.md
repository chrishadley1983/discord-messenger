# Peterbot Architecture

## Message Flow (Channel Mode)

```
Discord message → peter-channel (discord.js) → MCP notification → Claude Code session → reply tool → Discord
```

Scheduled jobs:
```
APScheduler → scheduler.py → POST /job to jobs-channel → Claude processes skill → reply tool → scheduler receives response → POST /post to peter-channel HTTP :8104 → Discord
```

## Channel Sessions

Three persistent Claude Code sessions run in WSL tmux:
- **peter-channel** — Discord conversations (discord.js gateway + reply tool + HTTP :8104)
- **whatsapp-channel** — WhatsApp conversations (HTTP :8102, via Evolution API)
- **jobs-channel** — Scheduled jobs (HTTP :8103, synchronous reply pattern)

Fallback: `PETERBOT_USE_CHANNEL=0` in `.env` reverts to router_v2 (`claude -p` per message).

## Memory System — Second Brain

See **MEMORY.md** for full details.

- **Injection**: Relevant memories prepended to your context before each message
- **Capture**: After you respond, the exchange is captured with facts/concepts extraction
- **Storage**: Supabase PostgreSQL + pgvector (semantic search via 384-dim gte-small embeddings)

## Scheduler System
- **SCHEDULE.md**: Defines cron/interval skill-based jobs
- **APScheduler**: Python scheduler in bot.py runs jobs at specified times
- **Quiet hours**: 23:00-06:00 UK — no scheduled jobs run
- **manifest.json**: Auto-generated listing all skills and triggers

**Infrastructure jobs** (registered in `bot.py`, NOT in SCHEDULE.md):
- `school_daily_sync` — Daily 7:03 AM: Gmail school email parser + Arbor scraper
- `school_weekly_sync` — Saturday 6:00 AM: term dates + newsletter + calendar sync
- `energy_daily_sync`, `whatsapp_sync`, `incremental_seed` — background jobs

## Reminder System
The Discord bot handles reminders separately from SCHEDULE.md.
- `/remind time:9am tomorrow task:check traffic` — Slash command
- Natural language: "Remind me at 9am to check traffic"

You do NOT manage reminders directly via slash commands — use the Reminders API instead (see GOVERNANCE.md).

## Your Channels
You respond in: #peterbot, #food-log, #ai-briefings, #api-balances, #traffic-reports, #news, #youtube
Each channel has its own conversation buffer (no cross-contamination).

## Voice Messages
See `WHATSAPP.md` for voice reply style rules and all WhatsApp behaviour.

## Your Capabilities
- Full Claude Code implementation capabilities
- Can create files, edit code, write scripts, build features
- Can modify skills, create documentation, implement solutions
- Can search, research, and synthesize information

## What Requires Chris
- **Bot core code** — bot.py, router_v2.py, scheduler.py
- **Deployments** — Pushing code, restarting services
- **Credentials** — API keys, secrets
