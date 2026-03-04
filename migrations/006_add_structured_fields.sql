-- Add structured extraction fields to knowledge_items
-- facts: Array of extracted factual statements from conversations
-- concepts: Array of {label, type, detail} objects for conceptual insights
-- Run in Supabase SQL Editor

-- Add columns
ALTER TABLE knowledge_items
ADD COLUMN IF NOT EXISTS facts JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS concepts JSONB DEFAULT '[]'::jsonb;

-- Add comments
COMMENT ON COLUMN knowledge_items.facts IS 'Extracted factual statements (JSON array of strings)';
COMMENT ON COLUMN knowledge_items.concepts IS 'Extracted concepts: [{label, type, detail}] where type is how-it-works|why-it-exists|gotcha|pattern|trade-off';

-- Update search_knowledge RPC to return new columns
CREATE OR REPLACE FUNCTION search_knowledge(
    query_embedding VECTOR(384),
    match_threshold FLOAT DEFAULT 0.75,
    match_count INT DEFAULT 20,
    min_decay FLOAT DEFAULT 0.2,
    capture_types TEXT[] DEFAULT NULL,
    exclude_parent UUID DEFAULT NULL
)
RETURNS TABLE (
    chunk_id UUID,
    parent_id UUID,
    chunk_index INT,
    chunk_content TEXT,
    similarity FLOAT,
    content_type TEXT,
    capture_type TEXT,
    title TEXT,
    source_url TEXT,
    source_message_id TEXT,
    source_system TEXT,
    full_text TEXT,
    summary TEXT,
    topics TEXT[],
    base_priority FLOAT,
    last_accessed_at TIMESTAMPTZ,
    access_count INT,
    decay_score FLOAT,
    created_at TIMESTAMPTZ,
    promoted_at TIMESTAMPTZ,
    status TEXT,
    facts JSONB,
    concepts JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        kc.id AS chunk_id,
        kc.parent_id,
        kc.chunk_index,
        kc.content AS chunk_content,
        1 - (kc.embedding <=> query_embedding) AS similarity,
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
    FROM knowledge_chunks kc
    JOIN knowledge_items ki ON kc.parent_id = ki.id
    WHERE ki.status = 'active'
      AND ki.decay_score >= min_decay
      AND (capture_types IS NULL OR ki.capture_type = ANY(capture_types))
      AND (exclude_parent IS NULL OR kc.parent_id != exclude_parent)
      AND 1 - (kc.embedding <=> query_embedding) >= match_threshold
    ORDER BY (1 - (kc.embedding <=> query_embedding)) * ki.decay_score * ki.base_priority DESC
    LIMIT match_count;
END;
$$;
