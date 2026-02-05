# Discord-Messenger Architecture

This document provides a comprehensive overview of the Peterbot system architecture, covering component interactions, file locations, and operational patterns.

---

## 1. System Overview

Peterbot is an AI-powered personal assistant running as a Discord bot on Windows, with Claude Code executing in WSL2 via tmux sessions.

```
+------------------+      +------------------+      +------------------+
|   Discord API    | <--> |  Discord Bot     | <--> |  Hadley API      |
|                  |      |  (Windows)       |      |  (Windows:8100)  |
+------------------+      +--------+---------+      +------------------+
                                   |
                                   | WSL subprocess
                                   v
                         +------------------+
                         |  tmux session    |
                         |  claude-peterbot |
                         |  (WSL2)          |
                         +--------+---------+
                                  |
                                  v
                         +------------------+
                         |  Claude Code     |
                         |  (AI/LLM)        |
                         +------------------+
```

### Services Running

| Service | Port | Platform | Description |
|---------|------|----------|-------------|
| Discord Bot | - | Windows | Main bot process, message routing |
| Hadley API | 8100 | Windows | FastAPI proxy for Gmail, Calendar, Notion |
| Peter Dashboard | 5000 | Windows | Flask web UI for monitoring |
| Memory Worker | 37777 | Windows | claude-mem persistent memory |
| Claude Code | - | WSL2 tmux | AI responses via tmux session |
| Hadley Bricks | 3000 | (External) | LEGO inventory management API |

---

## 2. Code Locations (Critical - Local vs WSL)

### Primary Mapping

| Component | Windows Path | WSL Path | Notes |
|-----------|--------------|----------|-------|
| Bot code | `C:\Users\Chris Hadley\Discord-Messenger\` | N/A | Runs on Windows |
| Peterbot config | `domains\peterbot\wsl_config\` | `/home/chris_hadley/peterbot/` | Symlinked to Windows |
| Claude Code session | N/A | tmux session `claude-peterbot` | Runs in WSL |
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
|   |   |-- router.py           # Message routing, tmux communication
|   |   |-- scheduler.py        # APScheduler job management
|   |   |-- data_fetchers.py    # Pre-fetch data for skills
|   |   |-- memory.py           # Memory context injection
|   |   |-- config.py           # Peterbot-specific config
|   |   |-- parser.py           # Response extraction from tmux
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

When a user sends a message to a Peterbot channel:

```
1. Discord Message
       |
       v
2. bot.py on_message()
   - Deduplication check
   - Channel routing (PETERBOT_CHANNEL_IDS)
       |
       v
3. peterbot/router.py handle_message()
   - Add message to per-channel buffer
   - Fetch memory context (async, graceful degradation)
   - Fetch Second Brain knowledge (async)
   - Acquire session lock (_session_lock)
       |
       v
4. Write context.md file (via WSL bash)
   - Contains: memory, recent buffer, channel info, user message
       |
       v
5. Send to tmux session (claude-peterbot)
   _tmux("send-keys", ..., "Read context.md and respond", "Enter")
       |
       v
6. Poll for response (wait_for_response)
   - Capture screen via tmux capture-pane
   - Detect spinner chars for "thinking" status
   - Post interim updates if taking too long
       |
       v
7. Extract response (parser.py)
   - Diff screen_before vs screen_after
   - Extract Claude's actual response
       |
       v
8. Response Pipeline (response/pipeline.py)
   - Sanitize (remove tool output noise)
   - Classify (report/alert/chat/etc.)
   - Format (Discord markdown)
   - Chunk (2000 char limit)
       |
       v
9. Post to Discord channel
   - Multiple chunks if needed
   - Embed attachments if any
       |
       v
10. Memory capture (async, fire-and-forget)
    - Save message pair for future retrieval
```

### Key Components in Flow

- **Session Lock**: Only one operation (conversation OR scheduled job) can use the tmux session at a time
- **Context File**: Large prompts written to `context.md` to avoid tmux paste issues
- **Channel Isolation**: `/clear` command sent on channel switch to prevent cross-contamination

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
7. Acquire session lock
   - /clear before each scheduled job
       |
       v
8. Send to Claude Code (same as conversation)
       |
       v
9. Extract and validate response
   - Check for NO_REPLY (suppress output)
   - Check for garbage patterns
       |
       v
10. Post to configured channel
    - Process through Response Pipeline
    - Optional WhatsApp via Twilio
       |
       v
11. Capture to memory (session: scheduled-<skill>)
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

### 3. Missing `/clear` Between Sessions

**Problem**: Claude Code retains context from previous conversation/job.

**Solution**: The router automatically sends `/clear` on channel switch. For scheduled jobs, `/clear` is sent before each job.

### 4. Uncommitted Changes

**Problem**: Skills/config changed but not tracked.

**Solution**: All `wsl_config/` files are git-tracked. Commit changes regularly.

### 5. Context File Conflicts

**Problem**: Multiple operations writing to same `context.md`.

**Solution**: Session lock (`_session_lock`) ensures only one operation at a time. Scheduled jobs use unique context filenames.

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
                    | tmux        |    | Google APIs    |
                    | (WSL)       |    | Notion, etc.   |
                    +-------------+    +----------------+
                           |
                           v
                    +-------------+
                    | Claude Code |
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
- tmux session: `tmux has-session -t claude-peterbot`

---

## 10. Configuration Reference

### Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `DISCORD_TOKEN` | Discord bot token | `MTIz...` |
| `PETERBOT_CHANNEL_ID` | Primary channel ID | `1234567890` |
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

## 11. Debugging Tips

### View tmux Session

```bash
# In WSL
tmux attach -t claude-peterbot
```

Press `Ctrl+B, D` to detach without killing.

### Check Recent Context

```bash
cat ~/peterbot/context.md
```

### View Raw Captures

```bash
# Recent response captures for debugging
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

## 12. Architecture Decisions

### Why tmux Instead of Direct API?

1. **Full Claude Code capabilities**: Tools, file access, web search
2. **Persistent session**: Maintains context across messages
3. **Permission mode**: `--permission-mode dontAsk` for autonomous operation
4. **MCP tools**: Access to brave search, memory, etc.

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

*Last updated: 2026-02-05*
