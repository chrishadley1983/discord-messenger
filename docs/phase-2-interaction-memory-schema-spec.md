# Phase 2: Interaction Memory Schema Design - Technical Spec

**Project:** Peterbot memory system  
**Purpose:** Design the schema, categories, and integration points for personality memory  
**Prerequisite:** Phase 1 complete (claude-mem internals documented)  
**Time estimate:** 2-3 hours design, then review  
**Risk:** Medium - design decisions lock in implementation approach

---

## Phase 1 Key Findings Summary

| Component | Location | Current State |
|-----------|----------|---------------|
| Compression prompts | `plugin/modes/code.json` → `prompts` | Code-focused only |
| Observation types | `plugin/modes/code.json` → `observation_types` | 6 types (bugfix, feature, etc.) |
| Storage schema | `src/services/sqlite/migrations.ts` | No category field |
| Parser | `src/sdk/parser.ts` | Extracts type, not category |
| Retrieval | `src/services/context/ObservationCompiler.ts` | Most recent N, type/concept filter |
| Injection | `src/services/context/sections/TimelineRenderer.ts` | Timeline format |

**Critical risks identified:**
- Database CHECK constraint mismatch (missing 'change' type)
- ChromaDB metadata doesn't include category
- FTS5 table tightly coupled to schema

---

## Architecture Decision: Fork vs Mode

### Option A: Fork Entire Plugin
- Separate codebase (peterbot-mem)
- Full control, can diverge completely
- Maintenance burden (can't pull upstream fixes easily)

### Option B: New Mode File Only
- Add `plugin/modes/peterbot.json` alongside `code.json`
- Switch mode via config
- Limited - can't change schema or retrieval logic

### Option C: Fork with Upstream Tracking (Recommended)
- Fork repo as `peterbot-mem`
- Keep `upstream` remote for pulling fixes
- Modify schema, prompts, retrieval
- Peterbot-specific mode file (`peterbot.json`)
- Can cherry-pick upstream improvements

**Decision: Option C**

Rationale:
- Need schema changes (category field, supersede logic)
- Need different retrieval (tiered)
- Need different prompts (personality extraction)
- Still want upstream bugfixes

---

## Architecture Decision: Two Systems or One?

### The Separation Problem

We decided:
- `#claude-code` → Standard claude-mem (technical only)
- `#peterbot` → Forked claude-mem (personality + technical)

But both are Claude Code sessions. Options:

### Option A: Two Separate Installs
```
~/.claude/plugins/claude-mem/          # Standard, for #claude-code
~/.claude/plugins/peterbot-mem/        # Fork, for #peterbot
```
- Clean separation
- But: How does Claude Code know which to use?
- Plugin selection isn't per-session

### Option B: One Install, Mode Switching
```
~/.claude/plugins/peterbot-mem/        # Fork with both modes
  plugin/modes/code.json               # Technical only
  plugin/modes/peterbot.json           # Personality + technical
```
- Single install
- Mode selected by... what? Working directory? Config?

### Option C: One Install, Project-Based Routing (Recommended)
```
~/.claude/plugins/peterbot-mem/
```
- Fork handles ALL projects
- Config file defines which projects get personality extraction
- Default: technical only (backwards compatible)
- Peterbot projects: personality + technical

**Decision: Option C**

New config in `~/.claude-mem/settings.json`:
```json
{
  "personality_projects": ["peterbot", "discord-messenger"],
  "default_mode": "code",
  "personality_mode": "peterbot"
}
```

When observation comes in:
- Check if project is in `personality_projects`
- If yes: use peterbot.json prompts, extract categories
- If no: use code.json prompts, technical only

---

## Architecture Decision: Discord Message Capture

### The Entry Point Problem

Current claude-mem flow:
```
Claude Code tool use → PostToolUse hook → observation.ts → worker
```

But Discord messages aren't tool uses. Options:

### Option A: Fake Tool Events
- Bot sends fake "UserMessage" tool event to worker
- Hacky, but uses existing pipeline

### Option B: New Hook Type
- Add `UserMessage` hook alongside `PostToolUse`
- Claude Code already has this event
- Cleaner integration

### Option C: Direct Worker API (Recommended)
- Bot calls worker HTTP API directly
- New endpoint: `/api/sessions/messages`
- Bypasses hooks entirely for Discord capture

**Decision: Option C**

Rationale:
- Hooks are for Claude Code events
- Discord messages are external
- Direct API is cleaner and more flexible

New worker endpoint:
```
POST /api/sessions/messages
{
  "contentSessionId": "peterbot-session",
  "source": "discord",
  "channel": "#peterbot",
  "timestamp": "2026-01-30T16:00:00Z",
  "userMessage": "I'm stressed about the eBay deadline",
  "assistantResponse": "Let me help you prioritize...",
  "metadata": {
    "messageId": "123456",
    "channelId": "789"
  }
}
```

Worker processes this:
1. Queues for SDK agent (like observation)
2. Uses peterbot.json prompts (personality extraction)
3. Stores with category field
4. Syncs to ChromaDB

---

## Architecture Decision: Recent Chat Buffer

### Where It Lives

The Discord buffer (last N messages) is NOT part of claude-mem. It's:
- Managed by Discord bot
- In-memory (Python list/deque)
- Prepended to messages sent to Claude Code

### Integration Point

```
Discord message arrives
       ↓
Bot layer:
  1. Add to recent_messages buffer
  2. POST to worker /api/sessions/messages (for memory extraction)
  3. Build context (buffer + injected memory)
  4. Send to Claude Code via tmux
       ↓
Claude Code processes (with context)
       ↓
Response captured
       ↓
Bot layer:
  1. Add response to recent_messages buffer
  2. POST to worker (for memory extraction)
  3. Send to Discord
```

### Buffer Configuration (in bot config, not claude-mem)

```python
# domains/peterbot/config.py
RECENT_BUFFER_SIZE = 20  # Last 20 messages
BUFFER_FORMAT = "[{timestamp}] {role}: {content}"
```

---

## Category Taxonomy

### Final Categories

| Category | Description | TTL | Supersede |
|----------|-------------|-----|-----------|
| `identity` | Core facts about user (name, location, family) | Permanent | Yes, within category |
| `preference` | How they like things done | Permanent | Yes, within category |
| `relationship` | People in their life, roles | Permanent | Yes, per person |
| `emotional` | Current feelings, stress, mood | 7 days | Yes, latest wins |
| `project-active` | Current project context | 30 days | Yes, per project |
| `goal` | What they're trying to achieve | Until achieved | Manual or date-based |
| `constraint` | Limitations, budgets, deadlines | Until passed | Yes, within category |
| `technical` | Code patterns, system knowledge | 90 days | No (accumulates) |

### Category Selection Logic

In compression prompt:
```
CATEGORY SELECTION
------------------
Choose the PRIMARY category for this observation:

- identity: Facts about WHO the user is
  Examples: "Lives in Tonbridge", "Has two children", "Runs a LEGO business"

- preference: HOW they want things done
  Examples: "Prefers concise responses", "Likes detailed specs", "Wants to avoid API costs"

- relationship: PEOPLE in their life
  Examples: "Abby is wife", "Max is son", "Reports to [manager]"

- emotional: Current FEELINGS (short-term)
  Examples: "Stressed about deadline", "Excited about Japan trip", "Frustrated with bug"

- project-active: CURRENT work context
  Examples: "Building eBay integration", "Working on Peterbot memory system"

- goal: What they're TRYING TO ACHIEVE
  Examples: "Planning Japan trip April 2026", "Launch Hadley Bricks by Q2"

- constraint: LIMITATIONS or boundaries
  Examples: "Budget of £10k for trip", "Must avoid API costs", "Deadline Friday"

- technical: CODE or SYSTEM knowledge
  Examples: "Auth uses JWT", "Database is Supabase", "Uses Next.js 14"

Default to 'technical' if observation is purely about code/systems with no personal context.
```

---

## Database Migrations

### Migration 008: Add Category Field

```typescript
// src/services/sqlite/migrations.ts

export const migration008: Migration = {
  version: 8,
  up: (db: Database) => {
    // Add category column with default
    db.run(`
      ALTER TABLE observations 
      ADD COLUMN category TEXT DEFAULT 'technical'
    `);
    
    // Index for category queries
    db.run(`
      CREATE INDEX IF NOT EXISTS idx_observations_category 
      ON observations(category)
    `);
    
    // Composite index for tiered retrieval
    db.run(`
      CREATE INDEX IF NOT EXISTS idx_observations_category_epoch 
      ON observations(category, created_at_epoch DESC)
    `);
  },
  down: (db: Database) => {
    // SQLite doesn't support DROP COLUMN easily
    // Would need table rebuild
  }
};
```

### Migration 009: Add Supersede Fields

```typescript
export const migration009: Migration = {
  version: 9,
  up: (db: Database) => {
    // Supersede tracking
    db.run(`
      ALTER TABLE observations 
      ADD COLUMN superseded_by INTEGER REFERENCES observations(id)
    `);
    
    db.run(`
      ALTER TABLE observations 
      ADD COLUMN is_active INTEGER DEFAULT 1
    `);
    
    // Index for active-only queries
    db.run(`
      CREATE INDEX IF NOT EXISTS idx_observations_active 
      ON observations(is_active) WHERE is_active = 1
    `);
  },
  down: (db: Database) => {}
};
```

### Migration 010: Fix Type CHECK Constraint

```typescript
export const migration010: Migration = {
  version: 10,
  up: (db: Database) => {
    // SQLite can't ALTER CHECK constraints
    // Need to recreate table (or just remove constraint)
    
    // Option: Remove constraint entirely, rely on app validation
    // This requires table rebuild - complex
    
    // Simpler: Just ensure 'change' type works by adding to mode config
    // The CHECK constraint will fail for 'change' - need to handle
    
    // For now, document that 'change' type may fail on old schemas
    // Full fix requires table rebuild migration
  },
  down: (db: Database) => {}
};
```

**Note:** The CHECK constraint issue is pre-existing in claude-mem. For now, we'll work around it by ensuring our new categories don't conflict. The `category` field has no CHECK constraint.

### Migration 011: Update FTS5 for Category

```typescript
export const migration011: Migration = {
  version: 11,
  up: (db: Database) => {
    // Drop old FTS table
    db.run(`DROP TABLE IF EXISTS observations_fts`);
    
    // Recreate with category
    db.run(`
      CREATE VIRTUAL TABLE observations_fts USING fts5(
        title, subtitle, narrative, text, facts, concepts, category,
        content='observations', content_rowid='id'
      )
    `);
    
    // Rebuild triggers (insert)
    db.run(`
      CREATE TRIGGER observations_ai AFTER INSERT ON observations BEGIN
        INSERT INTO observations_fts(rowid, title, subtitle, narrative, text, facts, concepts, category)
        VALUES (new.id, new.title, new.subtitle, new.narrative, new.text, new.facts, new.concepts, new.category);
      END
    `);
    
    // Rebuild triggers (delete)
    db.run(`
      CREATE TRIGGER observations_ad AFTER DELETE ON observations BEGIN
        INSERT INTO observations_fts(observations_fts, rowid, title, subtitle, narrative, text, facts, concepts, category)
        VALUES ('delete', old.id, old.title, old.subtitle, old.narrative, old.text, old.facts, old.concepts, old.category);
      END
    `);
    
    // Rebuild triggers (update)
    db.run(`
      CREATE TRIGGER observations_au AFTER UPDATE ON observations BEGIN
        INSERT INTO observations_fts(observations_fts, rowid, title, subtitle, narrative, text, facts, concepts, category)
        VALUES ('delete', old.id, old.title, old.subtitle, old.narrative, old.text, old.facts, old.concepts, old.category);
        INSERT INTO observations_fts(rowid, title, subtitle, narrative, text, facts, concepts, category)
        VALUES (new.id, new.title, new.subtitle, new.narrative, new.text, new.facts, new.concepts, new.category);
      END
    `);
    
    // Rebuild index from existing data
    db.run(`INSERT INTO observations_fts(observations_fts) VALUES ('rebuild')`);
  },
  down: (db: Database) => {}
};
```

---

## Supersede Rules

### Per-Category Behaviour

| Category | Supersede Trigger | Match Criteria |
|----------|-------------------|----------------|
| `identity` | New fact about same topic | Semantic similarity on title |
| `preference` | New preference about same domain | Semantic similarity on title |
| `relationship` | New info about same person | Extract person name, exact match |
| `emotional` | Any new emotional observation | Category match only (latest wins) |
| `project-active` | New info about same project | Project name in title |
| `goal` | Goal achieved or updated | Semantic similarity |
| `constraint` | Constraint changed or passed | Semantic similarity |
| `technical` | Never (accumulates) | N/A |

### Implementation

```typescript
// src/services/sqlite/observations/supersede.ts

export interface SupersedeConfig {
  category: string;
  enabled: boolean;
  matchStrategy: 'semantic' | 'exact' | 'category-only';
  matchField?: string;  // For exact match
}

export const SUPERSEDE_CONFIG: SupersedeConfig[] = [
  { category: 'identity', enabled: true, matchStrategy: 'semantic' },
  { category: 'preference', enabled: true, matchStrategy: 'semantic' },
  { category: 'relationship', enabled: true, matchStrategy: 'exact', matchField: 'title' },
  { category: 'emotional', enabled: true, matchStrategy: 'category-only' },
  { category: 'project-active', enabled: true, matchStrategy: 'semantic' },
  { category: 'goal', enabled: true, matchStrategy: 'semantic' },
  { category: 'constraint', enabled: true, matchStrategy: 'semantic' },
  { category: 'technical', enabled: false, matchStrategy: 'semantic' },
];

export async function checkAndSupersede(
  db: Database,
  chromaSync: ChromaSync,
  newObs: Observation
): Promise<number[]> {
  const config = SUPERSEDE_CONFIG.find(c => c.category === newObs.category);
  
  if (!config?.enabled) return [];
  
  let supersededIds: number[] = [];
  
  switch (config.matchStrategy) {
    case 'category-only':
      // Supersede ALL active observations in this category
      supersededIds = db.prepare(`
        SELECT id FROM observations 
        WHERE category = ? AND is_active = 1 AND id != ?
      `).all(newObs.category, newObs.id).map(r => r.id);
      break;
      
    case 'exact':
      // Supersede observations with exact field match
      supersededIds = db.prepare(`
        SELECT id FROM observations 
        WHERE category = ? AND ${config.matchField} = ? AND is_active = 1 AND id != ?
      `).all(newObs.category, newObs[config.matchField], newObs.id).map(r => r.id);
      break;
      
    case 'semantic':
      // Use ChromaDB to find similar observations
      const similar = await chromaSync.findSimilar(
        newObs.title + ' ' + newObs.subtitle,
        { category: newObs.category, threshold: 0.85 }
      );
      supersededIds = similar.map(s => s.obsId).filter(id => id !== newObs.id);
      break;
  }
  
  if (supersededIds.length > 0) {
    db.prepare(`
      UPDATE observations 
      SET is_active = 0, superseded_by = ? 
      WHERE id IN (${supersededIds.join(',')})
    `).run(newObs.id);
  }
  
  return supersededIds;
}
```

---

## Prompt Modifications

### New Mode File: `plugin/modes/peterbot.json`

This is a modified version of `code.json` with personality extraction.

Key changes to `prompts` object:

#### System Identity (Modified)

```
You are Peterbot-Mem, a specialized observer for creating searchable memory about BOTH technical work AND personal context.

Your job is to extract:
1. Technical knowledge (what was built, fixed, configured)
2. Personal knowledge (who the user is, what they prefer, how they feel, what they're working toward)

CRITICAL: Capture what you LEARN about the user, not just what they did.
```

#### Recording Focus (Modified)

```
WHAT TO RECORD
--------------

TECHNICAL (same as before):
- What the system NOW DOES differently
- What shipped, was fixed, configured
- Code patterns and architectural decisions

PERSONAL (NEW):
- Facts about the user's identity (name, location, family, job)
- Preferences expressed (how they like things done)
- Relationships mentioned (people in their life)
- Emotional state (stress, excitement, frustration)
- Active projects they're working on
- Goals they're trying to achieve
- Constraints they're operating under (budgets, deadlines, limitations)

EXAMPLES OF PERSONAL OBSERVATIONS:
- "User lives in Tonbridge, Kent" (identity)
- "User prefers concise responses without preamble" (preference)
- "Abby is user's wife" (relationship)
- "User stressed about eBay deadline" (emotional)
- "Working on Hadley Bricks eBay integration" (project-active)
- "Planning family trip to Japan, April 2026" (goal)
- "Wants to avoid API costs where possible" (constraint)
```

#### Category Guidance (New)

```
**category**: The memory category for retrieval. MUST be EXACTLY one of:
  - identity: Core facts about WHO the user is
  - preference: HOW they want things done
  - relationship: PEOPLE in their life (specify the person)
  - emotional: Current FEELINGS (these are short-term)
  - project-active: CURRENT work context
  - goal: What they're TRYING TO ACHIEVE
  - constraint: LIMITATIONS (budgets, deadlines, rules)
  - technical: CODE or SYSTEM knowledge (default for pure code observations)

Choose based on the PRIMARY purpose of the observation.
When in doubt between technical and personal, prefer the personal category.
```

#### Output Format (Modified)

```xml
<observation>
  <type>[ bugfix | feature | refactor | change | discovery | decision ]</type>
  <category>[ identity | preference | relationship | emotional | project-active | goal | constraint | technical ]</category>
  <title>[Short title - for relationships, include the person's name]</title>
  <subtitle>[One sentence explanation (max 24 words)]</subtitle>
  <facts>
    <fact>[Concise, self-contained statement]</fact>
  </facts>
  <narrative>[Full context]</narrative>
  <concepts>
    <concept>[knowledge-type]</concept>
  </concepts>
  <files_read>
    <file>[path if relevant]</file>
  </files_read>
  <files_modified>
    <file>[path if relevant]</file>
  </files_modified>
</observation>
```

#### Message Processing Prompt (New)

For Discord message capture (not tool use), add new prompt:

```
PROCESSING USER MESSAGE
-----------------------
You are observing a conversation between the user and their assistant.

<user_message>
{userMessage}
</user_message>

<assistant_response>
{assistantResponse}
</assistant_response>

Extract any observations from this exchange. Focus on:
1. Personal information the user shared
2. Preferences they expressed
3. Goals or constraints they mentioned
4. Emotional signals (stress, excitement, frustration)
5. Project context

If this is purely a technical question/answer with no personal context, you may output:
<no_observations>No personal or memorable context in this exchange</no_observations>

Otherwise, output one or more <observation> blocks.
```

---

## ChromaDB Updates

### Sync Function Changes

```typescript
// src/services/sync/ChromaSync.ts

async syncObservation(
  obsId: number,
  sessionId: string,
  project: string,
  obs: ParsedObservation,
  promptNumber: number,
  createdAtEpoch: number,
  discoveryTokens: number
): Promise<void> {
  const documentText = this.buildObservationDocument(obs);

  await this.client.callTool('add_documents', {
    collection_name: 'claude-mem-observations',
    documents: [documentText],
    ids: [`obs-${obsId}`],
    metadatas: [{
      obsId: String(obsId),
      memorySessionId: sessionId,
      project,
      type: obs.type,
      category: obs.category || 'technical',  // NEW
      promptNumber: String(promptNumber),
      createdAtEpoch: String(createdAtEpoch),
      isActive: '1'  // NEW - for filtering superseded
    }]
  });
}
```

### Update on Supersede

```typescript
async markSuperseded(obsIds: number[]): Promise<void> {
  for (const obsId of obsIds) {
    await this.client.callTool('update_document_metadata', {
      collection_name: 'claude-mem-observations',
      id: `obs-${obsId}`,
      metadata: { isActive: '0' }
    });
  }
}
```

---

## Tiered Retrieval Design

### Configuration

```typescript
// src/services/context/types.ts

export interface TierConfig {
  core: {
    categories: string[];
    maxCount: number;
  };
  active: {
    categories: string[];
    maxAgeDays: number;
    maxCount: number;
  };
  semantic: {
    enabled: boolean;
    maxCount: number;
  };
  recent: {
    maxCount: number;
  };
}

export const PETERBOT_TIERS: TierConfig = {
  core: {
    categories: ['identity', 'preference', 'relationship'],
    maxCount: 15
  },
  active: {
    categories: ['project-active', 'goal', 'emotional', 'constraint'],
    maxAgeDays: 14,
    maxCount: 15
  },
  semantic: {
    enabled: true,
    maxCount: 10
  },
  recent: {
    maxCount: 10
  }
};
```

### Query Implementation

See EXTENSION_POINTS.md for full implementation. Summary:

1. **Core tier**: Query by category IN (identity, preference, relationship), no time limit
2. **Active tier**: Query by category IN (project-active, goal, emotional, constraint), within 14 days
3. **Semantic tier**: ChromaDB query using current message, exclude already-selected
4. **Recent tier**: Fill remaining slots with most recent, any category

All queries include `WHERE is_active = 1` to exclude superseded.

---

## Integration: Discord Bot Changes

### New Endpoints to Call

```python
# domains/peterbot/memory.py

import aiohttp

WORKER_URL = "http://127.0.0.1:37777"

async def capture_message(
    session_id: str,
    channel: str,
    user_message: str,
    assistant_response: str,
    message_id: str,
    timestamp: str
):
    """Send message pair to worker for memory extraction."""
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"{WORKER_URL}/api/sessions/messages",
            json={
                "contentSessionId": session_id,
                "source": "discord",
                "channel": channel,
                "timestamp": timestamp,
                "userMessage": user_message,
                "assistantResponse": assistant_response,
                "metadata": {
                    "messageId": message_id
                }
            }
        )

async def get_context(session_id: str, current_message: str) -> str:
    """Get memory context for injection."""
    async with aiohttp.ClientSession() as session:
        resp = await session.get(
            f"{WORKER_URL}/api/context/inject",
            params={
                "sessionId": session_id,
                "query": current_message  # For semantic tier
            }
        )
        return await resp.text()
```

### Bot Message Handler

```python
# domains/peterbot/router.py

from .memory import capture_message, get_context
from .config import RECENT_BUFFER_SIZE, SESSION_ID
from collections import deque
import asyncio

recent_messages = []
failed_captures = deque(maxlen=100)  # Retry queue for failed extractions

async def handle_message(content: str, message_id: str, channel: str) -> str:
    timestamp = datetime.now().isoformat()
    
    # Add to recent buffer
    recent_messages.append({
        "timestamp": timestamp,
        "role": "user",
        "content": content
    })
    if len(recent_messages) > RECENT_BUFFER_SIZE:
        recent_messages.pop(0)
    
    # Get memory context (tiered retrieval)
    memory_context = await get_context(SESSION_ID, content)
    
    # Build full context
    recent_text = format_recent_messages(recent_messages)
    full_context = f"{memory_context}\n\n## Recent Conversation\n{recent_text}\n\n---\nCurrent message: {content}"
    
    # Send to Claude Code
    response = send_to_claude_code(full_context)
    
    # Add response to buffer
    recent_messages.append({
        "timestamp": datetime.now().isoformat(),
        "role": "assistant", 
        "content": response
    })
    if len(recent_messages) > RECENT_BUFFER_SIZE:
        recent_messages.pop(0)
    
    # Capture for memory (async with failure queue)
    asyncio.create_task(capture_with_retry(
        SESSION_ID, channel, content, response, message_id, timestamp
    ))
    
    return response

async def capture_with_retry(session_id, channel, content, response, message_id, timestamp):
    """Async capture with failure queue for retries."""
    try:
        await capture_message(session_id, channel, content, response, message_id, timestamp)
    except Exception as e:
        failed_captures.append({
            "session_id": session_id,
            "channel": channel,
            "content": content,
            "response": response,
            "message_id": message_id,
            "timestamp": timestamp,
            "error": str(e),
            "retries": 0
        })

async def retry_failed_captures():
    """Background task to retry failed captures."""
    while True:
        await asyncio.sleep(60)  # Check every minute
        
        retries = []
        while failed_captures:
            item = failed_captures.popleft()
            if item["retries"] < 3:
                try:
                    await capture_message(
                        item["session_id"], item["channel"], 
                        item["content"], item["response"],
                        item["message_id"], item["timestamp"]
                    )
                except:
                    item["retries"] += 1
                    retries.append(item)
        
        # Re-queue still-failing items
        for item in retries:
            failed_captures.append(item)
```

---

## File Summary: What Gets Modified/Created

### New Files

| File | Purpose |
|------|---------|
| `plugin/modes/peterbot.json` | Personality extraction prompts |
| `src/services/sqlite/observations/supersede.ts` | Supersede detection logic |
| `src/services/context/TieredRetrieval.ts` | Tiered query implementation |

### Modified Files

| File | Changes |
|------|---------|
| `src/services/sqlite/migrations.ts` | Add migrations 008-011 |
| `src/sdk/parser.ts` | Extract category field |
| `src/services/sqlite/observations/store.ts` | Store category, call supersede |
| `src/services/sqlite/observations/types.ts` | Add category to types |
| `src/services/sync/ChromaSync.ts` | Include category in metadata |
| `src/services/context/ObservationCompiler.ts` | Use tiered retrieval |
| `src/services/context/ContextBuilder.ts` | Accept current query for semantic |
| `src/services/context/sections/TimelineRenderer.ts` | Group by category |
| `src/services/worker/http/routes/SessionRoutes.ts` | Add /messages endpoint |
| `src/shared/SettingsDefaultsManager.ts` | Add personality_projects config |

---

## Implementation Order

### Phase 3: Modify Compression Prompts
1. Create `peterbot.json` mode file
2. Test prompt changes with sample inputs
3. Verify category extraction works

### Phase 4: Schema & Storage
1. Add migrations (008-011)
2. Update parser for category
3. Update store for category
4. Update ChromaDB sync
5. Test storage flow

### Phase 5: Retrieval & Injection
1. Implement tiered retrieval
2. Update context builder
3. Update injection format
4. Add /messages endpoint

### Phase 6: Integration & Test
1. Wire up Discord bot
2. End-to-end testing
3. Tune prompt quality
4. Tune retrieval balance

---

## Success Criteria

Phase 2 is complete when:

1. ✅ Category taxonomy finalized and documented
2. ✅ Migration SQL written and reviewed
3. ✅ Supersede rules defined per category
4. ✅ Prompt modifications designed
5. ✅ Discord integration points documented
6. ✅ Tiered retrieval logic designed
7. ✅ All architectural decisions made

**Gate:** Ready to implement in Phase 3.

---

## Confirmed Decisions

1. **Emotional TTL:** 7 days ✅

2. **Semantic similarity threshold:** 0.85 for supersede ✅

3. **Message capture:** Async with failure queue ✅
   - Fire-and-forget for zero added latency
   - Failed extractions go to retry queue
   - Background task retries periodically
   - Rationale: Memory is for future sessions, not same-message recall. Recent buffer provides immediate context.

4. **Multi-project:** Single project (`peterbot`) for all Discord observations ✅
   - All Discord chat goes to `peterbot` project bucket
   - Keeps it simple - no parsing project mentions from conversation
   - Peterbot is "personal assistant" context, distinct from technical project work
   - Semantic search can still surface relevant content if needed

5. **Backfill:** Leave existing observations as `technical` ✅
   - Existing claude-mem data is from Claude Code sessions (genuinely technical)
   - Personality observations will come from Discord going forward
   - Avoids complexity and risk for marginal benefit
