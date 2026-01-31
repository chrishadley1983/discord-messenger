# Extension Points

This document identifies the exact files and functions to modify for each planned feature.

---

## Feature A: Observation Categories

**Goal:** Add a "category" field (identity, preference, emotional, project-active, goal, etc.) to observations.

### 1. Add Category to Mode Configuration

**File:** `plugin/modes/code.json`

**Current:** Has `observation_types` array (bugfix, feature, etc.)

**Change needed:** Add new `observation_categories` array:

```json
{
  "observation_categories": [
    { "id": "identity", "label": "Identity", "description": "Who the user is" },
    { "id": "preference", "label": "Preference", "description": "How they like things" },
    { "id": "emotional", "label": "Emotional", "description": "Feelings and reactions" },
    { "id": "project-active", "label": "Project Active", "description": "Current project context" },
    { "id": "goal", "label": "Goal", "description": "What they want to achieve" },
    { "id": "technical", "label": "Technical", "description": "Code/system knowledge" }
  ]
}
```

### 2. Update Compression Prompts

**File:** `plugin/modes/code.json` → `prompts` object

**Current `type_guidance`:**
```
**type**: MUST be EXACTLY one of these 6 options...
```

**Add new `category_guidance`:**
```
**category**: The memory category for retrieval. MUST be one of:
  - identity: Core facts about who the user is
  - preference: How they prefer things done
  - emotional: Their feelings, reactions, frustrations
  - project-active: Context about current project work
  - goal: What they're trying to achieve
  - technical: Code patterns, system knowledge
```

**Update XML template in prompts:**
```xml
<observation>
  <type>...</type>
  <category>[identity | preference | emotional | project-active | goal | technical]</category>
  ...
</observation>
```

### 3. Add Column to Database Schema

**File:** `src/services/sqlite/migrations.ts`

**Add new migration:**
```typescript
export const migration008: Migration = {
  version: 8,
  up: (db: Database) => {
    db.run(`ALTER TABLE observations ADD COLUMN category TEXT DEFAULT 'technical'`);
    db.run(`CREATE INDEX IF NOT EXISTS idx_observations_category ON observations(category)`);
  },
  down: (db: Database) => {
    // SQLite doesn't support DROP COLUMN easily
  }
};

// Add to migrations array
export const migrations: Migration[] = [..., migration008];
```

### 4. Update Parser

**File:** `src/sdk/parser.ts`

**Function:** `parseObservations()`

**Current:**
```typescript
observations.push({
  type: finalType,
  title, subtitle, facts, narrative, concepts, files_read, files_modified
});
```

**Change to:**
```typescript
const category = extractField(obsContent, 'category') || 'technical';

observations.push({
  type: finalType,
  category,  // NEW
  title, subtitle, facts, narrative, concepts, files_read, files_modified
});
```

### 5. Update Storage

**File:** `src/services/sqlite/observations/store.ts`

**Function:** `storeObservation()`

**Current INSERT:**
```sql
INSERT INTO observations
(memory_session_id, project, type, title, subtitle, ...)
VALUES (?, ?, ?, ?, ?, ...)
```

**Add `category` column to INSERT.**

### 6. Update Types

**File:** `src/services/sqlite/observations/types.ts`

**Add to `ObservationInput` interface:**
```typescript
export interface ObservationInput {
  type: string;
  category: string;  // NEW
  title: string | null;
  // ...
}
```

---

## Feature B: Supersede Logic

**Goal:** New observations in the same category can mark old ones as superseded/replaced.

### 1. Add Schema Fields

**File:** `src/services/sqlite/migrations.ts`

**New migration:**
```typescript
export const migration009: Migration = {
  version: 9,
  up: (db: Database) => {
    db.run(`ALTER TABLE observations ADD COLUMN superseded_by INTEGER REFERENCES observations(id)`);
    db.run(`ALTER TABLE observations ADD COLUMN supersedes INTEGER REFERENCES observations(id)`);
    db.run(`ALTER TABLE observations ADD COLUMN is_active BOOLEAN DEFAULT 1`);
    db.run(`CREATE INDEX IF NOT EXISTS idx_observations_active ON observations(is_active)`);
  }
};
```

### 2. Add Supersede Detection to Compression Prompts

**File:** `plugin/modes/code.json` → `prompts`

**Add to prompt:**
```
SUPERSEDE LOGIC
---------------
If this observation REPLACES a previous belief/preference/fact, indicate it:
- Only for identity, preference, emotional categories
- Example: User now prefers tabs over spaces (supersedes previous spaces preference)

<observation>
  ...
  <supersedes_description>[Optional: what this replaces]</supersedes_description>
</observation>
```

### 3. Add Supersede Logic to Storage

**File:** `src/services/sqlite/observations/store.ts`

**After INSERT, add supersede detection:**
```typescript
// After storing new observation
if (['identity', 'preference', 'emotional'].includes(observation.category)) {
  // Find similar recent observations in same category
  const similar = findSimilarObservations(db, project, observation.category, observation.title);

  if (similar.length > 0) {
    // Mark old ones as superseded
    db.prepare(`
      UPDATE observations
      SET superseded_by = ?, is_active = 0
      WHERE id IN (${similar.map(s => s.id).join(',')})
    `).run(newObsId);
  }
}
```

### 4. Update Retrieval to Filter Superseded

**File:** `src/services/context/ObservationCompiler.ts`

**Function:** `queryObservations()`

**Add to WHERE clause:**
```sql
AND (is_active = 1 OR is_active IS NULL)
```

---

## Feature C: Tiered Retrieval

**Goal:** Instead of "most recent N", implement: core (always) + active (recent) + semantic (matched).

### 1. Define Tier Configuration

**File:** `src/services/context/types.ts`

**Add new types:**
```typescript
export interface TierConfig {
  core: {
    categories: string[];  // ['identity', 'preference']
    maxCount: number;      // Always include up to N
  };
  active: {
    categories: string[];  // ['project-active', 'goal']
    maxAge: number;        // Only if within N days
    maxCount: number;
  };
  semantic: {
    enabled: boolean;
    maxCount: number;
  };
  recent: {
    maxCount: number;      // Fill remaining with recent
  };
}
```

### 2. Update Context Config Loader

**File:** `src/services/context/ContextConfigLoader.ts`

**Add tier configuration loading:**
```typescript
export function loadContextConfig(): ContextConfig {
  // ... existing config ...

  return {
    // ... existing fields ...
    tiers: {
      core: {
        categories: ['identity', 'preference'],
        maxCount: 10
      },
      active: {
        categories: ['project-active', 'goal', 'emotional'],
        maxAge: 7 * 24 * 60 * 60 * 1000,  // 7 days
        maxCount: 15
      },
      semantic: {
        enabled: true,
        maxCount: 10
      },
      recent: {
        maxCount: 15
      }
    }
  };
}
```

### 3. Rewrite Observation Compiler

**File:** `src/services/context/ObservationCompiler.ts`

**Replace `queryObservations()` with tiered approach:**

```typescript
export function queryObservationsTiered(
  db: SessionStore,
  project: string,
  config: ContextConfig,
  currentQuery?: string  // For semantic tier
): Observation[] {
  const results: Observation[] = [];
  const seenIds = new Set<number>();

  // TIER 1: Core (always include, regardless of age)
  const coreObs = db.db.prepare(`
    SELECT * FROM observations
    WHERE project = ? AND category IN (${config.tiers.core.categories.map(() => '?').join(',')})
      AND is_active = 1
    ORDER BY created_at_epoch DESC
    LIMIT ?
  `).all(project, ...config.tiers.core.categories, config.tiers.core.maxCount);

  coreObs.forEach(obs => { results.push(obs); seenIds.add(obs.id); });

  // TIER 2: Active (recent within maxAge)
  const cutoff = Date.now() - config.tiers.active.maxAge;
  const activeObs = db.db.prepare(`
    SELECT * FROM observations
    WHERE project = ? AND category IN (${config.tiers.active.categories.map(() => '?').join(',')})
      AND is_active = 1 AND created_at_epoch > ?
      AND id NOT IN (${[...seenIds].join(',') || '0'})
    ORDER BY created_at_epoch DESC
    LIMIT ?
  `).all(project, ...config.tiers.active.categories, cutoff, config.tiers.active.maxCount);

  activeObs.forEach(obs => { results.push(obs); seenIds.add(obs.id); });

  // TIER 3: Semantic (if query provided and ChromaDB available)
  if (config.tiers.semantic.enabled && currentQuery) {
    const semanticObs = queryChromaForContext(currentQuery, project, config.tiers.semantic.maxCount);
    semanticObs.filter(obs => !seenIds.has(obs.id)).forEach(obs => {
      results.push(obs);
      seenIds.add(obs.id);
    });
  }

  // TIER 4: Recent (fill remaining slots)
  const remaining = config.totalObservationCount - results.length;
  if (remaining > 0) {
    const recentObs = db.db.prepare(`
      SELECT * FROM observations
      WHERE project = ? AND is_active = 1
        AND id NOT IN (${[...seenIds].join(',') || '0'})
      ORDER BY created_at_epoch DESC
      LIMIT ?
    `).all(project, remaining);

    recentObs.forEach(obs => results.push(obs));
  }

  return results;
}
```

### 4. Update Context Builder

**File:** `src/services/context/ContextBuilder.ts`

**Function:** `generateContext()`

**Change:**
```typescript
// OLD
const observations = queryObservations(db, project, config);

// NEW
const observations = queryObservationsTiered(db, project, config, input?.currentQuery);
```

---

## Feature D: Custom Injection Format

**Goal:** Change how context is injected at session start (e.g., structured [PETERBOT CONTEXT] format).

### 1. Update Timeline Renderer

**File:** `src/services/context/sections/TimelineRenderer.ts`

**Current:** Renders observations as timeline with emojis

**Change to structured format:**
```typescript
export function renderTimeline(
  timeline: TimelineItem[],
  fullObservationIds: Set<number>,
  config: ContextConfig,
  cwd: string,
  useColors: boolean
): string[] {
  const output: string[] = [];

  output.push('[PETERBOT CONTEXT]');
  output.push('');

  // Group by category
  const byCategory = groupBy(timeline.filter(t => t.type === 'observation'),
    t => t.data.category);

  // Core Identity
  if (byCategory.identity?.length) {
    output.push('## Core Identity');
    byCategory.identity.forEach(obs => {
      output.push(`- ${obs.data.title}: ${obs.data.subtitle}`);
    });
    output.push('');
  }

  // Preferences
  if (byCategory.preference?.length) {
    output.push('## Preferences');
    byCategory.preference.forEach(obs => {
      output.push(`- ${obs.data.title}`);
    });
    output.push('');
  }

  // Current Context
  output.push('## Current Context');
  const activeObs = [...(byCategory['project-active'] || []), ...(byCategory.goal || [])];
  activeObs.slice(0, 5).forEach(obs => {
    output.push(`- ${obs.data.title}: ${obs.data.subtitle}`);
  });
  output.push('');

  // Recent Technical
  if (byCategory.technical?.length) {
    output.push('## Recent Technical');
    byCategory.technical.slice(0, 10).forEach(obs => {
      output.push(`- [${obs.data.type}] ${obs.data.title}`);
    });
  }

  output.push('[/PETERBOT CONTEXT]');

  return output;
}
```

### 2. Update Header Renderer

**File:** `src/services/context/sections/HeaderRenderer.ts`

**Customize header format as needed.**

### 3. Update Footer Renderer

**File:** `src/services/context/sections/FooterRenderer.ts`

**Customize footer with usage instructions.**

---

## Summary: Files to Modify

| Feature | Primary Files | Secondary Files |
|---------|--------------|-----------------|
| **Categories** | `plugin/modes/code.json`, `src/services/sqlite/migrations.ts`, `src/sdk/parser.ts` | `src/services/sqlite/observations/store.ts`, `src/services/sqlite/observations/types.ts` |
| **Supersede** | `src/services/sqlite/migrations.ts`, `src/services/sqlite/observations/store.ts` | `src/services/context/ObservationCompiler.ts`, `plugin/modes/code.json` |
| **Tiered Retrieval** | `src/services/context/ObservationCompiler.ts`, `src/services/context/ContextConfigLoader.ts` | `src/services/context/types.ts`, `src/services/context/ContextBuilder.ts` |
| **Injection Format** | `src/services/context/sections/TimelineRenderer.ts` | `src/services/context/sections/HeaderRenderer.ts`, `src/services/context/sections/FooterRenderer.ts` |

---

## Implementation Order

1. **Categories** (foundation for everything else)
   - Schema migration first
   - Then prompts
   - Then parser/storage

2. **Tiered Retrieval** (uses categories)
   - Config types
   - Compiler rewrite
   - Builder integration

3. **Supersede Logic** (uses categories, optional)
   - Schema migration
   - Detection logic
   - Retrieval filtering

4. **Injection Format** (cosmetic, last)
   - Renderer changes only
   - No schema changes
