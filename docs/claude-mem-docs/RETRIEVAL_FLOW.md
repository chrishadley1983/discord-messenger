# Retrieval Flow: Search to Results

This document traces how memory is retrieved, from MCP search queries to context injection at session start.

## Two Retrieval Paths

1. **MCP Tools** - On-demand search via `search`, `timeline`, `get_observations`
2. **Context Injection** - Automatic injection at session start

---

## Path 1: MCP Tool Search

### File: `src/servers/mcp-server.ts`

Defines the MCP tools available to Claude.

```typescript
const tools = [
  {
    name: '__IMPORTANT',
    description: `3-LAYER WORKFLOW (ALWAYS FOLLOW):
1. search(query) → Get index with IDs (~50-100 tokens/result)
2. timeline(anchor=ID) → Get context around interesting results
3. get_observations([IDs]) → Fetch full details ONLY for filtered IDs
NEVER fetch full details without filtering first. 10x token savings.`,
  },
  {
    name: 'search',
    description: 'Step 1: Search memory. Returns index with IDs.',
    inputSchema: { type: 'object', additionalProperties: true },
    handler: async (args) => callWorkerAPI('/api/search', args)
  },
  {
    name: 'timeline',
    description: 'Step 2: Get context around results.',
    inputSchema: { type: 'object', additionalProperties: true },
    handler: async (args) => callWorkerAPI('/api/timeline', args)
  },
  {
    name: 'get_observations',
    description: 'Step 3: Fetch full details for filtered IDs.',
    inputSchema: {
      type: 'object',
      properties: { ids: { type: 'array', items: { type: 'number' } } },
      required: ['ids']
    },
    handler: async (args) => callWorkerAPIPost('/api/observations/batch', args)
  }
];
```

**Search Parameters:**
- `query`: Text for semantic search
- `limit`: Max results (default varies)
- `project`: Filter by project name
- `type` / `obs_type`: Filter by observation type
- `dateStart` / `dateEnd`: Date range filter
- `offset`: Pagination offset
- `orderBy`: Sort order

### File: `src/services/worker/search/SearchOrchestrator.ts`

Coordinates search strategies.

```typescript
export class SearchOrchestrator {
  private chromaStrategy: ChromaSearchStrategy | null;
  private sqliteStrategy: SQLiteSearchStrategy;
  private hybridStrategy: HybridSearchStrategy | null;

  async search(args: any): Promise<StrategySearchResult> {
    const options = this.normalizeParams(args);
    return await this.executeWithFallback(options);
  }

  private async executeWithFallback(options: NormalizedParams): Promise<StrategySearchResult> {
    // PATH 1: FILTER-ONLY (no query text) - Use SQLite
    if (!options.query) {
      return await this.sqliteStrategy.search(options);
    }

    // PATH 2: CHROMA SEMANTIC SEARCH (query text + Chroma available)
    if (this.chromaStrategy) {
      const result = await this.chromaStrategy.search(options);

      if (result.usedChroma) {
        return result;
      }

      // Chroma failed - fall back to SQLite
      return await this.sqliteStrategy.search({ ...options, query: undefined });
    }

    // PATH 3: No Chroma available - SQLite only
    return { results: { observations: [], sessions: [], prompts: [] }, usedChroma: false };
  }
}
```

### File: `src/services/worker/search/strategies/ChromaSearchStrategy.ts`

Semantic search via ChromaDB.

```typescript
async search(options: StrategySearchOptions): Promise<StrategySearchResult> {
  // Query ChromaDB for semantic similarity
  const chromaResults = await this.chromaSync.queryObservations(
    options.query,
    options.limit || 20,
    options.project
  );

  // Convert to observation format
  const observations = chromaResults.map(result => ({
    id: parseInt(result.metadata.obsId),
    type: result.metadata.type,
    title: result.metadata.title,
    project: result.metadata.project,
    created_at_epoch: parseInt(result.metadata.createdAtEpoch),
    similarity: result.similarity
  }));

  return { results: { observations }, usedChroma: true, strategy: 'chroma' };
}
```

### File: `src/services/worker/search/strategies/SQLiteSearchStrategy.ts`

Filter-based and FTS5 search via SQLite.

```typescript
search(options: StrategySearchOptions): StrategySearchResult {
  let query = `
    SELECT id, type, title, subtitle, project, created_at_epoch
    FROM observations
    WHERE 1=1
  `;
  const params: any[] = [];

  // Apply filters
  if (options.project) {
    query += ` AND project = ?`;
    params.push(options.project);
  }

  if (options.type) {
    const types = Array.isArray(options.type) ? options.type : [options.type];
    query += ` AND type IN (${types.map(() => '?').join(',')})`;
    params.push(...types);
  }

  if (options.dateRange?.start) {
    query += ` AND created_at_epoch >= ?`;
    params.push(new Date(options.dateRange.start).getTime());
  }

  query += ` ORDER BY created_at_epoch DESC LIMIT ?`;
  params.push(options.limit || 50);

  const results = this.db.prepare(query).all(...params);
  return { results: { observations: results }, usedChroma: false, strategy: 'sqlite' };
}
```

---

## Path 2: Context Injection (Session Start)

### File: `plugin/hooks/hooks.json`

```json
{
  "SessionStart": [
    {
      "matcher": "startup|clear|compact",
      "hooks": [
        { "type": "command", "command": "... hook claude-code context" }
      ]
    }
  ]
}
```

### File: `src/cli/handlers/context.ts`

```typescript
export const contextHandler: EventHandler = {
  async execute(input: NormalizedHookInput): Promise<HookResult> {
    await ensureWorkerRunning();

    const cwd = input.cwd ?? process.cwd();
    const context = getProjectContext(cwd);
    const port = getWorkerPort();

    // Request context from worker
    const projectsParam = context.allProjects.join(',');
    const url = `http://127.0.0.1:${port}/api/context/inject?projects=${encodeURIComponent(projectsParam)}`;

    const response = await fetch(url);
    const additionalContext = await response.text();

    return {
      hookSpecificOutput: {
        hookEventName: 'SessionStart',
        additionalContext  // This gets injected into Claude's context
      }
    };
  }
};
```

### File: `src/services/context/ContextBuilder.ts`

Main orchestrator for context generation.

```typescript
export async function generateContext(
  input?: ContextInput,
  useColors: boolean = false
): Promise<string> {
  const config = loadContextConfig();
  const project = getProjectName(input?.cwd ?? process.cwd());
  const projects = input?.projects || [project];

  const db = new SessionStore();

  // Query data
  const observations = projects.length > 1
    ? queryObservationsMulti(db, projects, config)
    : queryObservations(db, project, config);

  const summaries = projects.length > 1
    ? querySummariesMulti(db, projects, config)
    : querySummaries(db, project, config);

  if (observations.length === 0 && summaries.length === 0) {
    return renderEmptyState(project, useColors);
  }

  return buildContextOutput(project, observations, summaries, config, ...);
}
```

### File: `src/services/context/ContextConfigLoader.ts`

Loads configuration for what to include in context.

```typescript
export function loadContextConfig(): ContextConfig {
  const settings = SettingsDefaultsManager.loadFromFile(settingsPath);

  return {
    totalObservationCount: parseInt(settings.CLAUDE_MEM_CONTEXT_OBSERVATIONS, 10),  // Default: 50
    fullObservationCount: parseInt(settings.CLAUDE_MEM_CONTEXT_FULL_COUNT, 10),     // Default: 3
    sessionCount: parseInt(settings.CLAUDE_MEM_CONTEXT_SESSION_COUNT, 10),          // Default: 5
    showReadTokens: settings.CLAUDE_MEM_CONTEXT_SHOW_READ_TOKENS === 'true',
    showWorkTokens: settings.CLAUDE_MEM_CONTEXT_SHOW_WORK_TOKENS === 'true',
    observationTypes: new Set(settings.CLAUDE_MEM_CONTEXT_OBSERVATION_TYPES.split(',')),
    observationConcepts: new Set(settings.CLAUDE_MEM_CONTEXT_OBSERVATION_CONCEPTS.split(',')),
    fullObservationField: settings.CLAUDE_MEM_CONTEXT_FULL_FIELD,  // 'narrative' or 'facts'
    showLastSummary: settings.CLAUDE_MEM_CONTEXT_SHOW_LAST_SUMMARY === 'true',
    showLastMessage: settings.CLAUDE_MEM_CONTEXT_SHOW_LAST_MESSAGE === 'true',
  };
}
```

### File: `src/services/context/ObservationCompiler.ts`

Queries observations with type and concept filtering.

```typescript
export function queryObservations(
  db: SessionStore,
  project: string,
  config: ContextConfig
): Observation[] {
  const typeArray = Array.from(config.observationTypes);
  const conceptArray = Array.from(config.observationConcepts);

  return db.db.prepare(`
    SELECT
      id, memory_session_id, type, title, subtitle, narrative,
      facts, concepts, files_read, files_modified, discovery_tokens,
      created_at, created_at_epoch
    FROM observations
    WHERE project = ?
      AND type IN (${typeArray.map(() => '?').join(',')})
      AND EXISTS (
        SELECT 1 FROM json_each(concepts)
        WHERE value IN (${conceptArray.map(() => '?').join(',')})
      )
    ORDER BY created_at_epoch DESC
    LIMIT ?
  `).all(project, ...typeArray, ...conceptArray, config.totalObservationCount);
}
```

**Current retrieval logic:**
1. Filter by project
2. Filter by type (must match one of configured types)
3. Filter by concept (must have at least one matching concept)
4. Order by recency (most recent first)
5. Limit to `totalObservationCount` (default 50)

---

## Context Injection Format

### File: `src/services/context/sections/TimelineRenderer.ts`

Renders observations into a timeline format.

**Sample injected context:**
```
## claude-mem | Project: my-project

📊 Token Economics: 2,450 discovery → 890 injected (64% compression)

### Timeline

🔵 [2h ago] Discovery: Understanding auth flow
   How JWT tokens are validated in middleware

🟣 [4h ago] Feature: Add user preferences API
   New endpoint /api/preferences with CRUD operations

🔴 [1d ago] Bugfix: Fix race condition in cache
   Added mutex lock to prevent concurrent cache writes

### Recent Summary
**Request:** Implement caching layer
**Completed:** Redis integration with TTL support
**Next Steps:** Add cache invalidation on writes
```

---

## Key Retrieval Configurations

### Settings (~/.claude-mem/settings.json)

| Setting | Default | Purpose |
|---------|---------|---------|
| `CLAUDE_MEM_CONTEXT_OBSERVATIONS` | 50 | Max observations to query |
| `CLAUDE_MEM_CONTEXT_FULL_COUNT` | 3 | How many show full narrative |
| `CLAUDE_MEM_CONTEXT_SESSION_COUNT` | 5 | Recent summaries to include |
| `CLAUDE_MEM_CONTEXT_OBSERVATION_TYPES` | all | Which types to include |
| `CLAUDE_MEM_CONTEXT_OBSERVATION_CONCEPTS` | all | Which concepts to include |
| `CLAUDE_MEM_CONTEXT_FULL_FIELD` | narrative | Show narrative or facts |
| `CLAUDE_MEM_CONTEXT_SHOW_LAST_SUMMARY` | true | Include most recent summary |
| `CLAUDE_MEM_CONTEXT_SHOW_LAST_MESSAGE` | false | Include prior assistant message |

---

## Summary: Retrieval Flow

### MCP Search (On-demand)
1. Claude calls `mcp__claude-mem__search` tool
2. MCP server forwards to Worker HTTP API
3. SearchOrchestrator selects strategy (Chroma semantic or SQLite filter)
4. Results returned with IDs and summaries
5. Claude can drill down with `timeline` or `get_observations`

### Context Injection (Automatic)
1. SessionStart hook fires
2. context.ts calls Worker `/api/context/inject`
3. ContextBuilder loads config from settings
4. ObservationCompiler queries SQLite with type/concept filters
5. TimelineRenderer formats observations chronologically
6. Full context string returned and injected into Claude's session

**Current limitations:**
- Retrieval is "most recent N" with type/concept filters
- No semantic search for context injection (only MCP search)
- No tiered retrieval (all observations treated equally)
- No category-based prioritization
