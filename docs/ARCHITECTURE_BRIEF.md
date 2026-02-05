# Discord-Messenger System Architecture Brief

**Purpose**: This document provides comprehensive details about the Discord-Messenger system architecture. Use this to generate detailed architecture documentation.

---

## System Overview

A personal AI assistant ecosystem centered around a Discord bot ("Peter") that interfaces with Claude Code running in WSL via tmux. The system includes:

- **Discord Bot** - Message routing, scheduling, reactions
- **Peterbot (Claude Code)** - AI backend running in WSL tmux session
- **Memory System (claude-mem)** - Persistent memory across sessions
- **Second Brain** - Knowledge management with vector search
- **Hadley API** - REST proxy for external service integrations
- **Peter Dashboard** - Web UI for monitoring and control
- **NSSM Windows Services** - Reliable process management

---

## Infrastructure Components

### Windows Services (NSSM-managed)

| Service | Port | Purpose |
|---------|------|---------|
| HadleyAPI | 8100 | REST API proxy for external services |
| DiscordBot | - | Discord bot with APScheduler |
| PeterDashboard | 5000 | Web dashboard for monitoring |

All services: auto-start on boot, auto-restart on crash (5s delay), log rotation at 10MB.

**Logs**: `C:\Users\Chris Hadley\Discord-Messenger\logs\`

### WSL Components

- **claude-peterbot tmux session** - Claude Code instance for Peter
- **claude-mem worker** - Express API on port 37777 for memory processing
- **peterbot directory** - `/home/chris_hadley/peterbot` with symlinks to Windows config

---

## Core Components

### 1. Discord Bot (`bot.py`)

**Entry point**: `bot.py`
**Framework**: discord.py with APScheduler

**Key responsibilities**:
- Message routing to domain handlers based on channel
- Slash command registration (9 commands)
- APScheduler integration (26 jobs total)
- Message deduplication
- Reminder polling (60s interval)
- Second Brain passive capture

**Domain routing**:
```python
PETERBOT_CHANNEL_IDS = [...]  # Routes to peterbot domain
CLAUDE_CODE_CHANNEL = ...     # Routes to claude_code domain (dumb tunnel)
```

**Event handlers**:
- `on_ready`: Sync commands, init scheduler, load reminders
- `on_message`: Route to appropriate domain handler
- `on_reaction_add`: Handle reaction-based interactions

---

### 2. Peterbot Domain (`domains/peterbot/`)

The intelligent routing layer between Discord and Claude Code.

#### Router (`router.py`)

**Message flow**:
```
Discord message → router.py → memory context injection → tmux session → parse response → Discord
```

**Key features**:
- Session lock for concurrent access prevention
- Channel isolation (context cleared on channel switch)
- Interim update streaming (spinner detection)
- Image handling (Discord attachments → tmux)
- Busy message handling when processing

**Response parsing** (`parser.py`):
- Screen diff extraction (before/after comparison)
- ANSI stripping
- Response sanitization rules
- Instruction echo removal

#### Memory (`memory.py`)

**Per-channel conversation buffers**:
- Recent messages cached per channel
- Populated from Discord history on restart
- Injected as context before each message

**Circuit breaker**:
- Prevents hammering dead worker
- Graceful degradation during outages
- States: closed, open, half-open

**Capture store** (`capture_store.py`):
- SQLite persistence for captures
- Ensures no messages lost during outages
- Background processor retries failed captures

#### Scheduler (`scheduler.py`)

**Schedule source**: `SCHEDULE.md` in wsl_config
**Parser**: Markdown table format → APScheduler jobs

**Schedule formats**:
- Fixed time: `07:00 UK`, `Mon-Wed,Fri 08:10 UK`
- Hourly: `hourly+3 UK` (offset to avoid collisions)
- Half-hourly: `half-hourly+1 UK`
- Monthly: `1st 09:15 UK`

**Special features**:
- Quiet hours: 23:00-06:00 UK (no scheduled jobs)
- WhatsApp dual-posting: `#channel+WhatsApp`
- Quiet override: `#channel!quiet`

#### Response Pipeline (`response/pipeline.py`)

Five-stage processing for Claude's responses:
1. Raw extraction
2. Format detection
3. Sanitization
4. Length management
5. Delivery formatting

---

### 3. Skills System

**Location**: `domains/peterbot/wsl_config/skills/`
**Manifest**: `manifest.json` (auto-generated)

**55 skills** including:

| Category | Skills |
|----------|--------|
| Health | health-digest, weekly-health, monthly-health, nutrition-summary, hydration |
| Business (Hadley Bricks) | hb-pnl, hb-orders, hb-inventory-status, hb-pick-list, hb-dashboard, hb-tasks |
| Calendar/Email | email-summary, schedule-today, schedule-week, notion-todos |
| Traffic/Travel | school-run, school-pickup, traffic-check, directions, trip-prep |
| Monitoring | heartbeat, balance-monitor, api-usage, ring-status |
| Media | news, youtube-digest, football-scores, spurs-match |
| Utilities | weather, weather-forecast, ev-charging, whatsapp-keepalive |

**Skill structure**:
```
skills/<name>/
  SKILL.md        # Instructions, triggers, format
  (optional files)
```

**Data fetchers** (`data_fetchers.py`):
- Pre-fetch data before skill execution
- Inject as context for Claude

---

### 4. Second Brain (`domains/second_brain/`)

Knowledge management system with semantic search.

#### Database Schema (Supabase + pgvector)

**Tables**:
- `knowledge_items` - Parent items (articles, notes, ideas, calendar events)
- `knowledge_chunks` - Searchable text chunks with embeddings (384-dim gte-small)
- `knowledge_connections` - Discovered relationships between items

**Content types**: article, note, idea, voice_memo, url, document, conversation_extract, bookmark, training_data, social_save, calendar_event, calendar_pattern, key_date

**Capture types**:
- `explicit` - User commanded (!save) - priority 1.0
- `passive` - Auto-detected from conversation - priority 0.3
- `seed` - Bulk imported - priority 0.8

**Source systems**: discord, seed:github, seed:claude, seed:gemini, seed:gdrive, seed:gcal, seed:email, seed:bookmarks, seed:garmin, seed:instagram

#### Pipeline (`pipeline.py`)

```
Source → Extract content → Generate title/summary → Extract topics → Chunk text → Generate embeddings → Store in DB
```

**No API calls for processing** - uses keyword extraction and embedding-based search.

#### Seed Adapters (`seed/adapters/`)

- `calendar.py` - Google Calendar events
- `email.py` - Gmail categories (receipts, travel, subscriptions, etc.)
- `github.py` - Repository information
- Additional adapters for various sources

#### Components

- `embed.py` - Embedding generation (Supabase gte-small built-in)
- `chunk.py` - Text chunking for embedding
- `extract.py` - Content extraction from URLs/text
- `tag.py` - Topic extraction
- `db.py` - Database operations
- `digest.py` - Weekly knowledge digest generation

---

### 5. Hadley API (`hadley_api/`)

FastAPI REST proxy for external service integrations.

**Port**: 8100
**Auth**: API key for protected endpoints (localhost exempt)

#### Endpoints by Service

**Google (OAuth)**:
- `/gmail/unread`, `/gmail/search`, `/gmail/read/{id}`, `/gmail/raw/{id}`
- `/calendar/today`, `/calendar/week`, `/calendar/range`, `/calendar/upcoming`
- `/drive/search`, `/drive/read/{id}`
- `/contacts/search`
- `/sheets/{id}`, `/docs/{id}`
- `/tasks/lists`, `/tasks/{list_id}`

**Notion**:
- `/notion/todos`, `/notion/ideas`

**Health/IoT**:
- `/nutrition/*` - Garmin/Withings data
- `/ring/*` - Ring doorbell status
- `/kia/*`, `/ev/*` - Electric vehicle status
- `/whatsapp/*` - Twilio WhatsApp sending

**Browser Automation**:
- `/browser/*` - Playwright-based purchasing (Phase 9)

**Utility**:
- `/qr/generate` - QR code generation
- `/health` - Health check

#### Supporting Modules

- `google_auth.py` - OAuth token management
- `notion_client.py` - Notion API wrapper
- `browser_routes.py` - Browser automation endpoints

---

### 6. Peter Dashboard (`peter_dashboard/`)

FastAPI web application for system monitoring.

**Port**: 5000
**Features**:
- Real-time service status (WebSocket)
- Log viewing (NSSM logs + app logs)
- Service control (start/stop/restart via NSSM)
- Key file viewing/editing
- tmux session monitoring
- Background task status

#### Service Manager (`service_manager.py`)

**NSSM-aware service control**:
- Detects NSSM vs PID-file managed services
- Uses `net stop/start` for NSSM services (no admin required from service context)
- Tracks process status, port usage, orphan detection

---

### 7. Memory System (claude-mem)

External plugin providing persistent memory for Claude Code.

**Worker**: Express API on port 37777
**Database**: SQLite3 at `~/.claude-mem/claude-mem.db`
**Vectors**: Chroma for semantic search

**Lifecycle hooks**:
1. SessionStart
2. UserPromptSubmit
3. PostToolUse
4. Summary
5. SessionEnd

**Integration with Peterbot**:
- Memory context injected before each message
- Conversation exchanges captured after response
- Semantic search via MCP tools

---

## Scheduled Jobs

### Infrastructure Jobs (always running)

| Job | Interval | Purpose |
|-----|----------|---------|
| worker_health | 15 min | Check claude-mem worker status |
| capture_processor | 30 sec | Process pending memory captures |
| capture_cleanup | daily 3:00 AM | Clean old captures |
| incremental_seed | daily 1:00 AM | Second Brain seed imports |
| embedding_report | daily 3:00 AM | Embedding statistics |

### Skill-Based Jobs (from SCHEDULE.md)

21 jobs defined in SCHEDULE.md including:
- Morning briefing (07:00)
- News digest (07:02)
- Health digest (07:55)
- School runs (08:10 / 07:45 Thu)
- Hydration reminders (every 2 hours)
- Balance monitor (hourly)
- Heartbeat (half-hourly)
- Email/calendar summaries
- Weekly/monthly health reports

---

## Database Schemas

### Supabase Tables

1. **reminders** - One-off scheduled notifications
   - id, user_id, channel_id, task, run_at, fired_at

2. **knowledge_items** - Second Brain parent items
   - content_type, capture_type, title, source_url, full_text, summary, topics
   - base_priority, decay_score, access_count

3. **knowledge_chunks** - Searchable chunks with embeddings
   - parent_id, chunk_index, content, embedding (vector 384)

4. **knowledge_connections** - Item relationships
   - item_a_id, item_b_id, connection_type, similarity_score

5. **purchase_limits** - Browser purchasing limits
   - limit_type (per_order/daily/weekly), amount_gbp

6. **purchase_log** - Purchase transaction history
   - session_id, domain, amount_gbp, status, order_reference

7. **browser_action_log** - Browser action audit trail
   - action_type, action_data, screenshots, page_url

8. **browser_sessions** - Active browser session tracking

---

## Configuration

### Environment Variables (.env)

```
# Discord
DISCORD_TOKEN=

# Claude (renamed to prevent pickup)
DISCORD_BOT_CLAUDE_KEY=

# Supabase
SUPABASE_URL=
SUPABASE_KEY=

# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=

# Notion
NOTION_API_KEY=
NOTION_TODOS_DATABASE_ID=
NOTION_IDEAS_DATABASE_ID=

# Health devices
GARMIN_EMAIL=
GARMIN_PASSWORD=
WITHINGS_CLIENT_ID=
WITHINGS_CLIENT_SECRET=
WITHINGS_ACCESS_TOKEN=
WITHINGS_REFRESH_TOKEN=

# Other APIs
GOOGLE_MAPS_API_KEY=
FOOTBALL_DATA_API_KEY=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_FROM=
GROK_API_KEY=
MOONSHOT_API_KEY=
HADLEY_API_KEY=
```

### Key Config Files

- `config.py` - Global Python configuration
- `domains/peterbot/config.py` - Peterbot-specific settings
- `domains/peterbot/wsl_config/CLAUDE.md` - Claude's instructions
- `domains/peterbot/wsl_config/PETERBOT_SOUL.md` - Personality definition
- `domains/peterbot/wsl_config/SCHEDULE.md` - Scheduled jobs
- `domains/peterbot/wsl_config/HEARTBEAT.md` - Self-monitoring notes

---

## Data Flow Diagrams

### Message Processing Flow

```
User (Discord)
    │
    ▼
Discord Bot (bot.py)
    │
    ├─ Channel routing
    │
    ▼
Peterbot Router (router.py)
    │
    ├─ Acquire session lock
    ├─ Inject memory context
    ├─ Clear context if channel changed
    │
    ▼
Claude Code (tmux session in WSL)
    │
    ├─ Read CLAUDE.md, skills, playbooks
    ├─ Process with memory MCP
    │
    ▼
Response Parser (parser.py)
    │
    ├─ Screen diff extraction
    ├─ ANSI stripping
    ├─ Sanitization
    │
    ▼
Response Pipeline (response/pipeline.py)
    │
    ├─ Format detection
    ├─ Length management
    │
    ▼
Discord (send response)
    │
    ▼
Memory Capture (async)
    │
    ├─ Store in SQLite (capture_store)
    ├─ Send to worker (circuit breaker protected)
    │
    ▼
Second Brain (passive capture if applicable)
```

### Scheduled Job Flow

```
APScheduler (bot.py)
    │
    ├─ Check quiet hours
    │
    ▼
Peterbot Scheduler (scheduler.py)
    │
    ├─ Load skill SKILL.md
    ├─ Fetch data (data_fetchers.py)
    │
    ▼
Claude Code (tmux)
    │
    ├─ Execute skill instructions
    │
    ▼
Response → Discord channel (or WhatsApp)
```

---

## File Structure Summary

```
Discord-Messenger/
├── bot.py                      # Main Discord bot entry
├── config.py                   # Global configuration
├── logger.py                   # Logging setup
│
├── domains/
│   ├── peterbot/               # Peterbot AI assistant
│   │   ├── domain.py           # Domain registration
│   │   ├── router.py           # Message routing
│   │   ├── scheduler.py        # APScheduler integration
│   │   ├── memory.py           # Memory context
│   │   ├── parser.py           # Response parsing
│   │   ├── config.py           # Peterbot config
│   │   ├── data_fetchers.py    # Skill data pre-fetch
│   │   ├── capture_store.py    # SQLite capture persistence
│   │   ├── circuit_breaker.py  # Worker protection
│   │   ├── response/           # Response pipeline
│   │   ├── reminders/          # Reminder handling
│   │   └── wsl_config/         # WSL config (symlinked)
│   │       ├── CLAUDE.md       # Claude instructions
│   │       ├── PETERBOT_SOUL.md
│   │       ├── SCHEDULE.md     # Scheduled jobs
│   │       ├── HEARTBEAT.md    # Self-monitoring
│   │       └── skills/         # 55 skill definitions
│   │
│   ├── second_brain/           # Knowledge management
│   │   ├── pipeline.py         # Capture pipeline
│   │   ├── embed.py            # Embeddings
│   │   ├── chunk.py            # Text chunking
│   │   ├── extract.py          # Content extraction
│   │   ├── tag.py              # Topic extraction
│   │   ├── db.py               # Database operations
│   │   ├── digest.py           # Weekly digest
│   │   └── seed/               # Seed adapters
│   │
│   ├── claude_code/            # Dumb tunnel domain
│   ├── nutrition/              # Health data domain
│   ├── news/                   # News domain
│   └── api_usage/              # API monitoring
│
├── hadley_api/                 # REST API proxy
│   ├── main.py                 # FastAPI app (8100)
│   ├── google_auth.py          # OAuth management
│   ├── notion_client.py        # Notion API
│   └── browser_routes.py       # Browser automation
│
├── peter_dashboard/            # Web dashboard
│   ├── app.py                  # FastAPI app (5000)
│   └── service_manager.py      # NSSM service control
│
├── jobs/                       # Infrastructure jobs
│   ├── worker_health.py
│   ├── capture_processor.py
│   ├── incremental_seed.py
│   └── embedding_report.py
│
├── migrations/                 # SQL migrations
│   ├── 001_create_reminders_table.sql
│   ├── 002_create_second_brain_tables.sql
│   └── 003_create_purchase_tables.sql
│
├── logs/                       # NSSM service logs
├── data/                       # Local data (captures DB)
├── docs/                       # Documentation
└── setup_services.ps1          # NSSM setup script
```

---

## External Dependencies

### Python Packages (key ones)

- discord.py - Discord bot framework
- fastapi + uvicorn - REST API
- apscheduler - Job scheduling
- aiohttp - Async HTTP client
- supabase-py - Supabase client
- httpx - HTTP client for API calls
- garminconnect - Garmin API
- withings-api - Withings API
- google-api-python-client - Google APIs
- playwright - Browser automation

### External Services

- **Discord** - Bot hosting platform
- **Supabase** - Database (PostgreSQL + pgvector)
- **Anthropic Claude** - AI model (via Claude Code)
- **Google Cloud** - OAuth, Gmail, Calendar, Drive
- **Notion** - Task/idea management
- **Garmin Connect** - Fitness data
- **Withings** - Health device data
- **Ring** - Doorbell status
- **KIA Connect** - EV status
- **Twilio** - WhatsApp messaging
- **Various APIs** - Football data, maps, etc.

---

## Security Considerations

1. **API Key Protection** - HADLEY_API_KEY for remote access
2. **Localhost Exemption** - Local requests bypass API key
3. **RLS on Supabase** - Row-level security on sensitive tables
4. **Credential Storage** - .env file (not committed)
5. **Service Isolation** - NSSM services run with limited permissions
6. **Input Validation** - tmux session names validated
7. **Rate Limiting** - slowapi on API endpoints

---

## Known Limitations

1. **Single Claude Session** - One tmux session, session lock prevents concurrent messages
2. **WSL Dependency** - Requires WSL2 Ubuntu for Claude Code
3. **Symlink Fragility** - WSL symlinks can break if created through Git Bash
4. **Memory Worker** - Single point of failure (circuit breaker mitigates)
5. **Quiet Hours** - No scheduled jobs 23:00-06:00 UK

---

*Document generated for architecture documentation purposes. Last updated: February 2026*
