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

-- 3. tsvector on knowledge_items.title
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
