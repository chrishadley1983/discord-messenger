# Peter's Memory & Intelligence Architecture

> **System**: Discord-Messenger (Peterbot)
> **Owner**: Chris Hadley
> **Updated**: March 2026

---

## Overview

Peter is a personal AI assistant running as a Discord bot on Windows, with Claude Code executing in WSL2. The system combines three intelligence layers into a unified memory architecture that knows Chris's life — family, business (Hadley Bricks LEGO resale), health, finances, travel, and projects.

```
                          PETER'S INTELLIGENCE STACK
 ================================================================

  INTERFACE          Discord Bot + WhatsApp (Twilio)
      |
  ROUTING            router_v2.py -> claude -p (WSL2)
      |                 Provider cascade: Claude CC -> CC2 -> Kimi
      |
  MEMORY             Episodic (peterbot-mem)  +  Knowledge (Second Brain)
      |               "Remembers YOU"            "Remembers STUFF"
      |               SQLite + ChromaDB          Supabase + pgvector
      |
  ENRICHMENT         14 Seed Adapters (daily import at 1am)
      |               Gmail, Calendar, Garmin, Spotify, Netflix,
      |               GitHub, Bookmarks, Recipes, Travel, Finance...
      |
  AI PROCESSING      Claude CLI (/claude/extract on Hadley API)
      |               Summarise, Tag, Extract Facts/Concepts
      |
  INFRASTRUCTURE     Hadley API (FastAPI :8100) + Supabase Cloud
                      MCP Servers (Second Brain, Financial Data)
```

---

## 1. Message Flow

When Chris sends a Discord message:

1. **bot.py** receives the event, deduplicates, routes to Peterbot
2. **router_v2.py** builds context:
   - Per-channel conversation buffer (20 messages, isolated per channel)
   - Second Brain knowledge context (hybrid semantic + keyword search)
   - Attachment downloads (images from Discord CDN)
3. **invoke_llm()** sends to Claude Code via WSL:
   - `wsl bash -c "cd ~/peterbot && claude -p --output-format stream-json"`
   - Streams NDJSON events, extracts response
   - Provider cascade: `claude_cc` -> `claude_cc2` -> `kimi` (Moonshot)
4. **Response pipeline** processes output:
   - Classify (report/chat/alert), format (markdown), chunk (2000 char limit)
5. **Post-response** (async, fire-and-forget):
   - Capture message pair to memory
   - Auto-save to Second Brain (if document detected)
   - Log cost to `data/cli_costs.jsonl`

---

## 2. Three Memory Systems

### 2.1 Conversation Buffer (Short-term)

- **Per-channel deques** (20 messages max)
- **Isolation**: #food-log buffer is separate from #peterbot
- **Purpose**: Recent conversation context for Claude
- **Lifetime**: Session only (rebuilt from Discord history on startup)

### 2.2 Peterbot-mem (Episodic Memory)

- **Storage**: SQLite + ChromaDB (local)
- **Content**: Observations FROM conversations
- **Examples**: "Chris prefers concise responses", "Kids: Max, Emmie, Abby"
- **Retrieval**: Auto-injected into every conversation
- **Purpose**: Peter remembers YOU

### 2.3 Second Brain (Knowledge Store)

- **Storage**: Supabase PostgreSQL + pgvector (cloud)
- **Content**: External content TO retrieve
- **Examples**: Articles, emails, recipes, travel bookings, health data
- **Retrieval**: On-demand semantic search + proactive surfacing
- **Purpose**: Peter remembers STUFF

| Aspect | peterbot-mem | Second Brain |
|--------|-------------|--------------|
| What it stores | Observations FROM conversations | External content TO retrieve |
| Source | Peter learns from chatting | Explicit saves, passive capture, seed imports |
| Retrieval | Auto-injected into context | On-demand search + proactive surfacing |
| Storage | SQLite + ChromaDB (local) | Supabase + pgvector (cloud) |

---

## 3. Second Brain Pipeline

Every item (whether explicitly saved, passively captured, or imported by a seed adapter) flows through a 6-stage pipeline:

```
 Content In
     |
 1. EXTRACT     URL -> fetch + parse, or plain text
     |
 2. SUMMARISE   Claude CLI -> 2-3 sentence summary
     |           (via /claude/extract Hadley API endpoint)
 3. TAG         Claude CLI -> 3-8 topic tags
     |           (parallel with summarise)
 4. CHUNK       Split into ~300 word segments (50 word overlap)
     |
 5. EMBED       HuggingFace gte-small (384 dimensions)
     |
 6. STORE       Supabase: knowledge_items + knowledge_chunks
                 Dedup via source_url check
```

### AI Processing: Claude CLI

All AI processing (summarisation, tagging, structured extraction) routes through:
- **Hadley API** `POST /claude/extract` endpoint
- Shells out to `claude -p` CLI with OAuth credentials
- No API key needed — uses local Claude Code subscription
- Replaces the dead `DISCORD_BOT_CLAUDE_KEY` that was silently returning None

### Retrieval: Hybrid Search

```
Query -> Embed (gte-small)
           |
           v
   Semantic Search (pgvector cosine similarity)
           +
   Keyword Search (full-text)
           |
           v
   Rank by: similarity x decay_score x base_priority
           |
           v
   Top-N items injected into Peterbot context
```

### Decay Model

- Items lose relevance over time (half-life: 90 days)
- Accessed items get boosted (log2(access_count+1) multiplier)
- Priority: Explicit (1.0) > Seed (0.8) > Passive (0.3)

---

## 4. Seed Adapters (14 Data Sources)

Daily import at 1am UK via `incremental_seed.py`. Each adapter fetches from an external source and produces `SeedItem` objects that flow through the pipeline.

| # | Adapter | Source | What it imports |
|---|---------|--------|----------------|
| 1 | **Calendar** | Google Calendar API | Events from Chris, Abby, Family calendars |
| 2 | **Email** | Gmail (via Hadley API) | Important emails (travel, purchases, financial, health, school) |
| 3 | **GitHub** | GitHub API | Commits, repos, project activity |
| 4 | **Garmin** | Garmin Connect (garth) | Runs, swims, cycling — distance, pace, HR |
| 5 | **Bookmarks** | Chrome Bookmarks JSON | Browser bookmarks (live file, dedup handles repeats) |
| 6 | **Email Links** | Gmail + Playwright | Scraped content from email links (Gousto recipes, Airbnb) |
| 7 | **Hadley Bricks Email** | Gmail (business) | Orders, shipping, inquiries for the LEGO business |
| 8 | **Finance Summary** | Supabase (local) | Monthly P&L, savings rate, net worth snapshot |
| 9 | **Recipes** | Family Fuel app | Cooking recipes (low volume, full sync) |
| 10 | **Spotify** | Spotify API | Recently played + monthly top tracks |
| 11 | **Netflix** | Netflix cookies/CSV | Viewing history |
| 12 | **Travel** | Gmail + JSON-LD | Flight, hotel, train bookings + check-in instructions |
| 13 | **Claude History** | Claude Desktop | Past Claude conversation summaries |
| 14 | **Scrapers** | Email link sub-scrapers | Gousto recipe pages, Airbnb booking details |

### Travel Adapter (Newest — March 2026)

Supports 9 providers: BA, Airbnb, Booking.com, Trainline, Premier Inn, easyJet, Ryanair, Beeksebergen, Lalandia.

- Extracts Schema.org JSON-LD from confirmation emails (flights, hotels, trains)
- Falls back to Claude CLI parsing for rich details
- Separate check-in instruction email detection
- Ticket attachment detection (PDF, pkpass)

---

## 5. Scheduled Jobs

30+ jobs run on APScheduler, defined in `SCHEDULE.md`. Each invokes a skill via Claude Code.

### Daily Schedule (UK Time)

| Time | Job | Channel | Description |
|------|-----|---------|-------------|
| 06:30 | Morning Laughs | #peterbot | Dad jokes to start the day |
| 06:45 | Quality Report | #peter-heartbeat | System health check |
| 07:00 | Morning Briefing | #ai-briefings | AI news (Grok search + Claude curation) |
| 07:02 | News | #news | General news digest |
| 07:55 | Health Digest | #food-log | Weight, sleep, HR, goals |
| 08:00 | Nutrition Morning | #food-log | PT-style motivation + yesterday's macros |
| 08:10 | School Run | #traffic-reports | Traffic + route (Mon-Wed, Fri) |
| hourly | Hydration | #food-log | Water + steps progress with AI coaching |
| 14:55 | School Pickup | #traffic-reports | Afternoon traffic (Mon, Tue, Thu, Fri) |
| 21:00 | Nutrition Summary | #food-log | Daily macro totals |
| **01:00** | **Seed Import** | **#alerts** | **14 adapters import to Second Brain** |

### Weekly/Monthly

| Schedule | Job | Description |
|----------|-----|-------------|
| Sunday 09:10 | Weekly Health | Weight trend, nutrition avg, steps, sleep, PT grade |
| 1st of month 09:00 | Monthly Health | 30-day review with graphs |

---

## 6. Infrastructure

### Hadley API (FastAPI, port 8100)

Local Windows service (NSSM) providing:

| Route Group | Endpoints | Used By |
|-------------|-----------|---------|
| `/claude/extract` | POST — Claude CLI extraction | Second Brain pipeline, travel adapter |
| `/gmail/*` | unread, send, search, get (with html flag) | Email adapters, travel adapter |
| `/calendar/*` | today, upcoming, create | Calendar adapter, scheduler |
| `/places/*` | search, nearby, details, autocomplete | Travel planning |
| `/directions/*` | route, matrix | Travel logistics |
| `/weather/*` | forecast | Daily planning |
| `/currency` | conversion | Travel budgeting |
| `/translate` | text translation | Travel |

### MCP Servers

Two Model Context Protocol servers provide tool access to Claude:

**second-brain** — 6 tools:
- `search_knowledge` — Semantic + keyword search
- `save_to_brain` — Save URL or text
- `get_recent_items` — Recent captures
- `browse_topics` — All topic tags
- `get_item_detail` — Full item with connections
- `list_items` — Paginated browse

**financial-data** — 9 tools:
- `get_net_worth`, `get_budget_status`, `get_spending_by_category`
- `get_savings_rate`, `get_fire_status`, `find_recurring_transactions`
- `get_business_pnl`, `get_platform_revenue`, `get_financial_health`

### Provider Cascade

```
claude_cc (primary ~/.claude)
    |--- credit exhaustion? --->  claude_cc2 (secondary ~/.claude-secondary)
                                      |--- credit exhaustion? --->  kimi (Moonshot API)
```

- Auto-failover with keyword detection (60+ exhaustion signals)
- State persisted in `data/model_config.json`
- Failover history tracked for diagnostics

---

## 7. Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Claude CLI (`claude -p`) over API | Uses OAuth subscription, no API key cost. Reliable, same model. |
| Supabase + pgvector over local ChromaDB | Cloud-hosted, persistent, supports hybrid search. |
| HuggingFace gte-small (384d) for embeddings | Free, fast, good quality for personal knowledge. |
| Per-channel buffers over shared history | Prevents context bleeding between topics. |
| Fire-and-forget memory capture | Never blocks response delivery. |
| NDJSON streaming over batch response | Real-time tool use updates, better timeout handling. |
| Daily seed import (1am) with dedup | Incremental, handles repeats, doesn't duplicate. |
| Hadley API for all external services | Single gateway, consistent auth, easy to extend. |

---

## 8. Data Volumes (Approximate)

| Data Source | Items/Month | Storage |
|-------------|------------|---------|
| Gmail emails | ~200 | Supabase |
| Calendar events | ~50 | Supabase |
| Garmin activities | ~30 | Supabase |
| Chrome bookmarks | ~50 | Supabase |
| Spotify tracks | ~50 | Supabase |
| Netflix viewing | ~100 | Supabase |
| Travel bookings | ~10 | Supabase |
| Discord conversations | ~500+ | Supabase + SQLite |
| Scheduled job outputs | ~900+ | Discord + Supabase |

---

## Changelog

- **March 2026**: Fixed silent Claude API failure — all AI processing now routes through `/claude/extract` (Claude CLI). Travel adapter added with 9 providers.
- **February 2026**: Router V2 (NDJSON streaming), provider cascade, Spotify/Netflix/Recipes adapters.
- **January 2026**: Second Brain launch, seed adapters (Calendar, Email, GitHub, Garmin, Bookmarks), MCP servers.
