-- Second Brain: Peter's external knowledge store
-- Run this in Supabase SQL Editor
-- Requires: pgvector extension

-- Enable pgvector extension for embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- Parent items: articles, notes, voice memos, ideas
CREATE TABLE IF NOT EXISTS knowledge_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_type TEXT NOT NULL,          -- 'article', 'note', 'idea', 'voice_memo', 'url', 'document',
                                         -- 'conversation_extract', 'bookmark', 'training_data',
                                         -- 'social_save', 'calendar_event', 'calendar_pattern', 'key_date'
    capture_type TEXT NOT NULL,          -- 'explicit', 'passive', or 'seed'
    title TEXT,
    source_url TEXT,
    source_message_id TEXT,              -- Discord message ID that triggered capture
    source_system TEXT,                  -- 'discord', 'seed:github', 'seed:claude', 'seed:gemini',
                                         -- 'seed:gdrive', 'seed:gcal', 'seed:email', 'seed:bookmarks',
                                         -- 'seed:garmin', 'seed:instagram'
    full_text TEXT,                      -- Complete content (for reading later)
    summary TEXT,                        -- AI-generated 2-3 sentences (explicit only)
    topics TEXT[],                       -- Auto-extracted tags

    -- Retrieval priority & decay
    base_priority FLOAT DEFAULT 1.0,     -- 1.0 for explicit, 0.3 for passive, 0.8 for seed
    last_accessed_at TIMESTAMPTZ,        -- Boosted when retrieved
    access_count INT DEFAULT 0,          -- Times retrieved
    decay_score FLOAT DEFAULT 1.0,       -- Computed: decays over time, boosted on access

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT now(),
    promoted_at TIMESTAMPTZ,             -- When passive was promoted to explicit

    -- Status
    status TEXT DEFAULT 'active'         -- 'active', 'archived'
);

-- Searchable chunks with embeddings (explicit saves only)
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id UUID REFERENCES knowledge_items(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,               -- Chunk text (~300 words)
    embedding VECTOR(384),               -- Supabase gte-small (built-in, zero cost)
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Connection discovery log
CREATE TABLE IF NOT EXISTS knowledge_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_a_id UUID REFERENCES knowledge_items(id) ON DELETE CASCADE,
    item_b_id UUID REFERENCES knowledge_items(id) ON DELETE CASCADE,
    connection_type TEXT NOT NULL,        -- 'semantic', 'topic_overlap', 'cross_domain'
    description TEXT,                     -- AI-generated description of the connection
    similarity_score FLOAT,
    surfaced BOOLEAN DEFAULT false,       -- Has this been shown to Chris?
    surfaced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(item_a_id, item_b_id)
);

-- Index for fast similarity search (IVFFlat for approximate nearest neighbor)
CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_idx
ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Index for decay queries
CREATE INDEX IF NOT EXISTS knowledge_items_decay_idx
ON knowledge_items (decay_score DESC, status);

-- Index for topic filtering (GIN for array containment queries)
CREATE INDEX IF NOT EXISTS knowledge_items_topics_idx
ON knowledge_items USING gin (topics);

-- Index for capture type filtering
CREATE INDEX IF NOT EXISTS knowledge_items_capture_type_idx
ON knowledge_items (capture_type, status);

-- Index for source system filtering (seed imports)
CREATE INDEX IF NOT EXISTS knowledge_items_source_system_idx
ON knowledge_items (source_system);

-- Index for created_at (recent items queries)
CREATE INDEX IF NOT EXISTS knowledge_items_created_at_idx
ON knowledge_items (created_at DESC);

-- Index for chunk parent lookups
CREATE INDEX IF NOT EXISTS knowledge_chunks_parent_idx
ON knowledge_chunks (parent_id);

-- Index for connection lookups
CREATE INDEX IF NOT EXISTS knowledge_connections_item_a_idx
ON knowledge_connections (item_a_id);

CREATE INDEX IF NOT EXISTS knowledge_connections_item_b_idx
ON knowledge_connections (item_b_id);

-- Index for unsurfaced connections (weekly digest)
CREATE INDEX IF NOT EXISTS knowledge_connections_unsurfaced_idx
ON knowledge_connections (surfaced, created_at DESC)
WHERE surfaced = false;

-- Comments for documentation
COMMENT ON TABLE knowledge_items IS 'Peter Second Brain - parent knowledge items (articles, notes, ideas)';
COMMENT ON TABLE knowledge_chunks IS 'Searchable text chunks with embeddings for semantic search';
COMMENT ON TABLE knowledge_connections IS 'Discovered connections between knowledge items';

COMMENT ON COLUMN knowledge_items.capture_type IS 'explicit (user !save), passive (auto-detected), seed (bulk import)';
COMMENT ON COLUMN knowledge_items.base_priority IS '1.0 explicit, 0.3 passive, 0.8 seed';
COMMENT ON COLUMN knowledge_items.decay_score IS 'Computed score: decays over time (90-day half-life), boosted on access';
COMMENT ON COLUMN knowledge_chunks.embedding IS 'Supabase gte-small embeddings (384 dimensions, built-in)';
COMMENT ON COLUMN knowledge_connections.connection_type IS 'semantic (embedding match), topic_overlap (shared tags), cross_domain (different domains but related)';

-- =============================================================================
-- RPC FUNCTIONS
-- =============================================================================

-- Semantic search function
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
    status TEXT
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
        ki.status
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

-- Get topic counts function
CREATE OR REPLACE FUNCTION get_topic_counts()
RETURNS TABLE (topic TEXT, count BIGINT)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT unnest(ki.topics) AS topic, COUNT(*) AS count
    FROM knowledge_items ki
    WHERE ki.status = 'active'
    GROUP BY unnest(ki.topics)
    ORDER BY count DESC;
END;
$$;

-- Get fading but relevant items (connected to recently accessed items)
CREATE OR REPLACE FUNCTION get_fading_but_relevant(item_limit INT DEFAULT 5)
RETURNS SETOF knowledge_items
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT ki.*
    FROM knowledge_items ki
    JOIN knowledge_connections kc ON ki.id = kc.item_a_id OR ki.id = kc.item_b_id
    WHERE ki.decay_score < 0.3
      AND ki.decay_score > 0.05
      AND ki.status = 'active'
      AND EXISTS (
          SELECT 1 FROM knowledge_items ki2
          WHERE (ki2.id = kc.item_a_id OR ki2.id = kc.item_b_id)
            AND ki2.id != ki.id
            AND ki2.last_accessed_at > NOW() - INTERVAL '30 days'
      )
    ORDER BY ki.decay_score ASC
    LIMIT item_limit;
END;
$$;

-- Generate embedding function (uses Supabase's built-in gte-small)
-- Note: This requires the pg_embedding extension to be enabled
CREATE OR REPLACE FUNCTION generate_embedding(input_text TEXT)
RETURNS VECTOR(384)
LANGUAGE plpgsql
AS $$
DECLARE
    result VECTOR(384);
BEGIN
    -- Use Supabase's built-in embedding function
    -- This requires the ai extension or you can use an edge function
    SELECT embedding INTO result
    FROM ai.embed(
        'gte-small',
        input_text
    );
    RETURN result;
EXCEPTION
    WHEN OTHERS THEN
        -- Return zero vector if embedding fails
        RETURN array_fill(0::float, ARRAY[384])::vector(384);
END;
$$;
