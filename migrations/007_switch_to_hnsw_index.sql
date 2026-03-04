-- Migration 007: Switch from IVFFlat to HNSW index for knowledge_chunks embeddings
--
-- IVFFlat required periodic rebuilding as data grew (lists parameter must track sqrt(row_count))
-- and had a probes parameter that caused search misses.
-- HNSW is self-maintaining and provides better recall without tuning.
--
-- Also rewrites search_knowledge to use a CTE with index-friendly ORDER BY
-- instead of filtering on computed cosine similarity in WHERE clause.

-- Drop old IVFFlat indexes
DROP INDEX IF EXISTS knowledge_chunks_embedding_idx;
DROP INDEX IF EXISTS idx_knowledge_chunks_embedding;

-- Create HNSW index (self-maintaining, no rebuild needed as data grows)
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding_hnsw
    ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Rewrite search_knowledge function:
-- 1. SECURITY DEFINER to bypass RLS (function runs as owner, not caller)
-- 2. CTE with ORDER BY distance for HNSW index usage
-- 3. Filter and re-rank in outer query
CREATE OR REPLACE FUNCTION search_knowledge(
    query_embedding VECTOR(384),
    match_threshold FLOAT DEFAULT 0.75,
    match_count INT DEFAULT 20,
    min_decay FLOAT DEFAULT 0.2,
    capture_types TEXT[] DEFAULT NULL,
    exclude_parent UUID DEFAULT NULL
)
RETURNS TABLE (
    chunk_id UUID, parent_id UUID, chunk_index INT, chunk_content TEXT,
    similarity FLOAT, content_type TEXT, capture_type TEXT, title TEXT,
    source_url TEXT, source_message_id TEXT, source_system TEXT, full_text TEXT,
    summary TEXT, topics TEXT[], base_priority FLOAT, last_accessed_at TIMESTAMPTZ,
    access_count INT, decay_score FLOAT, created_at TIMESTAMPTZ, promoted_at TIMESTAMPTZ,
    status TEXT, facts JSONB, concepts JSONB
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $func$
BEGIN
    PERFORM set_config('hnsw.ef_search', '100', true);

    RETURN QUERY
    WITH nearest AS (
        -- Use index-friendly ORDER BY for HNSW scan
        SELECT
            kc.id AS chunk_id,
            kc.parent_id,
            kc.chunk_index,
            kc.content AS chunk_content,
            1 - (kc.embedding <=> query_embedding) AS similarity,
            kc.embedding <=> query_embedding AS distance
        FROM knowledge_chunks kc
        ORDER BY kc.embedding <=> query_embedding
        LIMIT match_count * 10  -- fetch extra candidates for filtering
    )
    SELECT
        n.chunk_id, n.parent_id, n.chunk_index, n.chunk_content, n.similarity,
        ki.content_type, ki.capture_type, ki.title,
        ki.source_url, ki.source_message_id, ki.source_system,
        ki.full_text, ki.summary, ki.topics, ki.base_priority,
        ki.last_accessed_at, ki.access_count, ki.decay_score,
        ki.created_at, ki.promoted_at, ki.status, ki.facts, ki.concepts
    FROM nearest n
    JOIN knowledge_items ki ON n.parent_id = ki.id
    WHERE ki.status = 'active'
      AND ki.decay_score >= min_decay
      AND n.similarity >= match_threshold
      AND (capture_types IS NULL OR ki.capture_type = ANY(capture_types))
      AND (exclude_parent IS NULL OR n.parent_id != exclude_parent)
    ORDER BY n.similarity * ki.decay_score * ki.base_priority DESC
    LIMIT match_count;
END;
$func$;
