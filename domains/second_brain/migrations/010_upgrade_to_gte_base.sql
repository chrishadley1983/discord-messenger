-- Migration: Upgrade embedding model from gte-small (384-dim) to gte-base (768-dim)
--
-- Steps:
-- 1. Drop HNSW index (can't alter vector dimensions with index)
-- 2. Alter embedding column from VECTOR(384) to VECTOR(768)
-- 3. NULL all existing embeddings (wrong dimensions)
-- 4. Update search_knowledge RPC parameter type
-- 5. Recreate HNSW index
--
-- After running this migration, run scripts/reembed_all.py to regenerate
-- all embeddings with the new model.

-- Step 1: Drop the HNSW index
DROP INDEX IF EXISTS knowledge_chunks_embedding_idx;

-- Step 2: Change vector dimensions
ALTER TABLE knowledge_chunks
    ALTER COLUMN embedding TYPE vector(768);

-- Step 3: NULL all existing embeddings (they're 384-dim, incompatible)
UPDATE knowledge_chunks SET embedding = NULL;

-- Step 4: Recreate the search RPC with new vector dimension
CREATE OR REPLACE FUNCTION search_knowledge(
    query_embedding vector(768),
    match_threshold float DEFAULT 0.75,
    match_count int DEFAULT 20,
    min_decay float DEFAULT 0.2,
    capture_types text[] DEFAULT NULL,
    exclude_parent uuid DEFAULT NULL
)
RETURNS TABLE (
    chunk_id uuid,
    parent_id uuid,
    chunk_index int,
    chunk_content text,
    similarity float,
    content_type text,
    capture_type text,
    title text,
    source_url text,
    source_message_id text,
    source_system text,
    full_text text,
    summary text,
    topics text[],
    base_priority float,
    last_accessed_at timestamptz,
    access_count int,
    decay_score float,
    created_at timestamptz,
    promoted_at timestamptz,
    status text,
    facts jsonb,
    concepts jsonb
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        c.parent_id,
        c.chunk_index,
        c.content AS chunk_content,
        1 - (c.embedding <=> query_embedding) AS similarity,
        ki.content_type,
        ki.capture_type,
        ki.title,
        ki.source_url,
        ki.source_message_id,
        ki.source_system,
        ki.full_text,
        ki.summary,
        ki.topics,
        ki.base_priority,
        ki.last_accessed_at,
        ki.access_count,
        ki.decay_score,
        ki.created_at,
        ki.promoted_at,
        ki.status,
        ki.facts,
        ki.concepts
    FROM knowledge_chunks c
    JOIN knowledge_items ki ON c.parent_id = ki.id
    WHERE
        c.embedding IS NOT NULL
        AND ki.status = 'active'
        AND ki.decay_score >= min_decay
        AND 1 - (c.embedding <=> query_embedding) >= match_threshold
        AND (capture_types IS NULL OR ki.capture_type = ANY(capture_types))
        AND (exclude_parent IS NULL OR c.parent_id != exclude_parent)
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- Step 5: Recreate HNSW index (after re-embedding, this will be populated)
CREATE INDEX knowledge_chunks_embedding_idx
    ON knowledge_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
