# Phase 0: Claude-Mem Validation - Technical Spec

**Project:** Peterbot foundation  
**Purpose:** Install and test claude-mem before forking for personality memory  
**Prerequisite:** Pre-Phase A complete (Discord → Claude Code relay working)  
**Test project:** Discord-Messenger  
**Time estimate:** 30-60 mins  
**Risk:** Low - installation and validation only, no code changes

---

## Overview

Validate that claude-mem works correctly before investing time forking it. We need to confirm:

1. Installation works (Bun, SQLite, ChromaDB)
2. Observations are captured on tool use
3. Web viewer displays data
4. Context injection works on session start
5. Discord relay triggers same hooks as direct typing

---

## Why Discord-Messenger?

- Actively working on it (Pre-A/B implementation)
- Personal project, low stakes
- Will generate real observations during development
- Can validate relay works by using the relay to build the relay

---

## Installation Steps

### 1. Install Bun (if not present)

```bash
curl -fsSL https://bun.sh/install | bash
source ~/.bashrc
```

### 2. Clone claude-mem

```bash
cd ~
git clone https://github.com/thedotmack/claude-mem.git
cd claude-mem
```

### 3. Install dependencies

```bash
bun install
```

### 4. Build

```bash
bun run build
```

---

## Configuration

### Claude-mem settings

Create `~/.claude-mem/settings.json`:

```json
{
  "CLAUDE_MEM_FOLDER_CLAUDEMD_ENABLED": "false",
  "CLAUDE_MEM_CONTEXT_OBSERVATIONS": 30,
  "CLAUDE_MEM_SKIP_TOOLS": ["Read", "Glob", "Grep", "LS"],
  "CLAUDE_MEM_DEBUG": "false"
}
```

| Setting | Value | Why |
|---------|-------|-----|
| `FOLDER_CLAUDEMD_ENABLED` | false | Don't create CLAUDE.md in subdirectories |
| `CONTEXT_OBSERVATIONS` | 30 | Number of observations to inject |
| `SKIP_TOOLS` | Read, Glob, Grep, LS | Skip noisy read-only operations |
| `DEBUG` | false | Keep logs clean (enable if troubleshooting) |

### Claude Code MCP config

Update `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "claude-mem": {
      "command": "bun",
      "args": ["run", "/home/your-username/claude-mem/src/index.ts"],
      "env": {}
    }
  },
  "hooks": {
    // ... existing notification hooks from Pre-A
  }
}
```

**Note:** Replace `/home/your-username/` with your actual WSL home path.

---

## Validation Steps

### Step 1: Start claude-mem worker

The worker should start automatically with Claude Code, but you can verify:

```bash
# Check if running
curl http://localhost:37777/health

# Or check the web viewer
open http://localhost:37777
```

### Step 2: Start test session

```bash
cd /mnt/c/Users/Chris/Projects/Discord-Messenger
tmux new -s claude-discord-messenger
claude
```

### Step 3: Generate observations

Do some real work in Claude Code:

```
Read the bot.py file and summarise the main components

Edit router.py to add a comment at the top

Run: python -c "print('test')"
```

Each of these should create observations.

### Step 4: Check web viewer

Open http://localhost:37777 in your browser.

**Expected:**
- Timeline of observations
- Each shows: timestamp, tool used, summary
- Clicking expands to show details

**If empty:** Check claude-mem logs, verify MCP is connected.

### Step 5: Test context injection

Start a new Claude Code session (or use `/clear` if available):

```bash
# Kill and restart
tmux kill-session -t claude-discord-messenger
cd /mnt/c/Users/Chris/Projects/Discord-Messenger
tmux new -s claude-discord-messenger
claude
```

Then ask:

```
What have I been working on recently?
```

Claude should reference observations from the previous session.

### Step 6: Test via Discord relay

From Discord `#claude-code` channel:

```
use discord-messenger
add a TODO comment to tools.py about session state detection
```

Then check web viewer - the edit should appear as an observation.

**This validates:** tmux relay triggers the same hooks as direct typing.

---

## Success Criteria

| Check | Status |
|-------|--------|
| Bun installed and working | ✅ v1.3.8 |
| Claude-mem cloned and built | ✅ v9.0.12 |
| Worker running on port 37777 | ✅ |
| Web viewer accessible | ✅ |
| Observations appear after tool use | ⬜ (monitoring) |
| Context injected on new session | ⬜ (to test) |
| Discord relay triggers observations | ⬜ (to test) |
| No CLAUDE.md files in project | ✅ (FOLDER_CLAUDEMD disabled) |

---

## Troubleshooting

### Worker not starting

```bash
# Check if port in use
lsof -i :37777

# Run manually to see errors
cd ~/claude-mem
bun run src/index.ts
```

### No observations appearing

1. Check MCP is registered: `claude mcp list` (if available)
2. Enable debug: set `CLAUDE_MEM_DEBUG": "true"` and restart
3. Check logs in `~/.claude-mem/logs/`

### Context not injecting

1. Verify `CONTEXT_OBSERVATIONS` > 0
2. Check there are actually observations in the database
3. Try `/memory status` or similar command if available

### Discord relay not triggering hooks

The relay should be invisible to claude-mem - it just sees stdin/stdout like normal typing. If observations don't appear:

1. Verify tmux session is correct
2. Check Claude Code is actually receiving and processing the command
3. Use `screen` command to verify output

---

## Files Created

| Path | Purpose |
|------|---------|
| `~/claude-mem/` | Claude-mem installation |
| `~/.claude-mem/settings.json` | Configuration |
| `~/.claude-mem/claude-mem.db` | SQLite database |
| `~/.claude-mem/chroma/` | Vector embeddings |
| `~/.claude/hooks/start-claude-mem-worker.sh` | Auto-start worker on session |
| `Discord-Messenger/.mcp.json` | MCP server registration |

### Additional Setup (not in original spec)

- **uvx v0.9.28** installed for ChromaDB vector search
- **SessionStart hook** added to auto-start worker service

---

## Next Steps

**If validation passes:**
- Phase 1: Fork repo, understand internals
- Focus on `src/sdk/prompts.ts` for compression logic
- Identify where to add personality observation types

**If validation fails:**
- Debug before proceeding
- Check GitHub issues for known problems
- Consider alternative approaches if fundamentally broken

---

## Notes for Phase 1

While testing, pay attention to:

1. **What observations look like** - Format, content, usefulness
2. **What's missing** - Personal context? Interaction style?
3. **Compression quality** - Are summaries accurate?
4. **Token usage** - How much context does injection use?

These insights will inform the Phase 1-5 fork decisions.
