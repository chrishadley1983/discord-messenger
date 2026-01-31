# Risks and Complications

This document identifies potential issues that could complicate modifications to claude-mem.

---

## Schema Risks

### Risk 1: Type Constraint in Database

**Location:** `src/services/sqlite/migrations.ts` (migration004)

**Issue:**
```sql
type TEXT NOT NULL CHECK(type IN ('decision', 'bugfix', 'feature', 'refactor', 'discovery'))
```

The `observations` table has a CHECK constraint that limits `type` to exactly 5 values.

**Impact:**
- Adding new types requires a migration
- The constraint doesn't include 'change' which IS in code.json
- There's a mismatch between schema and mode config

**Mitigation:**
- New migration to DROP and recreate CHECK constraint
- Or remove CHECK constraint entirely (rely on application validation)
- Verify all existing data before migration

### Risk 2: Missing Category Field

**Location:** `src/services/sqlite/migrations.ts`

**Issue:** No `category` field exists in schema. Must be added via migration.

**Impact:**
- Existing observations will have NULL category
- Need default value strategy (likely 'technical')
- Backfill logic may be needed

**Mitigation:**
- Add column with DEFAULT 'technical'
- Optionally run classification on existing observations

### Risk 3: FTS5 Virtual Table Coupling

**Location:** `src/services/sqlite/migrations.ts` (migration006)

**Issue:**
```sql
CREATE VIRTUAL TABLE observations_fts USING fts5(
  title, subtitle, narrative, text, facts, concepts,
  content='observations', content_rowid='id'
);
```

FTS5 table is tightly coupled to observations table via triggers.

**Impact:**
- Adding new columns to observations doesn't auto-add to FTS
- Need to recreate FTS table if adding category to search
- Trigger logic must be updated

**Mitigation:**
- New migration to recreate FTS table with category column
- Update all three triggers (ai, ad, au)

---

## Code Architecture Risks

### Risk 4: Mode Configuration Tightly Coupled

**Locations:**
- `plugin/modes/code.json` - defines observation_types
- `src/sdk/parser.ts` - validates against mode types
- `src/services/context/ContextConfigLoader.ts` - filters by types

**Issue:** Multiple places read and validate observation types. Adding categories means updating all of them.

**Impact:**
- Easy to miss a validation point
- Tests may hardcode type values
- Localized modes (code--ja.json, etc.) need same updates

**Mitigation:**
- Centralize type/category validation in one place
- Update all localized mode files
- Comprehensive test coverage

### Risk 5: ChromaDB Metadata Schema

**Location:** `src/services/sync/ChromaSync.ts`

**Issue:**
```typescript
metadatas: [{
  obsId: String(obsId),
  memorySessionId: sessionId,
  project,
  type: obs.type,
  promptNumber: String(promptNumber),
  createdAtEpoch: String(createdAtEpoch)
}]
```

ChromaDB metadata is a separate schema from SQLite.

**Impact:**
- Adding category requires updating ChromaSync
- Existing ChromaDB documents won't have category metadata
- ChromaDB queries filtering by category won't find old data

**Mitigation:**
- Update syncObservation() to include category
- Either accept old data limitation or rebuild ChromaDB index
- Add migration script for ChromaDB reindexing

### Risk 6: Multiple Agent Implementations

**Locations:**
- `src/services/worker/SDKAgent.ts` - Claude Agent SDK
- `src/services/worker/GeminiAgent.ts` - Gemini fallback
- `src/services/worker/OpenRouterAgent.ts` - OpenRouter fallback

**Issue:** Three different agent implementations, all use same prompts but may have different behaviors.

**Impact:**
- Prompt changes affect all agents
- Response parsing assumes same XML format from all
- Testing needs to cover all three paths

**Mitigation:**
- Focus on SDKAgent (primary path)
- Ensure prompts.ts is the single source for all agents
- Test with primary agent first, then verify alternatives

### Risk 7: Parser Fallback Behavior

**Location:** `src/sdk/parser.ts`

**Issue:**
```typescript
// NOTE FROM THEDOTMACK: ALWAYS save observations - never skip.
// If type is missing or invalid, use first type from mode as fallback
let finalType = fallbackType;
if (type && validTypes.includes(type.trim())) {
  finalType = type.trim();
}
```

Parser has strong "never skip" policy with silent fallbacks.

**Impact:**
- Invalid categories would silently fall back to default
- No logging of fallback usage (hidden data quality issues)
- Hard to debug why observations have wrong category

**Mitigation:**
- Add logging when fallback is used
- Consider explicit "unknown" category instead of silent default
- Add validation metrics/alerts

---

## Retrieval Risks

### Risk 8: Observation Compiler SQL Complexity

**Location:** `src/services/context/ObservationCompiler.ts`

**Issue:**
```sql
WHERE project = ?
  AND type IN (...)
  AND EXISTS (SELECT 1 FROM json_each(concepts) WHERE value IN (...))
```

Current query is already complex with JSON functions.

**Impact:**
- Adding tiered retrieval significantly increases complexity
- Multiple queries may be needed (core + active + semantic + recent)
- Performance could degrade with large observation counts

**Mitigation:**
- Add database indexes on new columns
- Consider materialized views for common queries
- Profile query performance before/after

### Risk 9: Context Size Limits

**Location:** `src/services/context/ContextBuilder.ts`

**Issue:** No explicit token counting for injected context.

**Impact:**
- Tiered retrieval could inject more tokens than before
- May exceed Claude's context window limits
- Different tiers have different token densities

**Mitigation:**
- Add token counting to context builder
- Implement hard cap with priority-based truncation
- Test with maximum observation counts

---

## Testing Risks

### Risk 10: Limited Test Coverage for Modifications

**Locations:**
- `tests/sqlite/observations.test.ts`
- `tests/worker/agents/response-processor.test.ts`
- `tests/context/observation-compiler.test.ts`

**Issue:** Tests exist but may not cover all edge cases for new features.

**Impact:**
- Schema changes may break existing tests
- New features need new test coverage
- Integration tests may be missing

**Mitigation:**
- Run full test suite before modifications
- Add tests for each new feature
- Consider integration test for full flow

### Risk 11: Localization Complexity

**Location:** `plugin/modes/code--*.json` (30+ localized files)

**Issue:** Every mode file needs same structural changes.

**Impact:**
- Missing a file leaves that language broken
- Translation of new prompt text needed
- Maintenance burden multiplied by locale count

**Mitigation:**
- Script to validate all mode files have same structure
- Consider inheritance/base mode pattern
- Document which prompts need translation

---

## Operational Risks

### Risk 12: Worker State During Migration

**Location:** Worker service at localhost:37777

**Issue:** Worker holds in-memory session state.

**Impact:**
- Schema migration while worker running could cause errors
- Active sessions may fail during upgrade
- Need clean restart procedure

**Mitigation:**
- Document upgrade procedure:
  1. Stop Claude Code
  2. Run migrations
  3. Restart worker
  4. Restart Claude Code

### Risk 13: ChromaDB Availability

**Location:** `src/services/sync/ChromaSync.ts`

**Issue:** ChromaDB is optional (degrades gracefully if unavailable).

**Impact:**
- Semantic search tier depends on ChromaDB
- If ChromaDB unavailable, tiered retrieval falls back
- Need clear fallback behavior

**Mitigation:**
- Document that semantic tier requires ChromaDB
- Ensure graceful degradation tested
- Consider making ChromaDB required for Peterbot

---

## Summary: Risk Priority

| Risk | Severity | Likelihood | Priority |
|------|----------|------------|----------|
| Type CHECK constraint | High | Certain | **P0** - Must fix |
| Missing category field | High | Certain | **P0** - Must add |
| FTS5 coupling | Medium | Likely | **P1** - Plan for |
| ChromaDB metadata | Medium | Certain | **P1** - Plan for |
| Mode config coupling | Medium | Likely | **P1** - Be careful |
| Parser fallbacks | Low | Possible | **P2** - Monitor |
| SQL complexity | Medium | Possible | **P2** - Profile |
| Test coverage | Medium | Likely | **P2** - Add tests |
| Localization | Low | Certain | **P3** - Automate |
| Worker state | Low | Possible | **P3** - Document |

---

## Recommended Pre-Work

Before starting modifications:

1. **Backup database** - ~/.claude-mem/memory.db
2. **Run full test suite** - `npm test`
3. **Document current schema** - `sqlite3 memory.db .schema`
4. **Check all mode files** have consistent structure
5. **Verify ChromaDB state** - May need rebuild anyway
