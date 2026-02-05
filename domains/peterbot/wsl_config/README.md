# Peterbot WSL Configuration

This folder contains version-controlled copies of the files that live in WSL at `/home/chris_hadley/peterbot/`.

## Why Two Locations?

**WSL Location** (`/home/chris_hadley/peterbot/`):
- Where Claude Code runs as "Peterbot"
- Active working directory for the tmux session
- Contains transient files like `context.md` and `raw_capture.log`

**This Folder** (`domains/peterbot/wsl_config/`):
- Version-controlled source of truth
- Changes here should be synced to WSL

## Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Technical instructions for Claude Code (tools, memory, skills) |
| `PETERBOT_SOUL.md` | Personality definition and conversation style |
| `skills/news/SKILL.md` | News skill with memory-aware formatting |

## Syncing

After editing files here, sync to WSL:

```bash
# From project root
python domains/peterbot/wsl_config/sync.py
```

Or manually:
```bash
wsl bash -c "cp /mnt/c/Users/Chris\ Hadley/Discord-Messenger/domains/peterbot/wsl_config/CLAUDE.md /home/chris_hadley/peterbot/"
wsl bash -c "cp /mnt/c/Users/Chris\ Hadley/Discord-Messenger/domains/peterbot/wsl_config/PETERBOT_SOUL.md /home/chris_hadley/peterbot/"
wsl bash -c "mkdir -p /home/chris_hadley/peterbot/.claude/skills/news && cp /mnt/c/Users/Chris\ Hadley/Discord-Messenger/domains/peterbot/wsl_config/skills/news/SKILL.md /home/chris_hadley/peterbot/.claude/skills/news/"
```

## Skills Strategy

Two skill locations exist by design:

1. **Claude Code native skills** (here in `wsl_config/skills/`):
   - Called by Claude Code during peterbot sessions
   - Format: Standard Claude Code skill markdown

2. **Phase 7 self-improvement skills** (future, in peterbot-mem repo):
   - Skills that modify the memory system itself
   - Will use different invocation mechanism
