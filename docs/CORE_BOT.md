# Core Bot System

Comprehensive documentation for the Discord Messenger core bot — the main runtime that powers Peter, the Hadley family's AI personal assistant. This document covers the entry point, message routing, job scheduling, memory system, response pipeline, and data fetching.

For high-level architecture (channel sessions, service topology, symlink strategy), see [ARCHITECTURE.md](./ARCHITECTURE.md).

---

## 1. System Overview

Peterbot is an AI personal assistant named "Peter" running as a Discord bot on Windows, with Claude Code executing in WSL2. The bot serves the Hadley family — managing schedules, health tracking, LEGO business automation, and family coordination across Discord and WhatsApp.

### Runtime Components

```
+------------------+     +-------------------+     +------------------+
| bot.py           |     | router_v2.py      |     | Claude Code      |
| (Windows/NSSM)   |---->| (CLI subprocess)  |---->| (WSL2)           |
|                  |     |                   |     |                  |
| - Discord events |     | - Context builder |     | - CLAUDE.md      |
| - APScheduler    |     | - NDJSON parser   |     | - MCP servers    |
| - WhatsApp HTTP  |     | - Provider cascade|     | - Skills         |
| - Channel launch |     | - Cost logging    |     | - File access    |
+------------------+     +-------------------+     +------------------+
        |                         |
        v                         v
+------------------+     +-------------------+
| scheduler.py     |     | response/         |
| (SCHEDULE.md)    |     | pipeline.py       |
|                  |     |                   |
| - Cron/interval  |     | 1. Sanitiser      |
| - Data fetchers  |     | 2. Classifier     |
| - Quiet hours    |     | 3. Formatter      |
| - Job history    |     | 4. Chunker        |
+------------------+     | 5. Renderer       |
                          +-------------------+
```

---

## 2. Entry Point: bot.py

Main Discord bot process, registered as the `DiscordBot` NSSM service on Windows.

### Responsibilities

| Area | Detail |
|------|--------|
| **Event Handling** | `on_ready`, `on_message` — core Discord gateway events |
| **Domain Registration** | Peterbot, News, API Usage, Claude Code — each domain handles its own channel IDs |
| **Scheduler** | APScheduler integration for all scheduled jobs (skill-based via SCHEDULE.md) |
| **Channel Auto-Launch** | Starts `peter-channel`, `whatsapp-channel`, `jobs-channel` tmux sessions in WSL on boot |
| **Second Brain Capture** | Passive capture of messages for knowledge base ingestion |
| **Message Deduplication** | Guards against processing the same Discord message twice (reconnect race conditions) |
| **WhatsApp Receiver** | Internal HTTP server on port 8101 receiving forwarded WhatsApp messages from Hadley API |
| **Orphan Cleanup** | `_kill_orphaned_bots()` kills stale bot.py processes left by NSSM restarts |
| **Ready Guard** | `_ready_initialized` flag prevents duplicate scheduler registration when Discord reconnects |

### Startup Sequence

```
1. bot.py main()
   |
   +-- _kill_orphaned_bots()          # Kill stale processes from previous NSSM restarts
   |
   +-- Load .env configuration
   |
   +-- Register domains (Peterbot, News, API Usage, Claude Code)
   |
   +-- on_ready()  [guarded by _ready_initialized]
       |
       +-- Parse SCHEDULE.md → register APScheduler jobs
       |
       +-- Launch channel sessions (peter-channel, whatsapp-channel, jobs-channel)
       |
       +-- Start WhatsApp HTTP listener (port 8101)
       |
       +-- Register legacy infrastructure jobs (energy_sync, school_sync, etc.)
       |
       +-- Log startup complete
```

### Message Routing

When a Discord message arrives in a Peterbot channel:

```python
on_message(message):
    # 1. Deduplication check
    # 2. Ignore bots (except whitelisted webhooks)
    # 3. Route by channel ID to appropriate domain
    # 4. For Peterbot: try channel first, fall back to router_v2
```

The channel architecture (peter-channel MCP server) is the primary path. When the channel session is down, messages fall back to `router_v2.py` which spawns a one-shot `claude -p` process.

---

## 3. Message Router: router_v2.py

The active message router. Spawns `claude -p --output-format stream-json` as an independent WSL subprocess for each conversation turn.

### Message Flow

```
1. handle_message(message, channel, bot)
   |
   +-- Add message to per-channel buffer (memory.py)
   |
   +-- Download Discord attachments to data/tmp/attachments/
   |
   +-- Build full context:
   |   - Memory buffer (last 20 messages)
   |   - Second Brain knowledge (semantic search)
   |   - Current message + attachment metadata
   |
   +-- Invoke Claude CLI:
   |   wsl bash -c "cd ~/peterbot && claude -p \
   |     --output-format stream-json \
   |     --verbose \
   |     --model claude-opus-4-6 \
   |     --max-turns 80 \
   |     --permission-mode bypassPermissions \
   |     --no-session-persistence"
   |
   +-- Parse NDJSON stream:
   |   - "system/init"  → MCP servers connected
   |   - "assistant" tool_use → post interim update ("Searching...", "Reading...")
   |   - "result" → extract final response text
   |
   +-- Process through 5-stage response pipeline
   |
   +-- Capture conversation pair to Second Brain (async)
   |
   +-- Return formatted response
```

### Provider Cascade

When the primary Claude subscription runs out of credits, the router cascades through alternative providers:

```
claude_cc  →  claude_cc2  →  kimi (Moonshot AI)
 (primary)    (backup CC)    (api.moonshot.ai/v1, model kimi-k2.5)
```

Credit exhaustion is detected via the `__CREDIT_EXHAUSTED__` sentinel string in CLI output.

### Loop Detection

The router tracks repeated tool+context combinations. If the same tool call appears with the same context more than 10 times, the conversation is aborted to prevent infinite loops.

### Tool Activity Tracking

During streaming, the router maps tool calls to emoji indicators posted as interim Discord updates:

| Emoji | Tool |
|-------|------|
| :page_facing_up: | Read file |
| :pencil2: | Edit file |
| :memo: | Write file |
| :mag: | Search / Grep |
| :globe_with_meridians: | Web search |
| :computer: | Bash command |
| :package: | MCP tool call |

### Cost Logging

Every CLI invocation logs cost data to `data/cli_costs.jsonl`:

```json
{"timestamp": "2026-03-27T09:15:00Z", "model": "claude-opus-4-6", "usd": 0.042, "gbp": 0.033, "turns": 3, "skill": null}
```

### CLI Configuration Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `CLI_TOTAL_TIMEOUT` | 20 minutes | Maximum wall-clock time per conversation |
| `CLI_MAX_TURNS` | 80 | Agentic turn limit for interactive conversations |
| `CLI_SCHEDULED_MAX_TURNS` | 50 | Turn limit for scheduled jobs |
| `CLI_MODEL` | `claude-opus-4-6` | Model used for all CLI invocations |
| `CLI_WORKING_DIR` | `~/peterbot` | WSL working directory (loads CLAUDE.md automatically) |

### Attachment Handling

Discord attachments are downloaded to `data/tmp/attachments/` on Windows, then converted to WSL paths (`/mnt/c/...`) before being passed to Claude CLI. Images are handled natively by Claude's multimodal capabilities.

---

## 4. Job Scheduler: scheduler.py

Parses `SCHEDULE.md` markdown tables and registers jobs with APScheduler. This is the brain of Peter's proactive behaviour — everything from morning briefings to hydration reminders.

### SCHEDULE.md Format

```markdown
## Fixed Time Jobs

| Job | Skill | Schedule | Channel | Enabled |
|-----|-------|----------|---------|---------|
| Morning Briefing | morning-briefing | 07:00 UK | #peterbot | yes |
| Hydration | hydration | 09:02,11:02,13:02,15:02,17:02 UK | #food-log | yes |
| Health Digest | health-digest | 21:30 UK | #health+WhatsApp | yes |

## Interval Jobs

| Job | Skill | Schedule | Channel | Enabled |
|-----|-------|----------|---------|---------|
| System Health | system-health | 30m | #alerts | yes |
```

### Schedule Syntax

| Pattern | Example | Meaning |
|---------|---------|---------|
| `HH:MM UK` | `07:00 UK` | Daily at 07:00 UK time |
| `HH:MM,HH:MM UK` | `09:02,11:02 UK` | Multiple times daily |
| `Day HH:MM` | `Sun 09:00` | Weekly on specific day |
| `1st HH:MM` | `1st 09:00` | Monthly on 1st |
| `hourly+N` | `hourly+3` | Every hour at :03 past |
| `half-hourly` | `half-hourly` | Every 30 minutes |
| `Nm` | `30m` | Interval: every N minutes |
| `Nh` | `2h` | Interval: every N hours |

### Channel Modifiers

| Modifier | Example | Effect |
|----------|---------|--------|
| `+WhatsApp` | `#health+WhatsApp` | Also send to WhatsApp (default contact) |
| `+WhatsApp:chris` | `#health+WhatsApp:chris` | Send to Chris's WhatsApp |
| `+WhatsApp:group` | `#health+WhatsApp:group` | Send to family group |
| `!quiet` | `#alerts!quiet` | Exempt from quiet hours |

### Execution Flow

```
1. APScheduler triggers _execute_job(job_config)
   |
   +-- Check quiet hours (23:00 - 06:00 UK)
   |   └── Skip unless channel has !quiet suffix
   |
   +-- Check pause system (data/schedule_pauses.json)
   |   └── Skip if skill is paused (cached 60s)
   |
   +-- Check overlap (is this skill already running?)
   |   └── Queue if busy
   |
   +-- Pre-fetch data via SKILL_DATA_FETCHERS (if registered)
   |   └── e.g. get_hydration_data(), get_health_digest_data()
   |
   +-- Load SKILL.md from skills/<name>/SKILL.md
   |
   +-- Build skill context:
   |   - Current date/time
   |   - SKILL.md instructions
   |   - Pre-fetched data (JSON)
   |   - "ONLY output the formatted response"
   |
   +-- Route to execution backend:
   |   - Channel (jobs-channel :8103) — preferred
   |   - CLI fallback (claude -p) — if channel is down
   |
   +-- Validate response:
   |   - NO_REPLY check → suppress output silently
   |   - Reasoning leak detection → strip preamble
   |
   +-- Post to Discord channel
   |   └── Process through response pipeline
   |
   +-- Optional: send to WhatsApp (if +WhatsApp modifier)
   |
   +-- Record in job_history.db
   |
   +-- Auto-save to Second Brain (if skill in SECOND_BRAIN_SAVE_SKILLS list)
```

### Pause System

Skills can be paused without editing SCHEDULE.md:

```json
// data/schedule_pauses.json
{
  "hydration": {"paused_at": "2026-03-27T10:00:00Z", "reason": "Testing"},
  "morning-briefing": {"paused_at": "2026-03-27T08:00:00Z", "reason": "On holiday"}
}
```

Pause state is cached for 60 seconds to avoid file I/O on every job trigger.

### News Deduplication

News-related skills track previously sent items in `data/news_history.jsonl` with a 7-day rolling window, preventing duplicate stories across runs.

### Schedule Reload

Two mechanisms for live reload without restarting the bot:

1. **API trigger**: `POST /schedule/reload` on Hadley API writes `data/schedule_reload.trigger`
2. **File watcher**: Scheduler checks for trigger file every 10 seconds, re-parses SCHEDULE.md

Manual skill execution is also supported via `data/skill_run.trigger`.

---

## 5. Data Fetchers: data_fetchers.py

Pre-computes data in parallel before Claude Code processes a skill. This ensures the AI has structured, fresh data without needing to make API calls itself (which would be slower and less reliable).

### Registered Fetchers

| Fetcher Function | Skill(s) | Data Sources |
|------------------|-----------|--------------|
| `get_nutrition_data()` | nutrition-summary | Hadley API (daily totals, steps, targets) |
| `get_hydration_data()` | hydration | Hadley API (water intake, steps, percentages) |
| `get_health_digest_data()` | health-digest | Garmin (sleep, steps, HR), Withings (weight), nutrition |
| `get_weekly_health_data()` | weekly-health | Week's metrics vs targets, trend analysis |
| `get_monthly_health_data()` | monthly-health | Month's metrics vs targets + previous month comparison |
| `get_balance_data()` | balance-monitor | Claude, Moonshot, Grok API balances + GCP costs |
| `get_youtube_data()` | youtube-digest | YouTube videos by category (deduped via Supabase) |
| `get_school_run_data()` | school-run | Traffic, weather, uniforms, school events |

### Registration

```python
# data_fetchers.py
SKILL_DATA_FETCHERS = {
    "nutrition-summary": get_nutrition_data,
    "hydration": get_hydration_data,
    "health-digest": get_health_digest_data,
    "weekly-health": get_weekly_health_data,
    "monthly-health": get_monthly_health_data,
    "balance-monitor": get_balance_data,
    "youtube-digest": get_youtube_data,
    "school-run": get_school_run_data,
}
```

### Garmin Sync

`_sync_garmin_to_supabase()` is called by health-related fetchers to ensure Supabase has fresh Garmin data (steps, sleep, heart rate) before the skill runs. This bridges the gap between Garmin's API and the Supabase-based data layer.

### Design Rationale

- **Speed**: Data is ready when Claude Code starts — no waiting for API calls
- **Parallelism**: Multiple data sources fetched concurrently via `asyncio.gather`
- **Error isolation**: Partial failures return what's available; skills degrade gracefully
- **Retry independence**: Fetchers can retry API calls without affecting Claude's turn budget

---

## 6. Memory System: memory.py

Per-channel conversation buffers and context building for Claude Code invocations.

### Buffer Management

Each Discord channel maintains a rolling buffer of the last 20 messages. Messages are stored as `(role, content, timestamp)` tuples.

```python
# Simplified buffer structure
channel_buffers = {
    1234567890: [  # channel ID
        ("user", "What's for dinner?", "2026-03-27T18:00:00Z"),
        ("assistant", "Based on your meal plan...", "2026-03-27T18:00:05Z"),
        # ... up to 20 messages
    ]
}
```

### Context Building: build_full_context()

Assembles the full prompt sent to Claude Code for each conversation turn:

```
+-------------------------------------------------------+
| 1. Channel Isolation Header                           |
|    "You are responding in #peterbot"                  |
+-------------------------------------------------------+
| 2. Current Date/Time                                  |
|    "Current time: Thu 27 Mar 2026, 18:00 UK"         |
+-------------------------------------------------------+
| 3. Japan Trip Context (WhatsApp only, Apr 3-19 2026) |
|    Trip dates, itinerary highlights, key info         |
+-------------------------------------------------------+
| 4. Pending Actions (WhatsApp confirmations)           |
|    Unacknowledged requests awaiting response          |
+-------------------------------------------------------+
| 5. Knowledge Context (Second Brain semantic search)   |
|    Top-k relevant memories matching the message       |
+-------------------------------------------------------+
| 6. Recent Conversation Buffer (last 20 messages)      |
|    Full conversation history for this channel         |
+-------------------------------------------------------+
| 7. Current Message + Attachment Metadata              |
|    The actual user message being responded to         |
+-------------------------------------------------------+
```

### Second Brain Integration

On each message, `build_full_context()` performs a semantic search against the Second Brain knowledge base, retrieving relevant memories, saved articles, and past conversations. This gives Peter contextual awareness of things the family has discussed before.

### Conversation Capture

After every successful response, `capture_message_pair()` saves the user+assistant exchange to the Second Brain:

```python
capture_message_pair(
    user_message="What's for dinner?",
    assistant_response="Based on your meal plan, tonight is...",
    session_id="discord-1234567890",  # or "scheduled-health-digest"
    channel_name="#peterbot"
)
```

**Failure resilience**: If the Second Brain is unreachable, the capture is queued locally in `data/captures.db` for retry later (via the reprocess pending items job).

---

## 7. Response Pipeline: response/pipeline.py

A 5-stage pipeline that transforms raw Claude Code output into properly formatted Discord messages.

### Pipeline Stages

```
Raw Claude Output
       |
       v
+------------------+
| 1. SANITISER     |  Strip Claude Code artifacts: tool markers (⏺),
|    sanitiser.py  |  token counts, ANSI escape codes, spinner chars,
|                  |  orphaned search fragments
+------------------+  (SKIPPED when pre_sanitised=True — v2 JSON output is clean)
       |
       v
+------------------+
| 2. CLASSIFIER    |  Detect response type based on content patterns:
|    classifier.py |  headers, code blocks, tables, bullet lists,
|                  |  nutrition data, error messages, etc.
+------------------+
       |
       v
+------------------+
| 3. FORMATTER     |  Apply Discord-native formatting:
|    formatters/   |  bold headers, code blocks, embeds,
|                  |  reaction suggestions, markdown cleanup
+------------------+
       |
       v
+------------------+
| 4. CHUNKER       |  Split into Discord-safe segments:
|    chunker.py    |  <2000 chars per message, respect code block
|                  |  boundaries, preserve table integrity
+------------------+
       |
       v
+------------------+
| 5. RENDERER      |  Produce final Discord message dict:
|    pipeline.py   |  {content, chunks[], embeds[], reactions[]}
+------------------+
       |
       v
  Discord channel.send()
```

### Response Types

The classifier assigns one of these types, which determines which formatter is used:

| Type | Trigger Patterns | Formatter |
|------|-----------------|-----------|
| `CONVERSATIONAL` | Default — casual chat, Q&A | `conversational.py` |
| `CODE` | Code blocks, technical content | `code.py` |
| `DATA_TABLE` | Markdown tables, structured data | `table.py` |
| `SEARCH_RESULTS` | Web search output | `search.py` |
| `NEWS_RESULTS` | News articles, headlines | `search.py` |
| `LIST` | Bullet/numbered lists | `list.py` |
| `SCHEDULE` | Calendar, schedule output | `schedule.py` |
| `ERROR` | Error messages, failures | `error.py` |
| `NUTRITION_SUMMARY` | Daily nutrition totals | `nutrition.py` |
| `NUTRITION_LOG` | Food logging confirmation | `nutrition.py` |
| `WATER_LOG` | Hydration logging | `nutrition.py` |
| `PROACTIVE` | Scheduled skill output | `proactive.py` |
| `MIXED` | Multiple types in one response | Splits and delegates |

### Raw Bypass

The `--raw` flag (set in message or by skills) returns content wrapped in a code block, skipping sanitisation entirely. Useful for debugging or technical output.

### Formatter Files

```
response/formatters/
├── conversational.py    # Casual chat — light formatting, emoji support
├── code.py              # Code blocks — syntax highlighting, file paths
├── error.py             # Errors — red formatting, troubleshooting hints
├── list.py              # Lists — bullet cleanup, indentation
├── nutrition.py         # Nutrition — tables, progress bars, targets
├── proactive.py         # Scheduled output — headers, sections
├── schedule.py          # Calendar — time formatting, event layout
├── search.py            # Search results — links, snippets, sources
└── table.py             # Tables — alignment, Discord-safe rendering
```

---

## 8. Configuration

### Global Configuration: config.py

Root-level configuration file containing all API credentials and system constants.

| Category | Keys |
|----------|------|
| **Discord** | `DISCORD_TOKEN`, channel IDs, webhook URLs |
| **Claude** | Model defaults, subscription config |
| **Supabase** | `SUPABASE_URL`, `SUPABASE_KEY` (Second Brain) |
| **Health** | Garmin, Withings credentials |
| **AI APIs** | OpenAI, xAI (Grok) keys |
| **Google** | Maps, Calendar, Gmail OAuth |
| **WhatsApp** | Evolution API config, phone numbers |

### Peterbot Configuration: domains/peterbot/config.py

Domain-specific configuration for the Peterbot subsystem.

| Setting | Value | Purpose |
|---------|-------|---------|
| **CLAUDE_MODEL** | `claude-sonnet-4-20250514` | Default model (overridden by CLI_MODEL for router) |
| **Provider Priority** | `claude_cc` > `claude_cc2` > `kimi` | Cascade on credit exhaustion |
| **Kimi Fallback** | `api.moonshot.ai/v1`, model `kimi-k2.5` | Last-resort provider (4096 tokens, 120s timeout) |
| **SECOND_BRAIN_SAVE_SKILLS** | See list below | Skills whose output is auto-saved to knowledge base |
| **DOCUMENT_MIN_LENGTH** | 800 chars | Minimum length for document-type responses |
| **DOCUMENT_MIN_HEADERS** | 2 | Minimum header count for document classification |

**Auto-saved skills** (output persisted to Second Brain):

- `daily-recipes`
- `health-digest`
- `nutrition-summary`
- `weekly-health`
- `morning-briefing`
- `news`
- `youtube-digest`
- `knowledge-digest`

---

## 9. Data Stores

| Database | Path | Purpose |
|----------|------|---------|
| `job_history.db` | `peter_dashboard/` | Job execution history — start time, status, duration, output |
| `parser_fixtures.db` | `data/` | Parser captures and fixtures (v1 tmux router only) |
| `captures.db` | `data/` | Second Brain pending captures — queued when Supabase is unreachable |
| `knowledge_items` | Supabase (cloud) | Second Brain — memories, articles, notes (pgvector embeddings) |
| `cli_costs.jsonl` | `data/` | Per-invocation cost log (USD + GBP) |
| `news_history.jsonl` | `data/` | News deduplication — 7-day rolling window |
| `schedule_pauses.json` | `data/` | Paused skills with reason and timestamp |

---

## 10. File Structure

```
bot.py                                  # Main entry point (NSSM service)
config.py                               # Global configuration (API keys, channels)
domains/peterbot/
├── router_v2.py                        # [ACTIVE] CLI --print mode routing
├── router.py                           # [FALLBACK] Legacy tmux screen-scraping router
├── scheduler.py                        # APScheduler + SCHEDULE.md parser
├── data_fetchers.py                    # Pre-fetch data for skills
├── memory.py                           # Conversation buffers + context builder
├── config.py                           # Peterbot-specific config
├── parser.py                           # Legacy response parser (v1 only)
├── capture_parser.py                   # Parser capture store (v1 only)
├── japan_alerts.py                     # Japan trip alerting (Apr 2026)
├── japan_context.py                    # Japan trip context injection
├── reminders/                          # Reminder subsystem
│   ├── executor.py                     #   Execute triggered reminders
│   ├── handler.py                      #   Process reminder commands
│   ├── parser.py                       #   Parse natural language time expressions
│   ├── scheduler.py                    #   APScheduler integration for reminders
│   └── store.py                        #   Persistent reminder storage
├── response/                           # 5-stage response pipeline
│   ├── pipeline.py                     #   Pipeline orchestrator + renderer
│   ├── classifier.py                   #   Response type detection
│   ├── sanitiser.py                    #   Claude Code artifact stripping
│   ├── chunker.py                      #   Discord message size splitting
│   └── formatters/                     #   Type-specific formatters
│       ├── conversational.py
│       ├── code.py
│       ├── error.py
│       ├── list.py
│       ├── nutrition.py
│       ├── proactive.py
│       ├── schedule.py
│       ├── search.py
│       └── table.py
└── wsl_config/                         # Symlinked to ~/peterbot in WSL
    ├── CLAUDE.md                       # Peter's instructions + governance
    ├── PETERBOT_SOUL.md                # Personality and tone definition
    ├── SCHEDULE.md                     # Scheduled job definitions
    ├── MEMORY.md                       # Memory system guide
    └── skills/                         # ~106 skill definitions (SKILL.md each)
```

---

## 11. Key Patterns and Conventions

### Async Architecture

The bot runs on Python's `asyncio` event loop (via discord.py). Blocking synchronous operations (file I/O, subprocess calls, HTTP requests) are wrapped with `asyncio.to_thread()`:

```python
result = await asyncio.to_thread(blocking_function, arg1, arg2)
```

### Graceful Degradation

Every external dependency has a fallback path:

| Dependency | Fallback |
|------------|----------|
| Channel sessions | Router v2 (claude -p) |
| Claude CC subscription | claude_cc2, then Kimi |
| Second Brain (Supabase) | Queue locally in captures.db |
| Data fetchers | Skill runs with empty/partial data |
| Hadley API | Direct API calls where possible |

### Message Deduplication

Discord.py can deliver `on_message` multiple times during reconnects. The bot maintains a set of recently processed message IDs to prevent duplicate processing.

### Orphan Process Cleanup

NSSM restarts can leave orphaned `bot.py` processes, each with its own APScheduler — causing jobs to execute 2-3x. On startup, `_kill_orphaned_bots()` identifies and terminates stale processes by checking parent process IDs.

### Context File Strategy

- **Router v2**: Context is piped via stdin to `claude -p`. No temp files.
- **Router v1** (legacy): Context written to `~/peterbot/context.md`, guarded by `_session_lock`.
- **Scheduled jobs**: Skill context assembled in-memory, passed via stdin (v2) or temp file (v1).

---

## 12. Cross-References

| Topic | Document |
|-------|----------|
| System architecture, channel sessions, symlinks | [ARCHITECTURE.md](./ARCHITECTURE.md) |
| Peter's personality and communication style | `domains/peterbot/wsl_config/PETERBOT_SOUL.md` |
| Peter's instructions and governance rules | `domains/peterbot/wsl_config/CLAUDE.md` |
| Scheduled job definitions | `domains/peterbot/wsl_config/SCHEDULE.md` |
| Memory system reference | `domains/peterbot/wsl_config/MEMORY.md` |
| Hadley API endpoints | `hadley_api/README.md` |
| Dashboard monitoring | `peter_dashboard/` |
| Skill creation guide | [ARCHITECTURE.md, Section 7](./ARCHITECTURE.md#7-creating-a-new-skill) |

---

*Last updated: 2026-03-27*
