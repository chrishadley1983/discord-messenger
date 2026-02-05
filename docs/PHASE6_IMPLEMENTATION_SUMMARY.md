# Phase 6: Discord Bot Integration - Implementation Summary

## Original Spec Summary

Wire peterbot-mem into the Discord bot so that:
1. Peterbot channel routes through Claude Code (tmux) - NOT Claude API
2. Memory context is injected before messages go to Claude Code
3. Message pairs are captured async for observation extraction

---

## What Was Implemented

### Core Architecture

```
Discord message (#peterbot)
       ↓
bot.py: Special routing for PETERBOT_CHANNEL
       ↓
peterbot/router.py:handle_message()
  1. Ensure headless tmux session exists (claude-peterbot)
  2. Add message to recent_buffer
  3. GET /api/context/inject - fetch memory context
  4. Build full context (time + memory + buffer + message)
  5. Write context to file (avoids tmux paste issues)
  6. Send prompt to Claude Code session
  7. Poll until response stabilizes (with thinking detection)
  8. Extract new response (marker-based + filtering)
  9. Log raw capture for debugging
  10. Capture message pair async to peterbot-mem
       ↓
Return cleaned response to Discord
```

### Files Created

| File | Purpose |
|------|---------|
| `domains/peterbot/config.py` | Session paths, memory endpoints, timeouts |
| `domains/peterbot/memory.py` | Memory client - context fetch, capture, retry queue |
| `domains/peterbot/router.py` | Message routing with memory injection |

### Files Modified

| File | Changes |
|------|---------|
| `domains/peterbot/__init__.py` | Export router functions |
| `bot.py` | Add peterbot special routing (like claude-code) |
| `~/.claude/hooks/discord-notify.sh` | Added peterbot exclusion |

### WSL Files Created

| File | Purpose |
|------|---------|
| `/home/chris_hadley/peterbot/CLAUDE.md` | Technical instructions for Claude Code |
| `/home/chris_hadley/peterbot/PETERBOT_SOUL.md` | Personality definition |
| `/home/chris_hadley/peterbot/.claude/settings.json` | Disabled hooks for isolation |
| `/home/chris_hadley/peterbot/.claude/skills/news/SKILL.md` | News skill |

---

## Scope Creep Items (Beyond Original Spec)

### 1. Headless Session Management
- **Original**: Use shared `start_session` from claude-code tools
- **Implemented**: Custom `create_headless_session()` - no Windows Terminal popup, complete isolation from claude-code channel

### 2. File-Based Context Injection
- **Original**: Send context directly via tmux send-keys
- **Implemented**: Write to `context.md` file, send simple prompt to read it (avoids tmux paste issues with large multi-line content)

### 3. Response Extraction Improvements
- **Original**: Basic diff-based extraction
- **Implemented**:
  - Marker-based extraction (find prompt, extract after)
  - Extensive filtering for Claude Code UI elements
  - Thinking state detection (wait while "Contemplating", "Searching", etc.)
  - Deduplication for rapid queued messages

### 4. Current Time Injection
- **Not in spec**: Added current date/time to context so Peterbot knows what day it is

### 5. Discord Formatting Guidance
- **Not in spec**: Added `PETERBOT_SOUL.md` with Discord-specific formatting rules

### 6. News Skill
- **Not in spec**: Full news skill implementation
  - Memory-aware source preferences
  - Markdown link formatting (avoid URL clipping)
  - Discord-optimized output

### 7. Raw Capture Logging
- **Not in spec**: Debug logging system
  - Async, non-blocking
  - Rolling 50KB log
  - Captures before/after screen states

### 8. Permission Mode
- **Not in spec**: Session starts with `--permission-mode dontAsk` to auto-approve tool use

---

## Key Technical Decisions

### 1. Why File-Based Context?
Tmux `send-keys` with large multi-line content triggers Claude Code's paste detection, showing `[Pasted text #1 +115 lines]` and not submitting properly. Writing to a file and sending a simple "Read context.md" prompt avoids this.

### 2. Why Marker-Based Extraction?
Diff-based extraction failed when:
- Screen scrolled, changing which lines were "new"
- Rapid messages caused context slip
Marker-based finds our prompt and extracts everything after, more reliable.

### 3. Why Thinking Detection?
Claude Code shows states like "Contemplating... (1m 15s)" during long operations. Without detection, we'd capture incomplete responses. Now we wait until no thinking indicators present.

### 4. Why Headless Session?
Using shared `start_session()` opened Windows Terminal and triggered hooks that posted to #claude-actions channel. Custom headless creation keeps peterbot isolated.

---

## Filters Applied to Response

Lines containing these patterns are stripped:
- `ctrl+`, `ctrl-` (keyboard shortcuts)
- `? for shortcuts` (status line)
- `Read X file` (tool use indicator)
- `Web Search(`, `Fetch(` (tool calls)
- `Skill(` (skill invocation)
- `Ran X hooks/tools` (hook status)
- `hook error`, `loaded skill` (status messages)
- `⎿` (nested output marker)
- `✻`, `✓`, `✗`, `⏵`, `✶` (status symbols)
- `Churned for`, `Worked for`, `Cogitated for` (timing)
- `Did X search` (search status)
- `shift+tab`, `don't ask` (mode indicators)
- Token/cost lines
- Prompt lines (`>`, `❯`)

---

## Configuration

### Environment Variables
- `PETERBOT_CHANNEL_ID` - Discord channel ID
- `PETERBOT_MEM_URL` - Worker URL (default: http://localhost:37777)
- `PETERBOT_SESSION_PATH` - WSL path (default: /home/chris_hadley/peterbot)

### Timeouts
- `RESPONSE_TIMEOUT`: 60 seconds
- `POLL_INTERVAL`: 0.5 seconds
- `STABLE_COUNT_THRESHOLD`: 3 (1.5s stability)
- Claude Code init delay: 8 seconds

---

## Verification Checklist

| Test | Status |
|------|--------|
| Session creates on first message | ✓ |
| Memory context injected | ✓ |
| Response extracted cleanly | ✓ |
| No UI elements in response | ✓ |
| #claude-code channel unaffected | ✓ |
| News skill invoked for news requests | ✓ |
| Thinking detection waits for completion | ✓ |
| Message pairs captured to memory | ✓ (verified via search API) |
| Raw logging working | ✓ |

---

## Known Limitations

1. **Session State Persistence**: Claude Code remembers conversation within session. If a response is missed/incomplete, Claude may say "I already answered that"

2. **Long Response Times**: News requests with multiple searches can take 2+ minutes. User sees typing indicator during this time.

3. **URL Line Wrapping**: Long URLs in raw format get clipped by tmux. Solved by requiring markdown links in news skill.

4. **Memory Capture Verification**: Async capture fires but success not confirmed in Discord. Check worker logs or search API to verify.

---

## Files for Review

### Core Implementation
- `domains/peterbot/config.py`
- `domains/peterbot/memory.py`
- `domains/peterbot/router.py`
- `domains/peterbot/__init__.py`
- `bot.py` (lines 29-34, 113-114, 184-194)

### WSL Configuration (Version Controlled)
Source of truth is in `domains/peterbot/wsl_config/`:
- `CLAUDE.md` - Technical instructions for Claude Code
- `PETERBOT_SOUL.md` - Personality definition
- `skills/news/SKILL.md` - News skill
- `README.md` - Explains the two-location strategy
- `sync.py` - Script to copy files to WSL

Deployed to `/home/chris_hadley/peterbot/` via `python domains/peterbot/wsl_config/sync.py`

### Supporting Changes
- `~/.claude/hooks/discord-notify.sh` (peterbot exclusion)

---

## File Location Strategy

### Why Two Locations?

| Location | Purpose |
|----------|---------|
| `/home/chris_hadley/peterbot/` | Claude Code's working directory - where it runs as Peterbot |
| `domains/peterbot/wsl_config/` | Version-controlled source - edit here, sync to WSL |

The WSL folder is NOT the peterbot-mem codebase. It's a dedicated workspace for the Claude Code session that processes Discord messages. It contains:
- Personality files (CLAUDE.md, PETERBOT_SOUL.md)
- Skills that Claude Code can invoke
- Transient files (context.md, raw_capture.log)
- Claude Code settings (.claude/settings.json)

### Skills Strategy

Two skill systems exist by design:

1. **Claude Code Native Skills** (in `wsl_config/skills/`):
   - Standard Claude Code skill markdown format
   - Called during peterbot Discord sessions
   - Example: news skill for formatted news requests

2. **Phase 7 Self-Improvement Skills** (future, in peterbot-mem repo):
   - Skills that modify the memory system itself
   - Different invocation mechanism (HTTP API)
   - Example: "tune my prompts" skill

---

## Review Responses

### Session Path Confusion
`/home/chris_hadley/peterbot` is intentionally separate from peterbot-mem. It's Claude Code's working directory when answering Discord messages - like a dedicated "office" for Peterbot.

### Version Control
WSL config files are now tracked in `domains/peterbot/wsl_config/`. Run `sync.py` after edits.

### Filter List Concerns
The extensive filter list handles Claude Code UI elements that shouldn't appear in Discord. If false positives occur, add exceptions rather than removing filters. The list is auditable in `router.py:clean_response_lines()`.

### Permission Mode (dontAsk)
This auto-approves tool use within the session. Safe because:
- Session runs in isolated workspace (~/peterbot)
- Only tools are Read, WebSearch, WebFetch, Skill
- No write access to sensitive directories
- Session is transient (destroyed on bot restart)

### Memory Capture Verification
Confirmed working. Test with:
```bash
curl "http://localhost:37777/api/search?project=peterbot&limit=5"
```
