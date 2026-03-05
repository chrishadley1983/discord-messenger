# Hybrid Search: Keyword + Vector for Second Brain

## Problem

The Second Brain uses pgvector semantic search (HNSW index on `knowledge_chunks.embedding`) with a default similarity threshold of 0.70 (MCP tool) / 0.75 (SQL function). Exact keyword searches like "Stocks Green" can miss if the embedding similarity falls below the threshold -- the gte-small model may not place a proper noun close enough to the query vector. The old peterbot-mem system handled this with ChromaDB semantic + SQLite keyword fallback.

## Current Architecture

### Database (Supabase PostgreSQL)

- **`knowledge_items`** -- parent records with `title`, `full_text`, `summary`, `topics[]`, `facts`, `concepts`
- **`knowledge_chunks`** -- child records with `content` (text) and `embedding` (vector(384))
- **HNSW index** on `knowledge_chunks.embedding` (migration 007)
- **No tsvector column** and **no GIN text-search index** exist on either table

### Search flow

1. MCP tool `search_knowledge(query, limit, min_similarity)` in `second_brain_mcp.py`
2. Calls `db.semantic_search()` in `domains/second_brain/db.py`
3. Which calls the `search_knowledge` RPC function (plpgsql) via Supabase REST
4. RPC does: HNSW nearest-neighbour scan -> filter by `match_threshold`, `min_decay`, status -> rank by `similarity * decay_score * base_priority`

### Key parameters

| Parameter | Default (SQL) | Default (MCP) |
|-----------|--------------|---------------|
| `match_threshold` | 0.75 | 0.70 |
| `match_count` | 20 | 5 |
| `min_decay` | 0.2 | 0.2 |

## Proposed Solution: Vector-first, Keyword-fallback

Strategy: try vector search first. If results are poor (zero results or all below a "confident" threshold), run a keyword search as fallback. This avoids the overhead of always running two queries while catching the exact-match cases that vector search misses.

### 1. Database Changes

#### a) Add tsvector column to `knowledge_chunks`

```sql
ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
```

Using a **generated stored column** means:
- Automatically maintained on INSERT/UPDATE -- no trigger needed
- Zero application-code changes for writes
- Stored (not virtual) so GIN index is efficient

#### b) Add GIN index for full-text search

```sql
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_fts
    ON knowledge_chunks USING GIN (fts);
```

#### c) Optional: tsvector on `knowledge_items.title`

```sql
ALTER TABLE knowledge_items
    ADD COLUMN IF NOT EXISTS title_fts tsvector
    GENERATED ALWAYS AS (to_tsvector('english', COALESCE(title, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_knowledge_items_title_fts
    ON knowledge_items USING GIN (title_fts);
```

This lets keyword search match on item titles as well as chunk content.

### 2. New SQL Function: `keyword_search_knowledge`

```sql
CREATE OR REPLACE FUNCTION keyword_search_knowledge(
    search_query TEXT,
    match_count INT DEFAULT 20,
    min_decay FLOAT DEFAULT 0.2,
    capture_types TEXT[] DEFAULT NULL,
    exclude_parent UUID DEFAULT NULL
)
RETURNS TABLE (
    chunk_id UUID, parent_id UUID, chunk_index INT, chunk_content TEXT,
    rank FLOAT,
    content_type TEXT, capture_type TEXT, title TEXT,
    source_url TEXT, source_message_id TEXT, source_system TEXT, full_text TEXT,
    summary TEXT, topics TEXT[], base_priority FLOAT, last_accessed_at TIMESTAMPTZ,
    access_count INT, decay_score FLOAT, created_at TIMESTAMPTZ, promoted_at TIMESTAMPTZ,
    status TEXT, facts JSONB, concepts JSONB
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $func$
DECLARE
    tsq tsquery;
BEGIN
    -- Build tsquery: try phrase first, fall back to AND of terms
    tsq := phraseto_tsquery('english', search_query);
    IF tsq IS NULL OR tsq = ''::tsquery THEN
        tsq := plainto_tsquery('english', search_query);
    END IF;

    RETURN QUERY
    SELECT
        kc.id AS chunk_id,
        kc.parent_id,
        kc.chunk_index,
        kc.content AS chunk_content,
        ts_rank_cd(kc.fts, tsq)::FLOAT AS rank,
        ki.content_type, ki.capture_type, ki.title,
        ki.source_url, ki.source_message_id, ki.source_system,
        ki.full_text, ki.summary, ki.topics, ki.base_priority,
        ki.last_accessed_at, ki.access_count, ki.decay_score,
        ki.created_at, ki.promoted_at, ki.status, ki.facts, ki.concepts
    FROM knowledge_chunks kc
    JOIN knowledge_items ki ON kc.parent_id = ki.id
    WHERE kc.fts @@ tsq
      AND ki.status = 'active'
      AND ki.decay_score >= min_decay
      AND (capture_types IS NULL OR ki.capture_type = ANY(capture_types))
      AND (exclude_parent IS NULL OR kc.parent_id != exclude_parent)
    ORDER BY ts_rank_cd(kc.fts, tsq) * ki.decay_score * ki.base_priority DESC
    LIMIT match_count;
END;
$func$;
```

Key design choices:
- Uses `phraseto_tsquery` first (preserves word order for "Stocks Green") with `plainto_tsquery` fallback (AND of terms)
- Same return shape as `search_knowledge` (minus `similarity`, plus `rank`) so Python code can process both result sets with minimal branching
- Same filters (status, decay, capture_types, exclude_parent) as vector search

### 3. Python Changes in `db.py`

Add a new `keyword_search` function alongside `semantic_search`:

```python
async def keyword_search(
    query: str,
    min_decay_score: float = SEARCH_MIN_DECAY,
    capture_types: Optional[list[CaptureType]] = None,
    exclude_parent_id: Optional[UUID] = None,
    limit: int = MAX_SEARCH_RESULTS,
) -> list[SearchResult]:
    """Full-text keyword search against knowledge chunks."""
    params = {
        "search_query": query,
        "match_count": MAX_CHUNKS_PER_SEARCH,
        "min_decay": min_decay_score,
    }
    if capture_types:
        params["capture_types"] = [ct.value for ct in capture_types]
    if exclude_parent_id:
        params["exclude_parent"] = str(exclude_parent_id)

    client = _get_http_client()
    response = await client.post(
        f"{_get_rest_url()}/rpc/keyword_search_knowledge",
        headers=_get_headers(),
        json=params,
    )
    response.raise_for_status()
    data = response.json()

    # Group by parent (same logic as semantic_search, using rank instead of similarity)
    # ... (reuse existing grouping code, set best_similarity = rank for sorting)
```

Add a hybrid orchestrator:

```python
async def hybrid_search(
    query: str,
    min_similarity: float = 0.75,
    min_decay_score: float = SEARCH_MIN_DECAY,
    capture_types: Optional[list[CaptureType]] = None,
    exclude_parent_id: Optional[UUID] = None,
    limit: int = MAX_SEARCH_RESULTS,
    keyword_fallback_threshold: float = 0.80,
) -> list[SearchResult]:
    """Vector search with keyword fallback.

    1. Run semantic search
    2. If best result < keyword_fallback_threshold OR zero results,
       also run keyword search and merge
    """
    results = await semantic_search(
        query=query,
        min_similarity=min_similarity,
        min_decay_score=min_decay_score,
        capture_types=capture_types,
        exclude_parent_id=exclude_parent_id,
        limit=limit,
    )

    needs_keyword = (
        len(results) == 0
        or results[0].best_similarity < keyword_fallback_threshold
    )

    if needs_keyword:
        kw_results = await keyword_search(
            query=query,
            min_decay_score=min_decay_score,
            capture_types=capture_types,
            exclude_parent_id=exclude_parent_id,
            limit=limit,
        )

        # Merge: add keyword results not already in vector results
        seen_ids = {r.item.id for r in results}
        for kr in kw_results:
            if kr.item.id not in seen_ids:
                results.append(kr)
                seen_ids.add(kr.item.id)

    return results[:limit]
```

The `keyword_fallback_threshold` (0.80) is intentionally higher than `min_similarity` (0.75). This means: if the best vector hit is between 0.75-0.80, it's returned but keyword search also runs to see if there's a better exact match. If the best hit is above 0.80, we trust vector search alone.

### 4. MCP Server Changes (`second_brain_mcp.py`)

Minimal change -- swap `db.semantic_search` for `db.hybrid_search`:

```python
@mcp.tool()
async def search_knowledge(query: str, limit: int = 5, min_similarity: float = 0.7) -> str:
    """Search Chris's personal knowledge base using semantic + keyword search.
    ...
    """
    results = await db.hybrid_search(  # Changed from db.semantic_search
        query=query,
        min_similarity=min_similarity,
        limit=limit,
    )
    # ... rest unchanged
```

The MCP tool signature stays the same -- no breaking change for Claude Desktop or Claude Code consumers.

### 5. Migration SQL

Single migration file `migrations/008_add_keyword_search.sql`:

```sql
-- Migration 008: Add full-text search (tsvector) for keyword fallback
--
-- Adds a generated tsvector column + GIN index on knowledge_chunks
-- so keyword search can complement pgvector semantic search.

-- 1. tsvector column on knowledge_chunks (auto-maintained)
ALTER TABLE knowledge_chunks
    ADD COLUMN IF NOT EXISTS fts tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

-- 2. GIN index for fast text search
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_fts
    ON knowledge_chunks USING GIN (fts);

-- 3. Optional: tsvector on knowledge_items.title
ALTER TABLE knowledge_items
    ADD COLUMN IF NOT EXISTS title_fts tsvector
    GENERATED ALWAYS AS (to_tsvector('english', COALESCE(title, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_knowledge_items_title_fts
    ON knowledge_items USING GIN (title_fts);

-- 4. Keyword search function
CREATE OR REPLACE FUNCTION keyword_search_knowledge(
    search_query TEXT,
    match_count INT DEFAULT 20,
    min_decay FLOAT DEFAULT 0.2,
    capture_types TEXT[] DEFAULT NULL,
    exclude_parent UUID DEFAULT NULL
)
RETURNS TABLE (
    chunk_id UUID, parent_id UUID, chunk_index INT, chunk_content TEXT,
    rank FLOAT,
    content_type TEXT, capture_type TEXT, title TEXT,
    source_url TEXT, source_message_id TEXT, source_system TEXT, full_text TEXT,
    summary TEXT, topics TEXT[], base_priority FLOAT, last_accessed_at TIMESTAMPTZ,
    access_count INT, decay_score FLOAT, created_at TIMESTAMPTZ, promoted_at TIMESTAMPTZ,
    status TEXT, facts JSONB, concepts JSONB
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $func$
DECLARE
    tsq tsquery;
BEGIN
    tsq := phraseto_tsquery('english', search_query);
    IF tsq IS NULL OR tsq = ''::tsquery THEN
        tsq := plainto_tsquery('english', search_query);
    END IF;

    RETURN QUERY
    SELECT
        kc.id AS chunk_id,
        kc.parent_id,
        kc.chunk_index,
        kc.content AS chunk_content,
        ts_rank_cd(kc.fts, tsq)::FLOAT AS rank,
        ki.content_type, ki.capture_type, ki.title,
        ki.source_url, ki.source_message_id, ki.source_system,
        ki.full_text, ki.summary, ki.topics, ki.base_priority,
        ki.last_accessed_at, ki.access_count, ki.decay_score,
        ki.created_at, ki.promoted_at, ki.status, ki.facts, ki.concepts
    FROM knowledge_chunks kc
    JOIN knowledge_items ki ON kc.parent_id = ki.id
    WHERE kc.fts @@ tsq
      AND ki.status = 'active'
      AND ki.decay_score >= min_decay
      AND (capture_types IS NULL OR ki.capture_type = ANY(capture_types))
      AND (exclude_parent IS NULL OR kc.parent_id != exclude_parent)
    ORDER BY ts_rank_cd(kc.fts, tsq) * ki.decay_score * ki.base_priority DESC
    LIMIT match_count;
END;
$func$;
```

## Complexity Estimate

| Component | Effort | Notes |
|-----------|--------|-------|
| Migration SQL | Low | Single file, run in Supabase SQL editor. Generated column auto-backfills existing rows. |
| `keyword_search` in `db.py` | Low | ~40 lines, mirrors `semantic_search` structure |
| `hybrid_search` in `db.py` | Low | ~30 lines orchestrator |
| MCP tool change | Trivial | One-line swap from `semantic_search` to `hybrid_search` |
| Testing | Medium | Need to verify: (a) exact keyword matches are found, (b) vector results still dominate when confident, (c) deduplication works |
| **Total** | **Small** | ~2-3 hours including testing |

## Risks & Considerations

1. **Generated column backfill**: Adding a `GENERATED ALWAYS AS` column will rewrite the entire `knowledge_chunks` table. For the current data volume this should complete in seconds, but on a very large table it could lock briefly.

2. **English stemmer limitations**: `to_tsvector('english', ...)` applies English stemming. Proper nouns like "Stocks Green" will be stemmed to "stock" and "green". For exact proper-noun matching, consider also searching with `websearch_to_tsquery` or a raw `ILIKE` fallback. This is a known limitation but still much better than vector-only for keyword queries.

3. **No extra API calls for keyword-only path**: Keyword search does not require an embedding, so the fallback path avoids a HuggingFace API call entirely -- it only hits the database.

4. **Future enhancement -- true RRF (Reciprocal Rank Fusion)**: If both vector and keyword results are desired simultaneously (not just fallback), a single SQL function could run both and merge with RRF scoring. This is more complex but gives the best of both worlds. Deferring this for now in favour of the simpler fallback approach.
