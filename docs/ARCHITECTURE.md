# Discord-Messenger Architecture

This document provides a comprehensive overview of the Peterbot system architecture, covering component interactions, file locations, and operational patterns.

---

## 1. System Overview

Peterbot is an AI-powered personal assistant running as a Discord bot on Windows, with Claude Code executing in WSL2.

### Router V2 (Active Default — Feb 2026)

Uses `claude -p --output-format stream-json --verbose` — each message spawns an independent CLI process. No tmux, no session lock, no screen-scraping.

```
+------------------+      +------------------+      +------------------+
|   Discord API    | <--> |  Discord Bot     | <--> |  Hadley API      |
|                  |      |  (Windows)       |      |  (Windows:8100)  |
+------------------+      +--------+---------+      +------------------+
                                   |
                                   | WSL subprocess (per-request)
                                   v
                         +------------------+
                         |  claude -p       |
                         |  --stream-json   |
                         |  (WSL2)          |
                         +--------+---------+
                                  |
                                  v
                         +------------------+
                         |  Claude Code     |
                         |  (AI/LLM)        |
                         +------------------+
```

### Router V1 (Legacy Fallback)

Uses persistent tmux session with screen-scraping. Revert by setting `PETERBOT_ROUTER_V2=0`.
Old files (router.py, parser.py, sanitiser.py) are kept in-tree for this fallback.

```
Discord Bot → tmux session (claude-peterbot) → screen capture → parser.py → sanitiser.py
```

### Services Running

| Service | Port | Platform | Description |
|---------|------|----------|-------------|
| Discord Bot | - | Windows | Main bot process, message routing |
| Hadley API | 8100 | Windows | FastAPI proxy for Gmail, Calendar, Notion |
| Peter Dashboard | 5000 | Windows | Flask web UI for monitoring |
| Memory Worker | 37777 | Windows | claude-mem persistent memory |
| Claude Code | - | WSL2 CLI | AI responses via `claude -p` (v2) or tmux (v1 fallback) |
| Hadley Bricks | 3000 | (External) | LEGO inventory management API |

---

## 2. Code Locations (Critical - Local vs WSL)

### Primary Mapping

| Component | Windows Path | WSL Path | Notes |
|-----------|--------------|----------|-------|
| Bot code | `C:\Users\Chris Hadley\Discord-Messenger\` | N/A | Runs on Windows |
| Peterbot config | `domains\peterbot\wsl_config\` | `/home/chris_hadley/peterbot/` | Symlinked to Windows |
| Claude Code (v2) | N/A | `claude -p` per-request | Independent process, no session |
| Claude Code (v1) | N/A | tmux session `claude-peterbot` | Legacy fallback only |
| Hadley API | `hadley_api/` | N/A | FastAPI on Windows |
| Dashboard | `peter_dashboard/` | N/A | FastAPI on Windows |
| Skills | `domains\peterbot\wsl_config\skills\` | `~/peterbot/skills/` | Via symlink |

### Directory Structure

```
Discord-Messenger/
|-- bot.py                      # Main Discord bot entry point
|-- config.py                   # Global configuration (API keys, channels)
|-- domains/
|   |-- peterbot/
|   |   |-- router_v2.py        # [ACTIVE] CLI --print mode routing (no tmux)
|   |   |-- router.py           # [FALLBACK] Legacy tmux screen-scraping router
|   |   |-- scheduler.py        # APScheduler job management (uses v2 or v1)
|   |   |-- data_fetchers.py    # Pre-fetch data for skills
|   |   |-- memory.py           # Memory context injection
|   |   |-- config.py           # Peterbot-specific config + USE_ROUTER_V2 flag
|   |   |-- parser.py           # [FALLBACK] Response extraction from tmux
|   |   |-- response/           # Response pipeline (sanitize, format, chunk)
|   |   |-- reminders/          # One-off reminder handling
|   |   `-- wsl_config/         # <-- SYMLINKED TO WSL
|   |       |-- CLAUDE.md       # Peter's main instructions
|   |       |-- PETERBOT_SOUL.md # Personality/tone
|   |       |-- SCHEDULE.md     # Scheduled job definitions
|   |       |-- MEMORY.md       # Memory system reference
|   |       |-- skills/         # Skill definitions (SKILL.md files)
|   |       `-- context.md      # Runtime context file (written per-request)
|   |-- claude_code/            # Direct Claude Code tunnel (dumb pipe)
|   `-- nutrition/              # Nutrition tracking (data services)
|-- hadley_api/
|   |-- main.py                 # FastAPI app (Gmail, Calendar, Notion, etc.)
|   |-- google_auth.py          # OAuth handling for Google APIs
|   `-- notion_client.py        # Notion API wrapper
|-- peter_dashboard/
|   |-- app.py                  # FastAPI dashboard
|   `-- service_manager.py      # Process control
|-- jobs/                       # Legacy job functions (being migrated to skills)
|   |-- balance_monitor.py
|   |-- morning_briefing.py
|   |-- weekly_health.py
|   `-- ...
`-- docs/
    |-- playbooks/              # Response format guides
    `-- ARCHITECTURE.md         # This file
```

---

## 3. Message Flow (Conversation)

### V2 Flow (Active Default)

Uses `claude -p --output-format stream-json`. No session lock, no tmux, no screen-scraping.

```
1. Discord Message
       |
       v
2. bot.py on_message()
   - Deduplication check
   - Channel routing (PETERBOT_CHANNEL_IDS)
       |
       v
3. peterbot/router_v2.py handle_message()
   - Add message to per-channel buffer
   - Fetch memory context (async, graceful degradation)
   - Fetch Second Brain knowledge (async)
   - Build full context string
       |
       v
4. Spawn: wsl bash -c "cd ~/peterbot && claude -p --output-format stream-json ..."
   - Context piped via stdin (no temp file)
   - CLAUDE.md loaded automatically (working dir ~/peterbot)
       |
       v
5. Stream NDJSON events from stdout
   - "system/init" → MCP servers connected
   - "assistant" with tool_use → post interim "🔍 Searching..."
   - "result" → extract clean result text
       |
       v
6. Response Pipeline (response/pipeline.py)
   - Sanitise: SKIPPED (pre_sanitised=True, JSON output is clean)
   - Classify (report/alert/chat/etc.)
   - Format (Discord markdown)
   - Chunk (2000 char limit)
       |
       v
7. Post to Discord channel
       |
       v
8. Memory capture (async, fire-and-forget)
```

### Key Differences from V1

| Aspect | V2 (Active) | V1 (Fallback) |
|--------|-------------|---------------|
| Execution | Independent process per request | Shared tmux session |
| Concurrency | Unlimited parallel requests | Session lock, one at a time |
| Response capture | JSON `result` field | Screen diff + 50+ regex parser |
| Sanitisation | Skipped (clean output) | Required (CC artifacts in screen) |
| Interim updates | Tool names from stream events | Spinner char detection |
| Channel isolation | Automatic (independent process) | `/clear` on channel switch |
| Temp files | None (stdin pipe) | context.md written to WSL |

### V1 Flow (Legacy Fallback)

Set `PETERBOT_ROUTER_V2=0` to revert. Uses tmux screen-scraping via router.py + parser.py + sanitiser.py.

```
handle_message() → session lock → write context.md → tmux send-keys →
poll screen → parser extract → sanitiser clean → pipeline → Discord
```

---

## 4. Skill Execution Flow (Scheduled Jobs)

Scheduled jobs follow a different flow, using pre-fetched data:

```
1. SCHEDULE.md defines job
   | Job | Skill | Schedule | Channel |
   |-----|-------|----------|---------|
   | Hydration | hydration | 09:02,11:02,... UK | #food-log |
       |
       v
2. scheduler.py parses SCHEDULE.md at startup
   - Creates APScheduler jobs
   - Registers with cron/interval triggers
       |
       v
3. APScheduler triggers _execute_job()
   - Check quiet hours (23:00-06:00)
   - Check for job overlap (queue if busy)
       |
       v
4. data_fetchers.py (if skill has fetcher)
   SKILL_DATA_FETCHERS["hydration"] -> get_hydration_data()
   - Calls Hadley API, Garmin, Withings, etc.
   - Returns structured JSON
       |
       v
5. Load SKILL.md from skills/<name>/SKILL.md
   - Contains instructions, output format rules
       |
       v
6. Build skill context
   - Time, skill instructions, pre-fetched data
   - "ONLY output the formatted response"
       |
       v
7. Send to Claude Code
   - V2: invoke_claude_cli() — independent process, no lock
   - V1: session lock → /clear → tmux send-keys → poll → parse
       |
       v
8. Validate response
   - Check for NO_REPLY (suppress output)
   - Check for garbage patterns (v1 only — v2 output is clean)
       |
       v
9. Post to configured channel
   - Process through Response Pipeline (pre_sanitised=True for v2)
   - Optional WhatsApp via Twilio
       |
       v
10. Capture to memory (session: scheduled-<skill>)
```

### Job Registration Sources

| Source | Location | Purpose |
|--------|----------|---------|
| **SCHEDULE.md** | `wsl_config/SCHEDULE.md` | Skill-based jobs (preferred) |
| **bot.py register_*()** | `bot.py` | Legacy jobs (being deprecated) |
| **jobs/*.py** | `jobs/` | Legacy data fetch functions |

**Important**: New jobs should be added as skills in `SCHEDULE.md`, NOT as functions in `jobs/`. The legacy `jobs/` functions remain only for their data-fetching utilities.

---

## 5. Symlink Strategy

The `wsl_config/` directory is symlinked into WSL so Claude Code can read skills and instructions directly:

```
Windows:  C:\Users\Chris Hadley\Discord-Messenger\domains\peterbot\wsl_config\
          |
          | (symlink in WSL)
          v
WSL:      /home/chris_hadley/peterbot -> /mnt/c/Users/Chris Hadley/Discord-Messenger/domains/peterbot/wsl_config
```

### Benefits

1. **Single source of truth**: Edit on Windows, immediately available in WSL
2. **No sync needed**: Changes are instant (same files)
3. **Git-tracked**: All config is in the Windows repo
4. **Claude Code access**: Can read SKILL.md, CLAUDE.md, etc. directly

### Creating the Symlink (one-time setup)

```bash
# In WSL
ln -s "/mnt/c/Users/Chris Hadley/Discord-Messenger/domains/peterbot/wsl_config" ~/peterbot
```

### Verification

```bash
# Should show Windows files
ls -la ~/peterbot/
ls -la ~/peterbot/skills/
```

---

## 6. Job Registration - Skills vs Legacy

### The Preferred Way: Skills (SCHEDULE.md)

```markdown
## Fixed Time Jobs

| Job | Skill | Schedule | Channel | Enabled |
|-----|-------|----------|---------|---------|
| Hydration Check-in | hydration | 09:02,11:02,... UK | #food-log | yes |
```

**Flow**: SCHEDULE.md -> scheduler.py -> data_fetchers.py -> SKILL.md -> Claude Code -> Discord

**Components**:
1. **SKILL.md**: Instructions in `skills/<name>/SKILL.md`
2. **Data Fetcher**: Optional function in `data_fetchers.py`
3. **Schedule Entry**: Row in SCHEDULE.md

### The Legacy Way: Job Functions (DON'T USE)

```python
# bot.py - legacy pattern
register_morning_briefing(scheduler, bot)  # Creates APScheduler job directly
```

**Why Not**:
- No skill instructions for Claude Code
- Hard-coded formatting in Python
- Not editable by Peter
- Being phased out

### Migration Status

The `USE_PETERBOT_SCHEDULER` flag in `bot.py` controls which system is active:
- `True`: Use SCHEDULE.md skills (current)
- `False`: Use legacy job functions

---

## 7. Creating a New Skill

### Step 1: Create SKILL.md

```bash
mkdir domains/peterbot/wsl_config/skills/my-skill
```

```markdown
# skills/my-skill/SKILL.md

---
name: my-skill
description: Brief description
trigger:
  - "keyword1"
  - "keyword2"
scheduled: true
conversational: true
channel: #peterbot
---

# My Skill

## Purpose
What this skill does.

## Pre-fetched Data (if applicable)
```json
{
  "example": "data structure"
}
```

## Output Format
**CRITICAL RULES:**
1. Output ONLY the formatted message
2. NO reasoning or preamble
...
```

### Step 2: Add Data Fetcher (if needed)

```python
# data_fetchers.py

async def get_my_skill_data() -> dict[str, Any]:
    """Fetch data for my-skill."""
    # Call APIs, aggregate data
    return {"key": "value"}

SKILL_DATA_FETCHERS = {
    ...
    "my-skill": get_my_skill_data,
}
```

### Step 3: Add to SCHEDULE.md (if scheduled)

```markdown
| My Skill | my-skill | 09:00 UK | #peterbot | yes |
```

### Step 4: Reload

```
/reload-schedule
```

Or test manually:
```
/skill my-skill
```

---

## 8. Common Pitfalls

### 1. Legacy Job Functions in `jobs/`

**Problem**: Adding new jobs by creating functions in `jobs/` and registering in `bot.py`.

**Solution**: Create skills in `wsl_config/skills/` and add to SCHEDULE.md.

### 2. Local vs Deployed Confusion

**Problem**: Editing files but changes not appearing.

**Solution**:
- Windows files are the source of truth
- WSL symlink means they're the same files
- Check symlink is correct: `ls -la ~/peterbot`

### 3. Missing `/clear` Between Sessions (V1 only)

**Problem**: Claude Code retains context from previous conversation/job.

**Solution**: The v1 router automatically sends `/clear` on channel switch. **Not applicable to v2** — each CLI call is a fresh process with no retained context.

### 4. Uncommitted Changes

**Problem**: Skills/config changed but not tracked.

**Solution**: All `wsl_config/` files are git-tracked. Commit changes regularly.

### 5. Context File Conflicts (V1 only)

**Problem**: Multiple operations writing to same `context.md`.

**Solution**: V1 uses session lock (`_session_lock`). **Not applicable to v2** — context is piped via stdin, no temp files.

### 8. Reverting to V1 (tmux) Router

**Problem**: V2 CLI router has issues and you need to fall back.

**Solution**: Set env var `PETERBOT_ROUTER_V2=0` and restart bot. Old router.py, parser.py, and sanitiser.py are still in-tree and will activate. The tmux session `claude-peterbot` will be created on first message.

### 6. Quiet Hours Bypass

**Problem**: Job doesn't run during 23:00-06:00.

**Solution**: Add `!quiet` suffix to channel: `#peter-heartbeat!quiet`

### 7. WhatsApp Not Working

**Problem**: WhatsApp messages not sending.

**Solution**: Check Twilio credentials, sandbox status. Add `+WhatsApp` to channel in SCHEDULE.md.

---

## 9. Service Dependencies

```
                    +-------------+
                    | Discord API |
                    +------+------+
                           |
                           v
+---------------+    +-----+------+    +----------------+
| Memory Worker | <- | Discord    | -> | Hadley API     |
| :37777        |    | Bot        |    | :8100          |
+---------------+    +-----+------+    +-------+--------+
                           |                   |
                           v                   v
                    +------+------+    +-------+--------+
                    | claude -p   |    | Google APIs    |
                    | (WSL, v2)   |    | Notion, etc.   |
                    +-------------+    +----------------+
                           |
                           v
                    +-------------+
                    | Claude Code |
                    | + MCP tools |
                    +-------------+
```

### Startup Order

1. Memory Worker (claude-mem) - `npm start` in claude-mem directory
2. Hadley API - `uvicorn hadley_api.main:app --port 8100`
3. Discord Bot - `python bot.py`
4. Dashboard (optional) - `uvicorn peter_dashboard.app:app --port 5000`

### Health Checks

- Memory Worker: `http://localhost:37777/health`
- Hadley API: `http://localhost:8100/health`
- Dashboard: `http://localhost:5000/api/status`
- Claude CLI (v2): `wsl bash -c "claude --version"` (should return version)
- tmux session (v1 only): `tmux has-session -t claude-peterbot`

---

## 10. Data Stores & Capture Flow

### Databases

| Database | Path | Purpose |
|----------|------|---------|
| `peter_dashboard/job_history.db` | Windows | Job execution history — `job_executions` table with start time, status, duration, output |
| `data/parser_fixtures.db` | Windows | Parser captures & fixtures — `captures` table with screen_before/after, parser_output, pipeline_output; `fixtures` table for regression testing |
| `data/captures.db` | Windows | Second Brain pending captures — `pending_captures` table for async memory ingestion |
| `~/.claude-mem/claude-mem.db` | Windows | Peterbot-mem conversation memories |

### Capture Flow (Response Lifecycle)

**V2 (Active):**
```
Message/Job → claude -p (WSL) → NDJSON stream → result field (clean text)
    ↓
response/pipeline.py: process(response, pre_sanitised=True) → chunks for Discord
    ↓
Discord channel.send()
```

**V1 (Fallback):**
```
Message/Job → Claude Code (tmux) → screen_before + screen_after captured
    ↓
parser.py: extract_new_response(screen_before, screen_after)
    ↓
response/pipeline.py: process(response) → sanitise → chunks for Discord
    ↓
Discord channel.send()
```

**Where captures are stored:**

| Source | Raw Log | DB Captures | Job History |
|--------|---------|-------------|-------------|
| User messages (router_v2.py) | N/A (no screen capture) | N/A | N/A |
| User messages (router.py, v1) | `~/peterbot/raw_output.log` | `data/parser_fixtures.db` | N/A |
| Scheduled jobs (scheduler.py) | N/A | `data/parser_fixtures.db` (v1 only) | `peter_dashboard/job_history.db` |

**Key files in flow:**
- `domains/peterbot/router_v2.py` — [ACTIVE] CLI --print mode, NDJSON stream parsing
- `domains/peterbot/router.py` — [FALLBACK] tmux screen-scraping
- `domains/peterbot/scheduler.py` — Job execution (uses v2 or v1 based on flag)
- `domains/peterbot/parser.py` — [FALLBACK] Response extraction from screen diffs
- `domains/peterbot/capture_parser.py` — `ParserCaptureStore` for parser quality tracking (v1 only)
- `domains/peterbot/response/pipeline.py` — Formatting, chunking (sanitisation skipped for v2)

### Parser Improvement Pipeline (V1 Only)

Nightly at 02:00 UK, the `parser-improve` skill reviews 24h captures from `data/parser_fixtures.db`:
1. Counts empty responses, ANSI leaks, echo issues, user reactions
2. Checks fixture regression pass rates
3. Runs leakage audit for undetected patterns
4. Recommends parser stage to improve

**Note**: This pipeline is irrelevant when v2 is active, since there is no screen-scraping or parsing.

---

## 11. Configuration Reference

### Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `DISCORD_TOKEN` | Discord bot token | `MTIz...` |
| `PETERBOT_CHANNEL_ID` | Primary channel ID | `1234567890` |
| `PETERBOT_ROUTER_V2` | Router version (`1`=CLI, `0`=tmux). Default: `1` | `1` |
| `PETERBOT_SESSION_PATH` | WSL path to peterbot dir | `/home/chris_hadley/peterbot` |
| `PETERBOT_MEM_URL` | Memory worker URL | `http://localhost:37777` |
| `HADLEY_BRICKS_API_KEY` | HB inventory API key | `sk-...` |
| `TWILIO_*` | WhatsApp credentials | Various |
| `GOOGLE_*` | OAuth credentials | Various |

### Key Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Peter's main instructions, playbook references |
| `PETERBOT_SOUL.md` | Personality, tone, communication style |
| `SCHEDULE.md` | Scheduled job definitions |
| `MEMORY.md` | Memory system usage guide |
| `skills/manifest.json` | Auto-generated skill index |

---

## 12. Debugging Tips

### Check Which Router is Active

The bot logs which router it's using on startup:
```
Peterbot: Using router v2 (Claude CLI --print mode)
```

### Test CLI Directly (V2)

```bash
# In WSL — test Claude CLI works
cd ~/peterbot
echo "Say hello" | claude -p --output-format stream-json --verbose --model opus --permission-mode bypassPermissions --no-session-persistence
```

### View tmux Session (V1 Fallback Only)

```bash
# In WSL
tmux attach -t claude-peterbot
```

Press `Ctrl+B, D` to detach without killing.

### Revert to V1

```bash
# Set env var and restart bot
set PETERBOT_ROUTER_V2=0
# Then restart bot.py via NSSM or manually
```

### View Raw Captures

```bash
# Recent response captures for debugging (v1 only)
tail -f ~/peterbot/raw_captures.log
```

### Test Skill Manually

```
/skill hydration
```

### Check Job Status

```
/status
```

### Force Schedule Reload

```
/reload-schedule
```

---

## 13. Architecture Decisions

### Why CLI --print Instead of tmux? (V2 Migration, Feb 2026)

The original tmux approach required 50+ regex patterns across parser.py (813 lines) and sanitiser.py (978 lines) to screen-scrape responses. The `claude -p --output-format stream-json` mode gives us:

1. **Clean JSON output**: `result` field contains the final response — no parsing needed
2. **No session lock**: Each call is an independent process, enabling concurrent requests
3. **Better interim updates**: Stream events tell us exactly what tools are being called
4. **No tmux at all**: Eliminates screen capture, line wrapping, ANSI stripping, scroll buffer issues
5. **Same capabilities**: Full Claude Code tools, MCP servers, file access, web search

**Revert path**: Set `PETERBOT_ROUTER_V2=0`. Old router.py, parser.py, sanitiser.py remain in-tree.

### Why tmux? (V1 Legacy — Superseded)

1. **Full Claude Code capabilities**: Tools, file access, web search
2. **Persistent session**: Maintains context across messages
3. **Permission mode**: `--permission-mode dontAsk` for autonomous operation
4. **MCP tools**: Access to brave search, memory, etc.

**Downsides** (why we migrated): Session lock contention, fragile screen-scraping, 50+ regex patterns, tmux line wrapping issues.

### Why Symlink Instead of Copy?

1. **Single source of truth**: No sync issues
2. **Instant updates**: No deployment step
3. **Git integration**: All changes tracked
4. **Simpler maintenance**: Edit anywhere, available everywhere

### Why Pre-fetch Data?

1. **Speed**: Data ready when Claude Code starts
2. **Reliability**: Can retry fetches independently
3. **Parallelism**: Fetch all data sources simultaneously
4. **Error isolation**: Skill can still run with partial data

### Why Skills Instead of Job Functions?

1. **Editable by Peter**: Can modify behavior without code changes
2. **Consistent interface**: All jobs follow same pattern
3. **Self-documenting**: SKILL.md contains all instructions
4. **Testable**: `/skill <name>` for manual testing

---

*Last updated: 2026-02-06 — Router V2 (CLI --print mode) now default*
