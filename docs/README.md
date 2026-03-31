# Discord Messenger — Project Documentation

> Peter is an AI personal assistant running as a Discord bot, built by Chris Hadley. He manages schedules, health tracking, LEGO business automation, family coordination, and more — across Discord, WhatsApp, and voice.

## System Documentation

These docs provide a comprehensive reference for the entire project. Start with Architecture for the big picture, then dive into specific subsystems.

### Core Architecture

| Document | Description |
|----------|-------------|
| [Architecture](./ARCHITECTURE.md) | System overview, component diagram, message flows, symlink strategy, architecture decisions |
| [Core Bot](./CORE_BOT.md) | bot.py, router_v2, scheduler, response pipeline, memory system, data fetchers |
| [Channels](./CHANNELS.md) | peter-channel (Discord), whatsapp-channel, jobs-channel — MCP channel protocol, fallback, lifecycle |

### Feature References

| Document | Description |
|----------|-------------|
| [Skills Reference](./SKILLS_REFERENCE.md) | All 106 skills organized by category with triggers, schedules, channels, data sources |
| [Scheduled Jobs](./SCHEDULED_JOBS.md) | Complete daily timeline, schedule syntax, data fetchers, job execution flow, channel map |
| [Hadley API Reference](./HADLEY_API_REFERENCE.md) | 316+ REST endpoints across 16 modules (Gmail, Calendar, Drive, Spotify, Nutrition, etc.) |

### Subsystems

| Document | Description |
|----------|-------------|
| [Second Brain](./SECOND_BRAIN.md) | Knowledge base — pipeline, embeddings, capture, search, 20 seed adapters, MCP server |
| [Domains & Integrations](./DOMAINS.md) | All 6 domains (Peterbot, Nutrition, News, API Usage, Claude Code, Second Brain) + external services |
| [Peter Dashboard](./PETER_DASHBOARD.md) | Monitoring UI — service health, job history, log viewing, alerts |
| [Peter Voice](./PETER_VOICE.md) | Desktop voice client — STT (Moonshine), TTS (Kokoro), hotkeys, wake word |

### Historical / Planning Docs

| Document | Description |
|----------|-------------|
| [Memory Architecture](./MEMORY-ARCHITECTURE.md) | Second Brain memory system design |
| [Response Pipeline](./RESPONSE.md) | Detailed response pipeline spec |
| [Phase 7 Summary](./PHASE7_SUMMARY.md) | Proactive self-improvement phase |
| [Phase 9 Browser](./phase9-browser-purchasing.md) | Browser purchasing automation |
| [Cron Jobs (Legacy)](./CRON_JOBS_REFERENCE.md) | Legacy cron job reference (superseded by SCHEDULED_JOBS.md) |

---

## Quick Reference

### Services

| Service | Port | Platform | Status |
|---------|------|----------|--------|
| Discord Bot (bot.py) | — | Windows (NSSM) | Active |
| Hadley API | 8100 | Windows (NSSM) | Active |
| Peter Dashboard | 5000 | Windows (NSSM) | Active |
| peter-channel | — | WSL (tmux) | Active |
| whatsapp-channel | 8102 | WSL (tmux) | Active |
| jobs-channel | 8103 | WSL (tmux) | Active |
| Peter Voice | — | Windows (tray) | Active |

### Key Paths

| Path | Purpose |
|------|---------|
| `bot.py` | Main Discord bot entry point |
| `domains/peterbot/router_v2.py` | Active message router |
| `domains/peterbot/scheduler.py` | Job scheduler |
| `domains/peterbot/wsl_config/` | Symlinked to ~/peterbot in WSL |
| `domains/peterbot/wsl_config/CLAUDE.md` | Peter's instructions |
| `domains/peterbot/wsl_config/SCHEDULE.md` | Job schedule definitions |
| `domains/peterbot/wsl_config/skills/` | 106 skill definitions |
| `hadley_api/main.py` | FastAPI REST API (316+ endpoints) |
| `peter_dashboard/app.py` | Monitoring dashboard |
| `mcp_servers/` | MCP servers (Second Brain, Financial Data) |

### Key Stats

- **106 skills** across 11 categories
- **50+ scheduled jobs** running daily
- **316+ API endpoints** in Hadley API
- **3 communication channels** (Discord, WhatsApp, Scheduled Jobs)
- **2 MCP servers** (Second Brain, Financial Data)
- **3 AI providers** (Claude primary, Claude secondary, Kimi fallback)
- **2,943+ knowledge items** in Second Brain

---

*Generated: 2026-03-27*
*Documentation Agent v1.0*
