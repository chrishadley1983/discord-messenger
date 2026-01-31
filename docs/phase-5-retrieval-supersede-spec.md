# Phase 5: Retrieval, Injection & Supersede Logic

**Project:** Peterbot memory system  
**Purpose:** Implement tiered retrieval, supersede detection, and /messages endpoint  
**Prerequisites:** Phase 3+4 complete (schema, prompts, storage working)  
**Time estimate:** 4-6 hours implementation  

---

## Current State (Post Phase 4)

| Component | Status | Location |
|-----------|--------|----------|
| Category field | ✅ Stored | SQLite + ChromaDB |
| is_active field | ✅ Schema ready | SQLite + ChromaDB metadata |
| Supersede schema | ✅ Columns exist | superseded_by, is_active |
| Retrieval | ❌ Still "most recent N" | ObservationCompiler.ts |
| Supersede logic | ❌ Not implemented | Needs supersede.ts |
| /messages endpoint | ❌ Not implemented | Needs SessionRoutes.ts |
| Category accuracy | ⚠️ Defaults to technical | Needs prompt tuning |

---

## Phase 5 Deliverables

### 5.1 Category Classification Tuning (Priority: High)

**Problem:** Agent defaults to `category: 'technical'` even for personal info like "User's name is Chris Hadley".

**File:** `plugin/modes/peterbot.json`

**Changes to category_guidance prompt:**

```
CATEGORY SELECTION - CRITICAL
-----------------------------
Choose the PRIMARY category. This determines how the memory is retrieved later.

PERSONAL CATEGORIES (use these when you learn about THE USER):
- identity: Facts about WHO the user is (name, location, family, job, company)
  → "User's name is Chris" = identity, NOT technical
  → "User lives in Tonbridge" = identity
  → "User runs Hadley Bricks" = identity

- preference: HOW they want things done (style, communication, approach)
  → "User prefers concise responses" = preference
  → "User likes detailed specs" = preference

- relationship: PEOPLE in their life (always include person's name in title)
  → "Abby is user's wife" = relationship
  → "Max is user's son" = relationship

- emotional: Current FEELINGS (short-term, will expire)
  → "User stressed about deadline" = emotional
  → "User excited about Japan trip" = emotional

- project-active: CURRENT work they're doing
  → "Working on Discord bot" = project-active
  → "Building eBay integration" = project-active

- goal: What they're TRYING TO ACHIEVE (future-oriented)
  → "Planning Japan trip April 2026" = goal
  → "Wants to launch by Q2" = goal

- constraint: LIMITATIONS (budgets, deadlines, rules)
  → "Budget is £10k" = constraint
  → "Deadline is Friday" = constraint

TECHNICAL CATEGORY (use ONLY for code/system knowledge):
- technical: Code patterns, architecture, system behavior
  → "Auth uses JWT tokens" = technical
  → "Database is Supabase" = technical
  → "Fixed race condition in cache" = technical

⚠️ IMPORTANT: If the observation is about THE USER (who they are, what they want, 
how they feel), it is NOT technical. Only use 'technical' for pure code/system facts.

When in doubt: personal > technical
```

**Add explicit examples to output_format prompt:**

```
CATEGORY EXAMPLES:
- Learning user's name → category: identity
- Learning user's preference → category: preference  
- Learning about a person in user's life → category: relationship
- Learning user is stressed/happy → category: emotional
- Learning what user is currently building → category: project-active
- Learning user's future plan → category: goal
- Learning a limitation/deadline → category: constraint
- Learning how code/system works → category: technical
```

---

### 5.2 Tiered Retrieval (Priority: High)

**Goal:** Replace "most recent N" with intelligent tiered selection.

#### ChromaSync API Reference

The existing `queryChroma()` method in `src/services/sync/ChromaSync.ts`:

```typescript
async queryChroma(
  query: string,
  limit: number,
  whereFilter?: Record<string, any>
): Promise<{ ids: number[]; distances: number[]; metadatas: any[] }>
```

- `distances`: Lower = more similar (0 = exact match, 1 = very different)
- `whereFilter`: Supports `{ project, is_active, doc_type, category }` filtering
- Returns SQLite IDs directly (already parsed from `obs_123` format)

#### 5.2.1 Tier Configuration

**File:** `src/services/context/TierConfig.ts` (NEW)

```typescript
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
    minSimilarity: number;
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
    maxCount: 10,
    minSimilarity: 0.7
  },
  recent: {
    maxCount: 10
  }
};

// Total max: 15 + 15 + 10 + 10 = 50 observations
```

#### 5.2.2 Tiered Retrieval Implementation

**File:** `src/services/context/TieredRetrieval.ts` (NEW)

```typescript
import { Database } from 'better-sqlite3';
import { TierConfig, PETERBOT_TIERS } from './TierConfig';
import { ChromaSync } from '../sync/ChromaSync';

export interface RetrievedObservation {
  id: number;
  type: string;
  category: string;
  title: string;
  subtitle: string | null;
  narrative: string | null;
  facts: string[];
  created_at_epoch: number;
  tier: 'core' | 'active' | 'semantic' | 'recent';
}

export async function retrieveObservationsTiered(
  db: Database,
  project: string,
  chromaSync: ChromaSync | null,
  currentQuery?: string,
  config: TierConfig = PETERBOT_TIERS
): Promise<RetrievedObservation[]> {
  const results: RetrievedObservation[] = [];
  const seenIds = new Set<number>();

  // TIER 1: Core (always include, no time limit)
  const coreObs = queryCoreObservations(db, project, config.core, seenIds);
  coreObs.forEach(obs => {
    results.push({ ...obs, tier: 'core' });
    seenIds.add(obs.id);
  });

  // TIER 2: Active (recent within maxAgeDays)
  const activeObs = queryActiveObservations(db, project, config.active, seenIds);
  activeObs.forEach(obs => {
    results.push({ ...obs, tier: 'active' });
    seenIds.add(obs.id);
  });

  // TIER 3: Semantic (if query provided and ChromaDB available)
  if (config.semantic.enabled && currentQuery && chromaSync) {
    const semanticObs = await querySemanticObservations(
      chromaSync, 
      project, 
      currentQuery, 
      config.semantic, 
      seenIds
    );
    semanticObs.forEach(obs => {
      results.push({ ...obs, tier: 'semantic' });
      seenIds.add(obs.id);
    });
  }

  // TIER 4: Recent (fill remaining slots)
  const recentObs = queryRecentObservations(db, project, config.recent, seenIds);
  recentObs.forEach(obs => {
    results.push({ ...obs, tier: 'recent' });
    seenIds.add(obs.id);
  });

  return results;
}

function queryCoreObservations(
  db: Database,
  project: string,
  config: TierConfig['core'],
  excludeIds: Set<number>
): Omit<RetrievedObservation, 'tier'>[] {
  const placeholders = config.categories.map(() => '?').join(',');
  const excludeClause = excludeIds.size > 0 
    ? `AND id NOT IN (${[...excludeIds].join(',')})` 
    : '';

  return db.prepare(`
    SELECT id, type, category, title, subtitle, narrative, facts, created_at_epoch
    FROM observations
    WHERE project = ?
      AND category IN (${placeholders})
      AND is_active = 1
      ${excludeClause}
    ORDER BY created_at_epoch DESC
    LIMIT ?
  `).all(project, ...config.categories, config.maxCount) as any[];
}

function queryActiveObservations(
  db: Database,
  project: string,
  config: TierConfig['active'],
  excludeIds: Set<number>
): Omit<RetrievedObservation, 'tier'>[] {
  const placeholders = config.categories.map(() => '?').join(',');
  const cutoffEpoch = Date.now() - (config.maxAgeDays * 24 * 60 * 60 * 1000);
  const excludeClause = excludeIds.size > 0 
    ? `AND id NOT IN (${[...excludeIds].join(',')})` 
    : '';

  return db.prepare(`
    SELECT id, type, category, title, subtitle, narrative, facts, created_at_epoch
    FROM observations
    WHERE project = ?
      AND category IN (${placeholders})
      AND is_active = 1
      AND created_at_epoch > ?
      ${excludeClause}
    ORDER BY created_at_epoch DESC
    LIMIT ?
  `).all(project, ...config.categories, cutoffEpoch, config.maxCount) as any[];
}

async function querySemanticObservations(
  chromaSync: ChromaSync,
  project: string,
  query: string,
  config: TierConfig['semantic'],
  excludeIds: Set<number>
): Promise<Omit<RetrievedObservation, 'tier'>[]> {
  try {
    // Use actual ChromaSync API: queryChroma()
    // Returns { ids: number[], distances: number[], metadatas: any[] }
    // distances: lower = more similar (0 = exact match, 1 = very different)
    const results = await chromaSync.queryChroma(
      query,
      config.maxCount * 2,
      {
        project: project,
        is_active: 1,
        doc_type: 'observation'
      }
    );

    // Convert minSimilarity to maxDistance threshold
    // similarity 0.7 means maxDistance 0.3
    const maxDistance = 1 - config.minSimilarity;

    return results.ids
      .map((id, i) => ({
        id,
        distance: results.distances[i],
        metadata: results.metadatas[i]
      }))
      .filter(r => !excludeIds.has(r.id))
      .filter(r => r.distance <= maxDistance)
      .slice(0, config.maxCount)
      .map(r => ({
        id: r.id,
        type: r.metadata.type as string,
        category: r.metadata.category as string,
        title: r.metadata.title as string,
        subtitle: null,
        narrative: null,
        facts: [],
        created_at_epoch: parseInt(r.metadata.created_at_epoch as string)
      }));
  } catch (error) {
    console.error('Semantic search failed, skipping tier:', error);
    return [];
  }
}

function queryRecentObservations(
  db: Database,
  project: string,
  config: TierConfig['recent'],
  excludeIds: Set<number>
): Omit<RetrievedObservation, 'tier'>[] {
  const excludeClause = excludeIds.size > 0 
    ? `AND id NOT IN (${[...excludeIds].join(',')})` 
    : '';

  return db.prepare(`
    SELECT id, type, category, title, subtitle, narrative, facts, created_at_epoch
    FROM observations
    WHERE project = ?
      AND is_active = 1
      ${excludeClause}
    ORDER BY created_at_epoch DESC
    LIMIT ?
  `).all(project, config.maxCount) as any[];
}
```

#### 5.2.3 Update Context Builder

**File:** `src/services/context/ContextBuilder.ts`

**Change:** Replace call to `queryObservations()` with `retrieveObservationsTiered()`.

```typescript
// OLD
const observations = queryObservations(db, project, config);

// NEW
import { retrieveObservationsTiered } from './TieredRetrieval';

const observations = await retrieveObservationsTiered(
  db.db,
  project,
  chromaSync,
  input?.currentQuery  // Pass current message for semantic search
);
```

#### 5.2.4 Update Context Injection Endpoint

**File:** `src/services/worker/http/routes/ContextRoutes.ts`

Add `query` parameter to `/api/context/inject`:

```typescript
// Accept query param for semantic tier
const query = url.searchParams.get('query') || undefined;

const context = await generateContext({
  projects: projectsList,
  cwd: cwd,
  currentQuery: query  // NEW: for semantic retrieval
});
```

---

### 5.3 Supersede Logic (Priority: Medium)

**Goal:** When a new observation contradicts/updates an old one, mark the old one as superseded.

#### 5.3.1 Supersede Configuration

**File:** `src/services/sqlite/observations/SupersedeConfig.ts` (NEW)

```typescript
export interface SupersedeRule {
  category: string;
  enabled: boolean;
  strategy: 'semantic' | 'exact-title' | 'category-only' | 'none';
  threshold?: number;  // For semantic matching
}

export const SUPERSEDE_RULES: SupersedeRule[] = [
  { category: 'identity', enabled: true, strategy: 'semantic', threshold: 0.85 },
  { category: 'preference', enabled: true, strategy: 'semantic', threshold: 0.85 },
  { category: 'relationship', enabled: true, strategy: 'exact-title' },  // Match person name in title
  { category: 'emotional', enabled: true, strategy: 'category-only' },   // Latest always wins
  { category: 'project-active', enabled: true, strategy: 'semantic', threshold: 0.85 },
  { category: 'goal', enabled: true, strategy: 'semantic', threshold: 0.85 },
  { category: 'constraint', enabled: true, strategy: 'semantic', threshold: 0.85 },
  { category: 'technical', enabled: false, strategy: 'none' },  // Technical accumulates
];

export function getSupersedRule(category: string): SupersedeRule {
  return SUPERSEDE_RULES.find(r => r.category === category) 
    || { category, enabled: false, strategy: 'none' };
}
```

#### 5.3.2 Supersede Detection

**File:** `src/services/sqlite/observations/supersede.ts` (NEW)

```typescript
import { Database } from 'better-sqlite3';
import { ChromaSync } from '../../sync/ChromaSync';
import { getSupersedRule } from './SupersedeConfig';

export interface SupersedeResult {
  supersededIds: number[];
  strategy: string;
}

export async function checkAndSupersede(
  db: Database,
  chromaSync: ChromaSync | null,
  newObservation: {
    id: number;
    category: string;
    title: string;
    project: string;
  }
): Promise<SupersedeResult> {
  const rule = getSupersedRule(newObservation.category);
  
  if (!rule.enabled) {
    return { supersededIds: [], strategy: 'disabled' };
  }

  let supersededIds: number[] = [];

  switch (rule.strategy) {
    case 'category-only':
      // Supersede ALL active observations in this category (emotional)
      supersededIds = findByCategoryOnly(db, newObservation);
      break;

    case 'exact-title':
      // Supersede observations with exact title match (relationship - person name)
      supersededIds = findByExactTitle(db, newObservation);
      break;

    case 'semantic':
      // Supersede semantically similar observations
      if (chromaSync && rule.threshold) {
        supersededIds = await findBySemantic(chromaSync, db, newObservation, rule.threshold);
      }
      break;

    case 'none':
    default:
      return { supersededIds: [], strategy: 'none' };
  }

  // Mark as superseded
  if (supersededIds.length > 0) {
    markSuperseded(db, supersededIds, newObservation.id);
    
    // Update ChromaDB metadata
    if (chromaSync) {
      await chromaSync.markSuperseded(supersededIds);
    }
  }

  return { supersededIds, strategy: rule.strategy };
}

function findByCategoryOnly(
  db: Database,
  newObs: { id: number; category: string; project: string }
): number[] {
  const rows = db.prepare(`
    SELECT id FROM observations
    WHERE project = ?
      AND category = ?
      AND is_active = 1
      AND id != ?
  `).all(newObs.project, newObs.category, newObs.id) as { id: number }[];
  
  return rows.map(r => r.id);
}

function findByExactTitle(
  db: Database,
  newObs: { id: number; category: string; title: string; project: string }
): number[] {
  const rows = db.prepare(`
    SELECT id FROM observations
    WHERE project = ?
      AND category = ?
      AND title = ?
      AND is_active = 1
      AND id != ?
  `).all(newObs.project, newObs.category, newObs.title, newObs.id) as { id: number }[];
  
  return rows.map(r => r.id);
}

async function findBySemantic(
  chromaSync: ChromaSync,
  db: Database,
  newObs: { id: number; category: string; title: string; project: string },
  threshold: number
): Promise<number[]> {
  try {
    // Use actual ChromaSync API: queryChroma()
    // Returns { ids: number[], distances: number[], metadatas: any[] }
    const results = await chromaSync.queryChroma(
      newObs.title,
      10,  // Check top 10 similar
      {
        project: newObs.project,
        category: newObs.category,
        is_active: 1,
        doc_type: 'observation'
      }
    );

    // Convert threshold to maxDistance (threshold 0.85 = maxDistance 0.15)
    const maxDistance = 1 - threshold;

    return results.ids
      .filter((id, i) => results.distances[i] <= maxDistance)
      .filter(id => id !== newObs.id);
  } catch (error) {
    console.error('Semantic supersede check failed:', error);
    return [];
  }
}

function markSuperseded(db: Database, ids: number[], supersededBy: number): void {
  const placeholders = ids.map(() => '?').join(',');
  db.prepare(`
    UPDATE observations
    SET is_active = 0, superseded_by = ?
    WHERE id IN (${placeholders})
  `).run(supersededBy, ...ids);
}
```

#### 5.3.3 Add ChromaDB markSuperseded Method

**File:** `src/services/sync/ChromaSync.ts`

Add new method:

```typescript
async markSuperseded(obsIds: number[]): Promise<void> {
  for (const obsId of obsIds) {
    try {
      await this.collection.update({
        ids: [`obs-${obsId}`],
        metadatas: [{ is_active: 0 }]
      });
    } catch (error) {
      console.error(`Failed to mark obs-${obsId} as superseded in ChromaDB:`, error);
    }
  }
}
```

#### 5.3.4 Integrate Supersede into Store

**File:** `src/services/sqlite/observations/store.ts`

After INSERT, call supersede check:

```typescript
import { checkAndSupersede } from './supersede';

export async function storeObservation(
  db: Database,
  chromaSync: ChromaSync | null,
  // ... existing params
): Promise<StoreObservationResult> {
  // ... existing INSERT logic ...
  
  const newId = Number(result.lastInsertRowid);

  // Check for supersede (async, don't block)
  if (observation.category !== 'technical') {
    checkAndSupersede(db, chromaSync, {
      id: newId,
      category: observation.category,
      title: observation.title || '',
      project
    }).then(result => {
      if (result.supersededIds.length > 0) {
        console.log(`Superseded ${result.supersededIds.length} observations via ${result.strategy}`);
      }
    }).catch(err => {
      console.error('Supersede check failed:', err);
    });
  }

  return { id: newId, createdAtEpoch: timestampEpoch };
}
```

---

### 5.4 /messages Endpoint (Priority: Medium)

**Goal:** Allow Discord bot to submit message pairs for memory extraction.

#### 5.4.1 New Route

**File:** `src/services/worker/http/routes/SessionRoutes.ts`

Add new endpoint:

```typescript
// POST /api/sessions/messages
// Body: { contentSessionId, source, channel, timestamp, userMessage, assistantResponse, metadata }

case '/api/sessions/messages': {
  if (req.method !== 'POST') {
    return new Response('Method not allowed', { status: 405 });
  }

  const body = await req.json();
  const {
    contentSessionId,
    source,
    channel,
    timestamp,
    userMessage,
    assistantResponse,
    metadata
  } = body;

  // Validate required fields
  if (!contentSessionId || !userMessage) {
    return new Response(JSON.stringify({ error: 'Missing required fields' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  // Queue for SDK agent processing
  const session = sessionManager.getOrCreateSession(contentSessionId, 'peterbot');
  
  session.pendingMessages.push({
    type: 'message',
    source: source || 'discord',
    channel: channel || 'unknown',
    timestamp: timestamp || new Date().toISOString(),
    userMessage,
    assistantResponse: assistantResponse || '',
    metadata: metadata || {}
  });

  // Trigger agent processing if not already running
  if (!session.agentRunning) {
    sdkAgent.processSession(session);
  }

  return new Response(JSON.stringify({ 
    status: 'queued',
    sessionId: contentSessionId
  }), {
    status: 202,
    headers: { 'Content-Type': 'application/json' }
  });
}
```

#### 5.4.2 Message Processing Prompt

**File:** `plugin/modes/peterbot.json`

Add new prompt for message processing (different from tool observation):

```json
{
  "message_processing": "PROCESSING CONVERSATION MESSAGE\n---------------------------------\nYou are observing a conversation between the user and their assistant.\n\n<user_message>\n{userMessage}\n</user_message>\n\n<assistant_response>\n{assistantResponse}\n</assistant_response>\n\nExtract any observations from this exchange. Focus on:\n1. Personal information the user shared (identity, preferences)\n2. People they mentioned (relationships)\n3. Goals or constraints they mentioned\n4. Emotional signals (stress, excitement, frustration)\n5. Project context\n\nIMPORTANT: This is conversation, not code work. Personal categories are MORE likely than technical.\n\nIf this is purely small talk with no memorable content, output:\n<no_observations>No memorable content in this exchange</no_observations>\n\nOtherwise, output one or more <observation> blocks with appropriate categories."
}
```

#### 5.4.3 SDK Agent Message Handling

**File:** `src/services/worker/SDKAgent.ts`

Add handling for 'message' type in message generator:

```typescript
if (message.type === 'message') {
  // Use message_processing prompt instead of observation prompt
  const prompt = buildMessagePrompt(message);
  yield { role: 'user', content: prompt };
}
```

**File:** `src/sdk/prompts.ts`

Add message prompt builder:

```typescript
export function buildMessagePrompt(msg: MessageInput): string {
  const mode = ModeManager.getInstance().getActiveMode();
  const template = mode.prompts.message_processing || DEFAULT_MESSAGE_PROMPT;
  
  return template
    .replace('{userMessage}', msg.userMessage)
    .replace('{assistantResponse}', msg.assistantResponse || '(no response yet)');
}
```

---

## Implementation Order

| Step | Task | Files | Est. Time |
|------|------|-------|-----------|
| 1 | Category tuning | peterbot.json | 30 min |
| 2 | Tier config | TierConfig.ts (new) | 15 min |
| 3 | Tiered retrieval | TieredRetrieval.ts (new) | 1 hour |
| 4 | Update ContextBuilder | ContextBuilder.ts | 30 min |
| 5 | Update context endpoint | ContextRoutes.ts | 15 min |
| 6 | Supersede config | SupersedeConfig.ts (new) | 15 min |
| 7 | Supersede logic | supersede.ts (new) | 1 hour |
| 8 | ChromaDB supersede | ChromaSync.ts | 15 min |
| 9 | Integrate into store | store.ts | 30 min |
| 10 | /messages endpoint | SessionRoutes.ts | 45 min |
| 11 | Message prompt | peterbot.json, prompts.ts | 30 min |
| 12 | SDK message handling | SDKAgent.ts | 30 min |
| 13 | Testing | - | 1 hour |

**Total: ~7 hours**

---

## Verification Checklist

### Category Tuning
- [ ] Create observation with personal info → category should NOT be 'technical'
- [ ] "User's name is X" → category: identity
- [ ] "User prefers X" → category: preference

### Tiered Retrieval
- [ ] Core observations (identity/preference/relationship) always included
- [ ] Active observations filtered by 14-day window
- [ ] Semantic tier returns relevant results
- [ ] Total count respects limits

### Supersede Logic
- [ ] New emotional observation supersedes old ones
- [ ] New identity observation with similar title supersedes old
- [ ] Technical observations do NOT supersede
- [ ] Superseded observations have is_active = 0

### /messages Endpoint
- [ ] POST /api/sessions/messages returns 202
- [ ] Message queued for processing
- [ ] Observation created with appropriate category
- [ ] Works with just userMessage (no response yet)

---

## Files Summary

### New Files
| File | Purpose |
|------|---------|
| `src/services/context/TierConfig.ts` | Tier configuration |
| `src/services/context/TieredRetrieval.ts` | Tiered query logic |
| `src/services/sqlite/observations/SupersedeConfig.ts` | Supersede rules |
| `src/services/sqlite/observations/supersede.ts` | Supersede detection |

### Modified Files
| File | Changes |
|------|---------|
| `plugin/modes/peterbot.json` | Category guidance, message_processing prompt |
| `src/services/context/ContextBuilder.ts` | Use tiered retrieval |
| `src/services/worker/http/routes/ContextRoutes.ts` | Add query param |
| `src/services/worker/http/routes/SessionRoutes.ts` | Add /messages endpoint |
| `src/services/sync/ChromaSync.ts` | Add markSuperseded method |
| `src/services/sqlite/observations/store.ts` | Call supersede check |
| `src/sdk/prompts.ts` | Add buildMessagePrompt |
| `src/services/worker/SDKAgent.ts` | Handle message type |

---

## Post-Phase 5: What Remains

Phase 6 (Discord Integration):
- Discord bot memory.py module
- Async capture with failure queue
- Bot message handler integration
- End-to-end testing

Phase 6 is blocked until Discord bot routing is functional.
