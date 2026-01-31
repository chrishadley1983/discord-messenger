# Claude-Mem Architecture

This document maps the complete file structure and explains each component's purpose.

## High-Level Architecture

```
+-----------------------------------------------------------------------------+
|                           CLAUDE CODE (Primary Session)                      |
|                                                                              |
|  User --> Claude --> Tool Use --> Hook Triggered                            |
+-------------------------------------+----------------------------------------+
                                      | PostToolUse / Stop / SessionStart
                                      v
+-----------------------------------------------------------------------------+
|                           HOOKS (plugin/hooks/hooks.json)                    |
|                                                                              |
|  SessionStart --> context handler --> inject memory into session            |
|  UserPromptSubmit --> session-init handler --> create/resume session        |
|  PostToolUse --> observation handler --> queue tool data                     |
|  Stop --> summarize handler --> trigger session summary                      |
+-------------------------------------+----------------------------------------+
                                      | HTTP calls to localhost:37777
                                      v
+-----------------------------------------------------------------------------+
|                           WORKER SERVICE (port 37777)                        |
|                                                                              |
|  HTTP API --> SessionManager --> SDKAgent --> Claude Agent SDK               |
|                                     |                                        |
|                                     v                                        |
|  Parses XML --> Stores to SQLite --> Syncs to ChromaDB                       |
+-----------------------------------------------------------------------------+
```

---

## Directory Structure

### `/plugin/` - Claude Code Plugin Package
The installable plugin that hooks into Claude Code.

| Path | Purpose |
|------|---------|
| `plugin/hooks/hooks.json` | **CRITICAL**: Defines all Claude Code hooks (SessionStart, PostToolUse, Stop, UserPromptSubmit) |
| `plugin/.claude-plugin/plugin.json` | Plugin manifest for Claude Code marketplace |
| `plugin/modes/code.json` | **CRITICAL**: Default mode config with observation types and compression prompts |
| `plugin/modes/code--*.json` | Localized versions of code mode (Japanese, Spanish, etc.) |
| `plugin/scripts/worker-service.cjs` | Compiled worker entry point |
| `plugin/scripts/smart-install.js` | Auto-installs native dependencies |
| `plugin/ui/viewer-bundle.js` | Compiled web UI bundle |

### `/src/cli/` - CLI Hook Handlers
Processes hook events from Claude Code.

| Path | Purpose |
|------|---------|
| `src/cli/handlers/context.ts` | **SessionStart**: Fetches and injects memory context |
| `src/cli/handlers/observation.ts` | **PostToolUse**: Sends tool data to worker |
| `src/cli/handlers/session-init.ts` | **UserPromptSubmit**: Creates/resumes SDK session |
| `src/cli/handlers/summarize.ts` | **Stop**: Triggers session summary generation |
| `src/cli/handlers/user-message.ts` | Handles user message events |
| `src/cli/hook-command.ts` | CLI entry point for hook execution |
| `src/cli/adapters/` | Adapters for different clients (claude-code, cursor, raw) |

### `/src/sdk/` - Agent SDK Integration
Interfaces with Claude Agent SDK for compression.

| Path | Purpose |
|------|---------|
| `src/sdk/prompts.ts` | **CRITICAL**: Builds prompts for SDK agent (init, observation, summary, continuation) |
| `src/sdk/parser.ts` | **CRITICAL**: Parses XML observation and summary blocks from SDK responses |
| `src/sdk/index.ts` | Module exports |

### `/src/services/sqlite/` - SQLite Database Layer
Persistent storage for all memory data.

| Path | Purpose |
|------|---------|
| `src/services/sqlite/migrations.ts` | **CRITICAL**: Database schema definitions (7 migrations) |
| `src/services/sqlite/Database.ts` | Base database class with migration support |
| `src/services/sqlite/SessionStore.ts` | Main interface for session/observation operations |
| `src/services/sqlite/Observations.ts` | Re-exports from observations/ subdirectory |
| `src/services/sqlite/observations/store.ts` | **CRITICAL**: `storeObservation()` - saves parsed observations |
| `src/services/sqlite/observations/types.ts` | TypeScript interfaces for observations |
| `src/services/sqlite/observations/get.ts` | Query observations by ID |
| `src/services/sqlite/observations/recent.ts` | Query recent observations |
| `src/services/sqlite/SessionSearch.ts` | FTS5 full-text search queries |
| `src/services/sqlite/Summaries.ts` | Session summary storage |
| `src/services/sqlite/Timeline.ts` | Timeline query utilities |

### `/src/services/worker/` - Background Worker Service
Long-running service that processes observations.

| Path | Purpose |
|------|---------|
| `src/services/worker/SDKAgent.ts` | **CRITICAL**: Runs Claude Agent SDK loop, manages session lifecycle |
| `src/services/worker/SessionManager.ts` | Manages active sessions, message queues |
| `src/services/worker/DatabaseManager.ts` | Database connection management |
| `src/services/worker/Search.ts` | Re-exports from search/ subdirectory |
| `src/services/worker/search/SearchOrchestrator.ts` | **CRITICAL**: Coordinates search strategies |
| `src/services/worker/search/strategies/ChromaSearchStrategy.ts` | Semantic search via ChromaDB |
| `src/services/worker/search/strategies/SQLiteSearchStrategy.ts` | Filter-based search via SQLite |
| `src/services/worker/search/strategies/HybridSearchStrategy.ts` | Combined semantic + filter search |
| `src/services/worker/agents/ResponseProcessor.ts` | **CRITICAL**: Parses SDK responses, saves observations |
| `src/services/worker/http/routes/` | HTTP API route handlers |

### `/src/services/context/` - Context Injection
Builds memory context for session start.

| Path | Purpose |
|------|---------|
| `src/services/context/ContextBuilder.ts` | **CRITICAL**: Main entry point for context generation |
| `src/services/context/ContextConfigLoader.ts` | Loads settings for context filtering |
| `src/services/context/ObservationCompiler.ts` | **CRITICAL**: Queries and filters observations for injection |
| `src/services/context/TokenCalculator.ts` | ROI/token usage calculations |
| `src/services/context/sections/` | Renderers for header, timeline, summary, footer |
| `src/services/context/formatters/` | Markdown and color output formatters |

### `/src/services/sync/` - ChromaDB Synchronization
Vector database for semantic search.

| Path | Purpose |
|------|---------|
| `src/services/sync/ChromaSync.ts` | **CRITICAL**: Syncs observations/summaries to ChromaDB collections |

### `/src/services/domain/` - Domain Logic
Mode and configuration management.

| Path | Purpose |
|------|---------|
| `src/services/domain/ModeManager.ts` | Loads and manages active mode configuration |
| `src/services/domain/types.ts` | Mode configuration TypeScript interfaces |

### `/src/servers/` - MCP Server
Model Context Protocol server for Claude Desktop/other clients.

| Path | Purpose |
|------|---------|
| `src/servers/mcp-server.ts` | MCP tool definitions (search, timeline, get_observations) |

### `/src/shared/` - Shared Utilities
Cross-cutting concerns used throughout.

| Path | Purpose |
|------|---------|
| `src/shared/paths.ts` | Standard file paths (~/.claude-mem/, etc.) |
| `src/shared/worker-utils.ts` | Worker port/host configuration |
| `src/shared/SettingsDefaultsManager.ts` | Settings file loading with defaults |
| `src/shared/hook-constants.ts` | Hook configuration constants |

### `/src/types/` - TypeScript Types
Shared type definitions.

| Path | Purpose |
|------|---------|
| `src/types/database.ts` | Database row types |
| `src/types/transcript.ts` | Transcript parsing types |

---

## Database Schema (SQLite)

### Core Tables (from migrations.ts)

#### `sdk_sessions`
Tracks SDK compression sessions.
```sql
id INTEGER PRIMARY KEY
content_session_id TEXT UNIQUE NOT NULL  -- Claude Code session ID
memory_session_id TEXT UNIQUE            -- SDK agent session ID
project TEXT NOT NULL
user_prompt TEXT
started_at TEXT NOT NULL
started_at_epoch INTEGER NOT NULL
completed_at TEXT
completed_at_epoch INTEGER
status TEXT CHECK(status IN ('active', 'completed', 'failed'))
```

#### `observations`
Stores compressed observations.
```sql
id INTEGER PRIMARY KEY
memory_session_id TEXT NOT NULL          -- FK to sdk_sessions
project TEXT NOT NULL
text TEXT NOT NULL                       -- Legacy field
type TEXT NOT NULL CHECK(type IN ('decision', 'bugfix', 'feature', 'refactor', 'discovery'))
title TEXT
subtitle TEXT
facts TEXT                               -- JSON array
narrative TEXT
concepts TEXT                            -- JSON array
files_read TEXT                          -- JSON array
files_modified TEXT                      -- JSON array
prompt_number INTEGER
discovery_tokens INTEGER DEFAULT 0       -- ROI tracking
created_at TEXT NOT NULL
created_at_epoch INTEGER NOT NULL
```

#### `session_summaries`
Stores session progress summaries.
```sql
id INTEGER PRIMARY KEY
memory_session_id TEXT UNIQUE NOT NULL   -- FK to sdk_sessions
project TEXT NOT NULL
request TEXT
investigated TEXT
learned TEXT
completed TEXT
next_steps TEXT
notes TEXT
discovery_tokens INTEGER DEFAULT 0
created_at TEXT NOT NULL
created_at_epoch INTEGER NOT NULL
```

#### `observations_fts` (FTS5 Virtual Table)
Full-text search index on observations.
```sql
-- Content synced via triggers from observations table
title, subtitle, narrative, text, facts, concepts
```

---

## ChromaDB Collections

### `claude-mem-observations`
Vector embeddings for semantic search on observations.

**Document format:**
```
{title} | {subtitle}

{narrative}

Facts:
- {fact1}
- {fact2}

Concepts: {concept1}, {concept2}
```

**Metadata:**
- `obsId`: Observation database ID
- `memorySessionId`: Session ID
- `project`: Project name
- `type`: Observation type
- `promptNumber`: Prompt sequence number
- `createdAtEpoch`: Timestamp

### `claude-mem-summaries`
Vector embeddings for semantic search on summaries.

---

## Mode Configuration (code.json)

Modes define observation types and compression prompts.

### `observation_types` Array
```json
[
  { "id": "bugfix", "label": "Bug Fix", "description": "Something was broken, now fixed" },
  { "id": "feature", "label": "Feature", "description": "New capability added" },
  { "id": "refactor", "label": "Refactor", "description": "Code restructured" },
  { "id": "change", "label": "Change", "description": "Generic modification" },
  { "id": "discovery", "label": "Discovery", "description": "Learning about existing system" },
  { "id": "decision", "label": "Decision", "description": "Architectural choice with rationale" }
]
```

### `observation_concepts` Array
```json
[
  { "id": "how-it-works", "label": "How It Works" },
  { "id": "why-it-exists", "label": "Why It Exists" },
  { "id": "what-changed", "label": "What Changed" },
  { "id": "problem-solution", "label": "Problem-Solution" },
  { "id": "gotcha", "label": "Gotcha" },
  { "id": "pattern", "label": "Pattern" },
  { "id": "trade-off", "label": "Trade-Off" }
]
```

### `prompts` Object
Contains all prompt templates used by the SDK agent. Key prompts:
- `system_identity`: Defines the observer agent's role
- `observer_role`: Instructions for observation behavior
- `recording_focus`: What to record vs. skip
- `type_guidance`: How to select observation type
- `concept_guidance`: How to select concepts
- `output_format_header`: XML template instructions

---

## Key Files for Modification

| Feature | Primary File | Secondary Files |
|---------|-------------|-----------------|
| Observation types | `plugin/modes/code.json` | `src/services/sqlite/migrations.ts` |
| Compression prompts | `plugin/modes/code.json` (prompts object) | `src/sdk/prompts.ts` |
| Storage schema | `src/services/sqlite/migrations.ts` | `src/services/sqlite/observations/store.ts` |
| Retrieval logic | `src/services/context/ObservationCompiler.ts` | `src/services/context/ContextConfigLoader.ts` |
| Context injection | `src/services/context/ContextBuilder.ts` | `src/services/context/sections/*.ts` |
| Search | `src/services/worker/search/SearchOrchestrator.ts` | `src/services/worker/search/strategies/*.ts` |
