# Domains & Integrations

## Domain Architecture

The Discord Messenger uses domain-driven design. Each domain extends `domains.base.Domain` (an abstract base class) and provides:

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Domain identifier |
| `channel_id` | `int` | Discord channel this domain handles |
| `system_prompt` | `str` | Claude system prompt |
| `tools` | `list[ToolDefinition]` | Available tools for the domain |
| `schedules` | `list[ScheduledTask]` | Optional cron-style scheduled tasks |

Supporting types:
- **`ToolDefinition`** -- name, description, input_schema (JSON Schema), handler function. Converted to Claude API tool format via `to_api_format()`.
- **`ScheduledTask`** -- name, handler, hour, minute, day_of_week, timezone. Registered with APScheduler via `register_schedules()`.

---

## Domains

### 1. Peterbot (Primary)

**Location:** `domains/peterbot/`
**Channel:** Environment variable `PETERBOT_CHANNEL_ID`
**Purpose:** Primary conversational AI assistant -- all Discord and WhatsApp conversations flow through this domain.
**Documented in:** [CORE_BOT.md](./CORE_BOT.md)

Unlike other domains, Peterbot does not extend the `Domain` base class. It uses a dedicated routing architecture:

| Component | File | Purpose |
|-----------|------|---------|
| `router_v2.py` | CLI mode (default) | `claude -p --output-format stream-json --verbose` |
| `scheduler.py` | Job execution | Routes scheduled jobs to channel or CLI |
| `memory.py` | Context injection | Second Brain memory retrieval, buffer management |
| `config.py` | Configuration | Timeouts, provider cascade, channel mappings |
| `provider_manager.py` | Model fallback | 3-tier cascade: claude_cc -> claude_cc2 -> kimi |
| `kimi_provider.py` | Emergency fallback | Moonshot Kimi K2.5 API (no MCP, degraded mode) |
| `data_fetchers.py` | Pre-fetch data | Parallel data fetch for scheduled skills |
| `spotify_service.py` | Spotify integration | Spotipy client for playback control |
| `japan_alerts.py` | Japan trip monitoring | Train status, alerts |
| `purchase_confirmation.py` | Purchase workflows | Vinted/eBay purchase handling |
| `pending_actions.py` | Action queue | Deferred actions requiring confirmation |
| `feedback_processor.py` | Response quality | User feedback capture and processing |
| `parser.py` | Response parsing | Extract clean responses from CLI output |
| `response/` | Pipeline | sanitise -> classify -> format -> chunk |
| `wsl_config/` | WSL-side config | Symlinked to `~/peterbot` (CLAUDE.md, SCHEDULE.md, skills/) |

**Provider Cascade:**

| Priority | Provider | Config Dir | Capabilities |
|----------|----------|------------|-------------|
| 1 | `claude_cc` | `~/.claude` (default) | Full: MCP tools, CLAUDE.md, Second Brain |
| 2 | `claude_cc2` | `~/.claude-secondary` | Full: same as cc, different subscription |
| 3 | `kimi` | N/A (API) | Degraded: no MCP, no CLAUDE.md, pre-fetched data only |

Auto-switch triggers on credit exhaustion keywords (429, rate limit, quota exceeded, etc.). State persisted in `data/model_config.json`.

**Data Fetchers** (pre-fetch data for scheduled skills):
- `get_nutrition_data()` -- today's nutrition totals, steps, targets
- `get_hydration_data()` -- water intake, steps, time-of-day info

---

### 2. Nutrition

**Location:** `domains/nutrition/`
**Channel:** `1465294449038069912`
**Purpose:** Meal planning, macro tracking, fitness goals, health device integration

**System Prompt Personality:** "Pete" -- tough-love PT with banter. Goal: Chris hitting 80kg by April 2026 for Japan trip.

**Daily Targets:**

| Metric | Target |
|--------|--------|
| Calories | 2,100 |
| Protein | 120g |
| Carbs | 263g |
| Fat | 70g |
| Water | 3,500ml |
| Steps | 15,000 |

**Tools (14):**

| Tool | Handler | Description |
|------|---------|-------------|
| `log_meal` | `insert_meal` | Log meal with macros (breakfast/lunch/dinner/snack) |
| `log_water` | `insert_water` | Log water intake in ml |
| `get_today_totals` | `get_today_totals` | Daily nutrition totals vs targets |
| `get_today_meals` | `get_today_meals` | All meals logged today with timestamps |
| `get_steps` | `get_steps` | Today's step count from Garmin |
| `get_weight` | `get_weight` | Latest weight from Withings |
| `get_week_summary` | `get_week_summary` | Past 7 days daily totals |
| `get_weight_history` | `get_weight_history` | Weight trend (default 30 days) |
| `get_goals` | `get_goals` | Current targets and goal info |
| `update_goal` | `update_goal` | Modify any target or deadline |
| `save_favourite` | `save_favourite` | Save meal as preset for quick logging |
| `get_favourite` | `get_favourite` | Retrieve saved favourite by name |
| `list_favourites` | `list_favourites` | List all saved meal presets |
| `delete_favourite` | `delete_favourite` | Remove a saved favourite |

**Services (17 files):**

| Service | Purpose |
|---------|---------|
| `supabase_service.py` | Database interface (nutrition tables) |
| `garmin.py` | Steps, sleep, heart rate from Garmin Connect |
| `withings.py` | Weight tracking via Withings API |
| `family_fuel_service.py` | Family meal tracking (separate Supabase: `pocptwknyxyrtmnfnrph`) |
| `recipe_extractor.py` | Extract structured data from recipe URLs (Chrome CDP, JSON-LD) |
| `recipe_discovery_service.py` | Recipe recommendation engine |
| `recipe_card_generator.py` | Visual recipe card creation |
| `meal_plan_service.py` | Weekly meal plan CRUD |
| `meal_plan_config_service.py` | Template and preference management |
| `cooking_reminder_service.py` | Prep reminders based on meal plan |
| `grocery_service.py` | Sainsbury's Chrome CDP integration |
| `price_cache_service.py` | Grocery price tracking |
| `gousto_importer.py` | Import Gousto recipe box meals |
| `favourites_service.py` | Saved meal favourites |
| `goals_service.py` | Nutrition goals management |

**Scheduled Tasks:**

| Task | Schedule | Description |
|------|----------|-------------|
| `daily_summary` | 21:00 UK | Posts daily nutrition summary with emoji progress indicators |

---

### 3. News

**Location:** `domains/news/`
**Channel:** `1465277483866788037` (#ai-news)
**Purpose:** AI/tech news aggregation and personalised briefings

**RSS Sources:**

| Category | Sources |
|----------|---------|
| Tech | Hacker News, Ars Technica |
| UK | BBC UK News |
| F1 | Autosport F1 |

**Tools (2):**

| Tool | Handler | Description |
|------|---------|-------------|
| `get_headlines` | `fetch_feed` | Latest headlines by category (tech, uk, f1, or all) |
| `read_article` | `fetch_article` | Fetch and summarise a specific article by URL |

**Scheduled Tasks:**

| Task | Schedule | Description |
|------|----------|-------------|
| `morning_briefing` | 07:00 UK | Top headlines: 3 tech, 2 UK, 2 F1 |

---

### 4. API Usage

**Location:** `domains/api_usage/`
**Channel:** `1465761699582972142` (#api-balances)
**Purpose:** Track API spend across Claude, OpenAI, Google (Gemini), and GCP

**Budget Alerts:**
- Daily warning threshold: $1.00
- Monthly budget cap: $20.00

**Tools (5):**

| Tool | Handler | Description |
|------|---------|-------------|
| `get_anthropic_usage` | `get_anthropic_usage` | Claude API usage for a period |
| `get_openai_usage` | `get_openai_usage` | OpenAI API usage for a period |
| `get_google_usage` | `get_google_usage` | Gemini API usage and estimated cost |
| `get_google_daily_breakdown` | `get_google_daily_breakdown` | Day-by-day Gemini spend per model |
| `get_vision_effectiveness` | `get_vision_effectiveness` | Vinted Sniper Gemini Vision hit rate, response times |

**Services:**

| Service | Purpose |
|---------|---------|
| `anthropic_scraper.py` | Scrape Anthropic dashboard for usage data |
| `anthropic_usage.py` | Anthropic API usage tracking |
| `openai_usage.py` | OpenAI API usage tracking |
| `google_usage.py` | Google Workspace API usage |
| `gcp_monitoring.py` | Google Cloud Platform cost monitoring |

**Scheduled Tasks:**

| Task | Schedule | Description |
|------|----------|-------------|
| `weekly_summary` | Monday 09:00 UK | All providers: Anthropic + OpenAI + Gemini (billable total) |
| `daily_google_spend` | Daily 08:00 UK | 7-day Gemini spend table + Vision effectiveness report |

---

### 5. Claude Code

**Location:** `domains/claude_code/`
**Channel:** Environment variable `CLAUDE_CODE_CHANNEL_ID`
**Purpose:** Remote control of Claude Code tmux sessions from Discord. Direct command proxy -- no LLM involved.

**Pattern-Matching Router** (`router.py`):

The router uses regex pattern matching to route Discord messages to tmux actions. No Claude API calls needed.

| Command | Action |
|---------|--------|
| `@prefix: prompt` | Send to specific session (fuzzy match) |
| `sessions` / `ls` | List active tmux sessions |
| `screen` / `s` | Show last 40 lines of output |
| `screen N` | Show last N lines |
| `up` / `scroll` | Earlier history |
| `status` | All sessions with last activity times |
| `y` / `n` | Approve/deny permission |
| `esc` | Send Escape key |
| `ctrl-c` | Send Ctrl+C interrupt |
| `start <name>` | Start new session (project name or path) |
| `stop <name>` | Stop session |
| `attach` | Open Windows Terminal for session |
| `use <name>` | Set default target session |
| `projects` | List registered projects |
| `/command` | Forward slash command to session |
| _(anything else)_ | Forward as prompt to active session |

**Components:**

| File | Purpose |
|------|---------|
| `tools.py` | Tmux interaction (WSL-aware). Screen capture, send keys, session lifecycle. |
| `router.py` | Pattern-matching command router with session targeting |
| `projects.py` | Project registry with path shortcuts |
| `session_store.py` | Persistent session tracking (active session, activity timestamps) |
| `config.py` | Session prefix (`claude-`), screen line defaults, data paths |

**Platform Handling:** On Windows, all tmux commands are wrapped in `wsl bash -c`. New sessions auto-open Windows Terminal. ANSI escape codes and box-drawing characters are stripped from captured output.

---

### 6. Second Brain

**Location:** `domains/second_brain/`
**Purpose:** Long-term semantic memory with vector search (pgvector)
**Documented in:** [SECOND_BRAIN.md](./SECOND-BRAIN.md)

**Database:** Supabase project `modjoikyuhqzouxvieua` with pgvector (gte-base, 768-dim embeddings).

**Core Modules:**

| Module | Purpose |
|--------|---------|
| `db.py` | Supabase REST operations via httpx (shared client, 10 connections) |
| `embed.py` | Embedding generation via Supabase Edge Function |
| `chunk.py` | Content chunking (300 words, 50-word overlap, max 40 chunks) |
| `pipeline.py` | Full ingest pipeline: extract -> chunk -> embed -> store |
| `passive.py` | Auto-capture from conversations (signal phrases) |
| `surfacing.py` | Contextual surfacing of relevant knowledge |
| `connections.py` | Discover semantic connections between items |
| `decay.py` | Time-based relevance decay (90-day half-life) |
| `tag.py` | Domain tag assignment (17 tag groups, 60+ tags) |
| `extract.py` | Content extraction from various formats |
| `extract_structured.py` | Structured fact/concept extraction via Claude |
| `conversation.py` | Conversation-aware memory operations |
| `digest.py` | Knowledge digest generation |
| `health.py` | Health monitoring (orphaned items, decay stats, embed failures) |
| `admin.py` | Administrative operations |
| `commands.py` | User-facing commands |
| `summarise.py` | Content summarisation |
| `types.py` | Type definitions (KnowledgeItem, KnowledgeChunk, SearchResult, etc.) |
| `audit_report.py` | Audit report generation |

**Seed Adapters** (`seed/adapters/` -- 22 import sources):

| Adapter | Source |
|---------|--------|
| `bookmarks.py` | Browser bookmarks |
| `calendar.py` | Google Calendar events |
| `claude_code_history.py` | Claude Code session history |
| `claude_history.py` | Claude conversation history |
| `email.py` | Gmail emails |
| `email_links.py` | Links extracted from emails |
| `finance_summary.py` | Financial summaries |
| `garmin.py` | Garmin activity data |
| `garmin_health.py` | Garmin health metrics |
| `github.py` | GitHub repositories |
| `hadley_bricks_email.py` | Hadley Bricks business emails |
| `netflix.py` | Netflix viewing history |
| `peter_interactions.py` | Peter conversation history |
| `recipes.py` | Recipe collection |
| `reddit.py` | Reddit saved posts |
| `school.py` | School information |
| `spotify.py` | Spotify live API (last 50 tracks) |
| `spotify_export.py` | Spotify full data export (ZIP) |
| `travel.py` | Travel plans |
| `withings.py` | Withings health data |

**Configuration Highlights:**
- Similarity threshold: 0.75 (surfacing), 0.72 (connections)
- MMR diversity: 70% relevance / 30% diversity
- Decay half-life: 90 days with access boost
- Passive capture signals: "idea:", "note to self", "remember to", etc.

---

### 7. Data

**Location:** `domains/data/`
**Purpose:** Static data assets

Contains `instagram_prep/` with concept folders for Hadley Bricks Instagram content.

---

## External Integrations

### Google Services (via Hadley API OAuth)

The Hadley API (`hadley_api/google_auth.py`) handles OAuth 2.0 with automatic token refresh. Supports two accounts:
- **personal** -- Chris's personal Gmail (`GOOGLE_REFRESH_TOKEN`)
- **hadley-bricks** -- chris@hadleybricks.co.uk (`GOOGLE_REFRESH_TOKEN_HB`)

OAuth scopes: Gmail (read/compose/send/modify/settings), Calendar (full), Drive (full), Contacts (full), Tasks (full), Sheets (full), Docs (full).

| Service | Prefix | Endpoint Count | Key Operations |
|---------|--------|----------------|----------------|
| Gmail | `/gmail/*` | 20 | unread, search, get, labels, starred, thread, draft, send, reply, forward, archive, trash, mark-read, attachments, attachment/text, filters, signature, vacation |
| Calendar | `/calendar/*` | 16 | today, week, meal-context, free, range, create, event (get/delete/update), recurring, invite, calendars, busy, search, quickadd, next, conflicts |
| Drive | `/drive/*` | 16 | search, create, upload, share, recent, trash, folder, move, copy, rename, export, permissions, storage, starred, shared, download |
| Sheets | `/sheets/*` | 5 | read, write, append, clear, info |
| Docs | `/docs/*` | 2 | read, append |
| Tasks | `/tasks/*` | 3 | list, create, complete |
| Contacts | `/contacts/*` | 1 | search |
| Maps / Places | `/directions`, `/places/*`, `/geocode`, etc. | 10 | directions, places/search, places/details, places/nearby, places/autocomplete, directions/matrix, geocode, timezone, elevation, distance |

---

### WhatsApp (Evolution API)

**Hadley API routes:** `/whatsapp/*` (webhook receiver + send endpoints)
**Channel:** `whatsapp-channel/` (HTTP :8102 via Anthropic channels)

- Self-hosted Evolution API instance
- Incoming messages received via webhook, routed to Peter
- Voice notes transcribed (STT via faster-whisper) and responses include voice (TTS via Kokoro ONNX)
- Allowed senders: Chris Hadley, Abby Hadley
- Debounce: 3-second buffer, up to 5 messages batched

---

### Spotify

**Service:** `domains/peterbot/spotify_service.py` (spotipy, sync -- callers use `asyncio.to_thread()`)
**API routes:** `/spotify/*`

Full scopes include: playback state, modify playback, library read/modify, playlists (read/write), user profile, follow, recently played, top tracks.

| Category | Capabilities |
|----------|-------------|
| Playback | Play, pause, skip, previous, seek, volume, shuffle, repeat |
| Queue | Add tracks to queue |
| Devices | List devices, transfer playback between Spotify Connect devices |
| Search | Search tracks/albums/artists/playlists |
| Playlists | List, search, play by name |
| Now Playing | Current track with mood data |
| Recommendations | Based on currently playing track |

---

### Notion

**Client:** `hadley_api/notion_client.py`
**API routes:** `/notion/todos`, `/notion/ideas`

| Database | ID env var | Purpose |
|----------|-----------|---------|
| Todos | `NOTION_TODOS_DATABASE_ID` | Personal task management |
| Ideas | `NOTION_IDEAS_DATABASE_ID` | Ideas capture and tracking |

Supports full CRUD with status workflow via Notion API v2022-06-28.

---

### Health Services

| Service | Location | Data |
|---------|----------|------|
| **Garmin Connect** | `domains/nutrition/services/garmin.py` | Steps, sleep, heart rate, activities |
| **Withings** | `domains/nutrition/services/withings.py` | Body weight, composition |
| **Withings status** | `/withings/status` API endpoint | Connection health check |

---

### Home & Vehicle

| Service | API Endpoint | Purpose |
|---------|-------------|---------|
| **Ring** | `GET /ring/status` | Doorbell status |
| **Kia Connect** | `GET /kia/status` | Vehicle status, battery level |
| **EV Charger (Ohme)** | `GET /ev/status` | Charger state |
| **EV Combined** | `GET /ev/combined` | Kia + Ohme combined view |

---

### Financial

| Service | Integration Point | Purpose |
|---------|-------------------|---------|
| **Personal Finance** | `mcp_servers/financial_data/personal_finance.py` | Net worth, budget, spending, savings, FIRE, transactions |
| **Business Finance** | `mcp_servers/financial_data/business_finance.py` | Platform revenue, P&L (eBay, Amazon, BrickLink, Brick Owl) |
| **Finance API** | `hadley_api/finance_routes.py` (prefix `/finance`) | REST endpoints for financial data |
| **GCP Billing** | `domains/api_usage/services/gcp_monitoring.py` | Google Cloud cost monitoring |
| **Monzo** | Via Supabase | Bank transactions |
| **HB Proxy** | `/hb/{path}` -> `localhost:3000` | Hadley Bricks Next.js app API proxy (auto-injects API key) |

---

### Content Platforms

| Platform | Integration | Purpose |
|----------|-------------|---------|
| **YouTube** | `/youtube/search` API endpoint | Search and subscription digest |
| **Instagram** | Via Google Drive + skills | Content prep and scheduling (Hadley Bricks) |
| **Vinted** | `hadley_api/vinted_routes.py` | Gmail parsing for collection notifications |

---

### AI Providers

| Provider | Purpose | Config | MCP Support |
|----------|---------|--------|-------------|
| **Claude (Anthropic)** | Primary -- conversations + skills | `claude_cc` (default `~/.claude`) | Full |
| **Claude Secondary** | Fallback on credit exhaustion | `claude_cc2` (`~/.claude-secondary`) | Full |
| **Kimi K2.5 (Moonshot)** | Emergency fallback | `api.moonshot.ai`, OpenAI-compatible | None (degraded mode) |
| **Gemini (Google)** | Vinted image analysis | Via Hadley Bricks app | N/A |

**Kimi Fallback Details:**
- API base: `https://api.moonshot.ai/v1`
- Model: `kimi-k2.5`
- Max tokens: 4,096
- Pricing: $0.60/M input, $3.00/M output
- Limitations: no MCP tools, no CLAUDE.md auto-load. Pre-fetched context (memory, knowledge, skill data) is injected into user messages.

---

### Voice (STT / TTS)

**Engine:** `hadley_api/voice_engine.py`
**API routes:** `/voice/*`

| Component | Technology | Details |
|-----------|-----------|---------|
| STT | faster-whisper | Model: `small.en`, CPU-only |
| TTS | Kokoro ONNX | Model: `kokoro-v1.0.onnx`, voice: `bm_daniel`, 24kHz, en-gb |

Models auto-downloaded on first use to `models/voice/`. Both run locally -- no external API calls.

---

### Browser Automation

**API routes:** `/browser/*` (`hadley_api/browser_routes.py`)

| Method | Default | Fallback |
|--------|---------|----------|
| Chrome CDP | Port 9222, real Chrome with cookies | -- |
| Playwright | -- | Headless browser |

- Domain allowlist enforced (amazon.co.uk, ebay.co.uk, premierinn.com, etc.)
- Spending limiter per user
- Session-based: start -> navigate -> interact -> close

---

### Vault (Encrypted Storage)

**API routes:** `/vault/cards` (`hadley_api/vault_routes.py`)

Encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256). Data never leaves localhost. No logging of sensitive fields.

| Endpoint | Purpose |
|----------|---------|
| `POST /vault/cards` | Save new card (encrypts + writes to disk) |
| `GET /vault/cards` | List cards (last-4 digits only) |
| `GET /vault/cards/default` | Full card details (browser automation only) |
| `DELETE /vault/cards/{id}` | Remove a card |

---

### Utility Endpoints

The Hadley API exposes numerous utility endpoints that Peter uses for general-purpose queries:

| Category | Endpoints | Examples |
|----------|-----------|---------|
| Weather | `/weather/current`, `/weather/forecast` | Current conditions, 5-day forecast |
| Traffic | `/traffic/school` | School run traffic estimate |
| Location | `/location/{person}` | Family member location |
| Conversion | `/currency`, `/units`, `/calculate` | Currency rates, unit conversion, math |
| Reference | `/wikipedia`, `/dictionary`, `/synonyms` | Lookups |
| Fun | `/quote`, `/fact` | Random quotes, facts |
| Network | `/ip`, `/dns`, `/whois`, `/ping` | Network diagnostics |
| Encoding | `/encode`, `/qrcode`, `/shorten` | URL encoding, QR codes, URL shortener |
| Time | `/time`, `/countdown`, `/age`, `/holidays`, `/sunrise`, `/moon` | Date/time utilities |
| ID | `/uuid`, `/random`, `/password`, `/color` | Generators |

---

### MCP Servers

Located in `mcp_servers/`:

| Server | File | Tools | Purpose |
|--------|------|-------|---------|
| Second Brain | `second_brain_mcp.py` | 6 | Knowledge base search and save |
| Financial Data | `financial_data_mcp.py` | 11 | Personal finance + Hadley Bricks business data |
| Keepa | `keepa_mcp.py` | -- | Amazon price history lookup |

Additional MCP servers configured externally (not in this repo):
- **Supabase** -- database operations
- **Brave Search** -- web search (`@brave/brave-search-mcp-server`)
- **SearXNG** -- self-hosted meta search (localhost:8888)
- **Context7** -- documentation lookup
- **Gmail** -- `@gongrzhe/server-gmail-autoauth-mcp`

---

### Deployment & Publishing

| Service | Purpose | Details |
|---------|---------|---------|
| **Surge.sh** | HTML publishing | Free, instant HTTPS URLs on global CDN |
| **NSSM** | Windows services | DiscordBot, HadleyAPI, PeterDashboard, HadleyBricks |
| `/deploy/surge` | API endpoint | Programmatic surge deployment |

---

### Schedule & Job Management

| Endpoint | Purpose |
|----------|---------|
| `GET /schedule` | Read SCHEDULE.md |
| `PUT /schedule` | Write SCHEDULE.md + trigger reload |
| `POST /schedule/reload` | Trigger reload only |
| `POST /schedule/run/{skill_name}` | Manually run a skill |
| `GET /schedule/jobs` | List registered jobs |
| `PATCH /schedule/jobs/{skill}` | Modify job config |
| `GET /schedule/pauses` | List paused skills |
| `POST /schedule/pauses` | Pause a skill |
| `GET /jobs/health` | Aggregated health across DM (SQLite) and HB (Supabase) |

---

### Reminders

| Endpoint | Purpose |
|----------|---------|
| `GET /reminders` | List active reminders |
| `POST /reminders` | Create reminder |
| `PATCH /reminders/{id}` | Update reminder |
| `DELETE /reminders/{id}` | Delete reminder |
| `POST /reminders/{id}/acknowledge` | Acknowledge a nag |
| `GET /reminders/active-nags` | Active nagging reminders |

---

### Meal Planning (Extended)

The Hadley API exposes a comprehensive meal planning system beyond the Nutrition domain tools:

| Category | Endpoints | Purpose |
|----------|-----------|---------|
| Plans | CRUD on `/meal-plan/*` | Create, view, delete meal plans |
| Import | `/meal-plan/import/sheets`, `/csv`, `/gousto` | Import from Google Sheets, CSV, Gousto |
| Shopping | `/meal-plan/shopping-list/*` | Generate, view, HTML export, push to trolley |
| Templates | `/meal-plan/templates/*` | Meal plan templates and preferences |
| Staples | `/meal-plan/staples/*` | Recurring staple items management |
| History | `/meal-plan/history` | Past meal tracking with ratings |
| Recipes | `/recipes/*` | Extract, discover, search, CRUD, recipe cards |
| Grocery | `/grocery/{store}/*` | Price scan, search, slots, trolley (Sainsbury's CDP) |
