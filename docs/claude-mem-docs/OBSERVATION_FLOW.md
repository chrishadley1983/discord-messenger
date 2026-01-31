# Observation Flow: Capture to Storage

This document traces an observation from the moment it's captured to when it's stored in the database.

## Overview

```
User uses tool in Claude Code
         |
         v
+------------------+     +-------------------+     +------------------+
| PostToolUse Hook | --> | Worker HTTP API   | --> | SessionManager   |
| observation.ts   |     | /api/sessions/    |     | queues message   |
+------------------+     | observations      |     +------------------+
                         +-------------------+              |
                                                           v
+------------------+     +-------------------+     +------------------+
| SQLite + Chroma  | <-- | ResponseProcessor | <-- | SDKAgent         |
| storage          |     | parses XML        |     | runs Claude      |
+------------------+     +-------------------+     +------------------+
```

---

## Step 1: Hook Trigger

### File: `plugin/hooks/hooks.json`

```json
{
  "PostToolUse": [
    {
      "matcher": "*",
      "hooks": [
        {
          "type": "command",
          "command": "bun \"${CLAUDE_PLUGIN_ROOT}/scripts/worker-service.cjs\" hook claude-code observation",
          "timeout": 120
        }
      ]
    }
  ]
}
```

**What happens:**
- Claude Code fires `PostToolUse` event after ANY tool execution
- The `matcher: "*"` catches all tool uses (Read, Write, Bash, etc.)
- Passes tool data via stdin to the hook handler

### File: `src/cli/handlers/observation.ts`

```typescript
export const observationHandler: EventHandler = {
  async execute(input: NormalizedHookInput): Promise<HookResult> {
    await ensureWorkerRunning();

    const { sessionId, cwd, toolName, toolInput, toolResponse } = input;
    const port = getWorkerPort();

    // Send to worker - worker handles privacy check and database operations
    const response = await fetch(`http://127.0.0.1:${port}/api/sessions/observations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contentSessionId: sessionId,
        tool_name: toolName,
        tool_input: toolInput,
        tool_response: toolResponse,
        cwd
      })
    });

    return { continue: true, suppressOutput: true };
  }
};
```

**Data passed to worker:**
- `contentSessionId`: Claude Code's session ID (links all observations in a conversation)
- `tool_name`: e.g., "Read", "Write", "Bash"
- `tool_input`: JSON of tool parameters
- `tool_response`: JSON of tool output
- `cwd`: Working directory (for project identification)

---

## Step 2: Worker Receives Observation

### File: `src/services/worker/http/routes/SessionRoutes.ts`

The worker HTTP API receives the observation and queues it for the SDK agent.

### File: `src/services/worker/SessionManager.ts`

```typescript
// Observation is added to the session's message queue
session.pendingMessages.push({
  type: 'observation',
  tool_name: toolName,
  tool_input: toolInput,
  tool_response: toolResponse,
  cwd: cwd,
  prompt_number: promptNumber
});
```

---

## Step 3: SDK Agent Processing

### File: `src/services/worker/SDKAgent.ts`

The SDK agent runs a Claude subprocess that observes the primary session.

```typescript
async startSession(session: ActiveSession, worker?: WorkerRef): Promise<void> {
  // Create message generator (event-driven)
  const messageGenerator = this.createMessageGenerator(session, cwdTracker);

  // Run Agent SDK query loop
  const queryResult = query({
    prompt: messageGenerator,
    options: {
      model: modelId,
      cwd: OBSERVER_SESSIONS_DIR,
      disallowedTools,  // Observer has NO tools - observation only
      abortController: session.abortController,
      pathToClaudeCodeExecutable: claudePath,
    }
  });

  // Process SDK messages
  for await (const message of queryResult) {
    if (message.type === 'assistant') {
      // Parse and process response
      await processAgentResponse(textContent, session, ...);
    }
  }
}
```

---

## Step 4: Compression Prompts

### File: `plugin/modes/code.json` (prompts object)

The SDK agent receives structured prompts that instruct it how to compress observations.

#### System Identity Prompt
```
You are a Claude-Mem, a specialized observer tool for creating searchable memory FOR FUTURE SESSIONS.

CRITICAL: Record what was LEARNED/BUILT/FIXED/DEPLOYED/CONFIGURED, not what you (the observer) are doing.

You do not have access to tools. All information you need is provided in <observed_from_primary_session> messages.
```

#### Recording Focus Prompt
```
WHAT TO RECORD
--------------
Focus on deliverables and capabilities:
- What the system NOW DOES differently (new capabilities)
- What shipped to users/production (features, fixes, configs, docs)
- Changes in technical domains (auth, data, UI, infra, DevOps, docs)

Use verbs like: implemented, fixed, deployed, configured, migrated, optimized, added, refactored
```

#### Type Guidance Prompt
```
**type**: MUST be EXACTLY one of these 6 options (no other values allowed):
  - bugfix: something was broken, now fixed
  - feature: new capability or functionality added
  - refactor: code restructured, behavior unchanged
  - change: generic modification (docs, config, misc)
  - discovery: learning about existing system
  - decision: architectural/design choice with rationale
```

#### Concept Guidance Prompt
```
**concepts**: 2-5 knowledge-type categories. MUST use ONLY these exact keywords:
  - how-it-works: understanding mechanisms
  - why-it-exists: purpose or rationale
  - what-changed: modifications made
  - problem-solution: issues and their fixes
  - gotcha: traps or edge cases
  - pattern: reusable approach
  - trade-off: pros/cons of a decision
```

#### Output Format (XML Template)
```xml
<observation>
  <type>[ bugfix | feature | refactor | change | discovery | decision ]</type>
  <title>[Short title capturing the core action or topic]</title>
  <subtitle>[One sentence explanation (max 24 words)]</subtitle>
  <facts>
    <fact>[Concise, self-contained statement]</fact>
    <fact>[Concise, self-contained statement]</fact>
  </facts>
  <narrative>[Full context: What was done, how it works, why it matters]</narrative>
  <concepts>
    <concept>[knowledge-type-category]</concept>
  </concepts>
  <files_read>
    <file>[path/to/file]</file>
  </files_read>
  <files_modified>
    <file>[path/to/file]</file>
  </files_modified>
</observation>
```

### File: `src/sdk/prompts.ts`

Builds the actual prompts sent to the SDK agent.

```typescript
export function buildObservationPrompt(obs: Observation): string {
  return `<observed_from_primary_session>
  <what_happened>${obs.tool_name}</what_happened>
  <occurred_at>${new Date(obs.created_at_epoch).toISOString()}</occurred_at>
  <working_directory>${obs.cwd}</working_directory>
  <parameters>${JSON.stringify(toolInput, null, 2)}</parameters>
  <outcome>${JSON.stringify(toolOutput, null, 2)}</outcome>
</observed_from_primary_session>`;
}
```

---

## Step 5: XML Parsing

### File: `src/sdk/parser.ts`

Parses the SDK agent's XML response into structured data.

```typescript
export function parseObservations(text: string): ParsedObservation[] {
  const observations: ParsedObservation[] = [];

  // Match <observation>...</observation> blocks
  const observationRegex = /<observation>([\s\S]*?)<\/observation>/g;

  let match;
  while ((match = observationRegex.exec(text)) !== null) {
    const obsContent = match[1];

    // Extract all fields
    const type = extractField(obsContent, 'type');
    const title = extractField(obsContent, 'title');
    const subtitle = extractField(obsContent, 'subtitle');
    const narrative = extractField(obsContent, 'narrative');
    const facts = extractArrayElements(obsContent, 'facts', 'fact');
    const concepts = extractArrayElements(obsContent, 'concepts', 'concept');
    const files_read = extractArrayElements(obsContent, 'files_read', 'file');
    const files_modified = extractArrayElements(obsContent, 'files_modified', 'file');

    // Validate type against mode's valid types
    const mode = ModeManager.getInstance().getActiveMode();
    const validTypes = mode.observation_types.map(t => t.id);

    observations.push({
      type: validTypes.includes(type) ? type : validTypes[0],
      title, subtitle, facts, narrative, concepts, files_read, files_modified
    });
  }

  return observations;
}
```

**Key behaviors:**
- Always saves observations (never skips)
- Falls back to first valid type if type is invalid
- All fields except type are nullable

---

## Step 6: Database Storage

### File: `src/services/worker/agents/ResponseProcessor.ts`

Orchestrates storage after parsing.

```typescript
export async function processAgentResponse(
  text: string,
  session: ActiveSession,
  dbManager: DatabaseManager,
  ...
): Promise<void> {
  // Parse observations and summary
  const observations = parseObservations(text, session.contentSessionId);
  const summary = parseSummary(text, session.sessionDbId);

  // ATOMIC TRANSACTION: Store observations + summary
  const result = sessionStore.storeObservations(
    session.memorySessionId,
    session.project,
    observations,
    summaryForStore,
    session.lastPromptNumber,
    discoveryTokens,
    originalTimestamp
  );

  // Sync to ChromaDB (fire-and-forget)
  for (let i = 0; i < observations.length; i++) {
    dbManager.getChromaSync().syncObservation(
      result.observationIds[i],
      session.contentSessionId,
      session.project,
      observations[i],
      ...
    );
  }
}
```

### File: `src/services/sqlite/observations/store.ts`

The actual SQLite INSERT.

```typescript
export function storeObservation(
  db: Database,
  memorySessionId: string,
  project: string,
  observation: ObservationInput,
  promptNumber?: number,
  discoveryTokens: number = 0,
  overrideTimestampEpoch?: number
): StoreObservationResult {
  const stmt = db.prepare(`
    INSERT INTO observations
    (memory_session_id, project, type, title, subtitle, facts, narrative, concepts,
     files_read, files_modified, prompt_number, discovery_tokens, created_at, created_at_epoch)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  const result = stmt.run(
    memorySessionId,
    project,
    observation.type,
    observation.title,
    observation.subtitle,
    JSON.stringify(observation.facts),
    observation.narrative,
    JSON.stringify(observation.concepts),
    JSON.stringify(observation.files_read),
    JSON.stringify(observation.files_modified),
    promptNumber || null,
    discoveryTokens,
    timestampIso,
    timestampEpoch
  );

  return { id: Number(result.lastInsertRowid), createdAtEpoch: timestampEpoch };
}
```

---

## Step 7: ChromaDB Sync

### File: `src/services/sync/ChromaSync.ts`

Syncs to vector database for semantic search.

```typescript
async syncObservation(
  obsId: number,
  sessionId: string,
  project: string,
  obs: ParsedObservation,
  promptNumber: number,
  createdAtEpoch: number,
  discoveryTokens: number
): Promise<void> {
  // Build document text for embedding
  const documentText = this.buildObservationDocument(obs);

  // Upsert to ChromaDB
  await this.client.callTool('add_documents', {
    collection_name: 'claude-mem-observations',
    documents: [documentText],
    ids: [`obs-${obsId}`],
    metadatas: [{
      obsId: String(obsId),
      memorySessionId: sessionId,
      project,
      type: obs.type,
      promptNumber: String(promptNumber),
      createdAtEpoch: String(createdAtEpoch)
    }]
  });
}

private buildObservationDocument(obs: ParsedObservation): string {
  const parts: string[] = [];

  if (obs.title) parts.push(obs.title);
  if (obs.subtitle) parts.push(obs.subtitle);
  if (obs.narrative) parts.push(obs.narrative);
  if (obs.facts?.length) parts.push(`Facts: ${obs.facts.join('; ')}`);
  if (obs.concepts?.length) parts.push(`Concepts: ${obs.concepts.join(', ')}`);

  return parts.join('\n\n');
}
```

---

## Summary: Complete Data Flow

1. **PostToolUse hook** catches tool execution
2. **observation.ts** sends data to worker HTTP API
3. **SessionManager** queues message for SDK agent
4. **SDKAgent** feeds tool data to Claude subprocess
5. **Claude (SDK)** generates XML observation using prompts from `code.json`
6. **parser.ts** extracts structured data from XML
7. **ResponseProcessor** orchestrates storage
8. **store.ts** INSERTs into SQLite `observations` table
9. **ChromaSync** upserts to ChromaDB for semantic search

**Data stored per observation:**
- `memory_session_id`: Links to SDK session
- `project`: Project name (from cwd)
- `type`: One of 6 types (bugfix, feature, etc.)
- `title`: Short title
- `subtitle`: One-sentence explanation
- `facts`: JSON array of facts
- `narrative`: Full context
- `concepts`: JSON array of concept tags
- `files_read`: JSON array of file paths
- `files_modified`: JSON array of file paths
- `prompt_number`: Sequence in session
- `discovery_tokens`: Token cost for ROI
- `created_at_epoch`: Timestamp
