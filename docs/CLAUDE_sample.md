# Claude-Mem: AI Development Instructions

Claude-mem is a Claude Code plugin providing persistent memory across sessions. It captures tool usage, compresses observations using the Claude Agent SDK, and injects relevant context into future sessions.

## Architecture

**5 Lifecycle Hooks**: SessionStart → UserPromptSubmit → PostToolUse → Summary → SessionEnd
**Hooks** (`src/hooks/*.ts`) - TypeScript → ESM, built to `plugin/scripts/*-hook.js`
**Worker Service** (`src/services/worker-service.ts`) - Express API on port 37777, Bun-managed, handles AI processing asynchronously
**Database** (`src/services/sqlite/`) - SQLite3 at `~/.claude-mem/claude-mem.db`
**Search Skill** (`plugin/skills/mem-search/SKILL.md`) - HTTP API for searching past work, auto-invoked when users ask about history
**Chroma** (`src/services/sync/ChromaSync.ts`) - Vector embeddings for semantic search
**Viewer UI** (`src/ui/viewer/`) - React interface at http://localhost:37777, built to `plugin/ui/viewer.html`

## Privacy Tags

- `<private>content</private>` - User-level privacy control

## Build Commands

npm run build-and-sync

## File Locations

- **Database**: `~/.claude-mem/claude-mem.db`
- **Chroma**: `~/.claude-mem/chroma/`

---

## Peterbot Mode

When running as Peterbot via Discord, see `PETERBOT_SOUL.md` for personality and conversation style.

### Tool Usage (Peterbot)

**Web Search** - USE PROACTIVELY for:
- Current events, news, prices, weather
- "Who is", "what is the latest", time-sensitive queries
- Facts you're uncertain about
- Research tasks (search multiple times, synthesize)
- Anything that could have changed since training

**Memory Context** - Injected above each message. Use naturally without announcing it.

**File/Code Tools** - Available but Peterbot is conversational layer. Use for quick lookups, not heavy implementation.
