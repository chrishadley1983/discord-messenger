-- Second Brain Schema Migration
-- Run this in Supabase SQL Editor

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- KNOWLEDGE ITEMS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS knowledge_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content_type TEXT NOT NULL,
    capture_type TEXT NOT NULL DEFAULT 'explicit',
    title TEXT,
    source_url TEXT,
    source_message_id TEXT,
    source_system TEXT,
    full_text TEXT,
    summary TEXT,
    user_note TEXT,
    site_name TEXT,
    word_count INTEGER DEFAULT 0,
    topics TEXT[] DEFAULT '{}',
    base_priority FLOAT DEFAULT 1.0,
    decay_score FLOAT DEFAULT 1.0,
    access_count INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMPTZ,
    promoted_at TIMESTAMPTZ,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for knowledge_items
CREATE INDEX IF NOT EXISTS idx_knowledge_items_status ON knowledge_items(status);
CREATE INDEX IF NOT EXISTS idx_knowledge_items_capture_type ON knowledge_items(capture_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_items_created_at ON knowledge_items(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_knowledge_items_decay_score ON knowledge_items(decay_score);
CREATE INDEX IF NOT EXISTS idx_knowledge_items_source_url ON knowledge_items(source_url);
CREATE INDEX IF NOT EXISTS idx_knowledge_items_topics ON knowledge_items USING GIN(topics);

-- =============================================================================
-- KNOWLEDGE CHUNKS TABLE (with vector embeddings)
-- =============================================================================
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    parent_id UUID NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384),  -- gte-small produces 384-dim vectors
    start_word INTEGER,
    end_word INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for knowledge_chunks
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_parent_id ON knowledge_chunks(parent_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding ON knowledge_chunks
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- =============================================================================
-- KNOWLEDGE CONNECTIONS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS knowledge_connections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    item_a_id UUID NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
    item_b_id UUID NOT NULL REFERENCES knowledge_items(id) ON DELETE CASCADE,
    connection_type TEXT NOT NULL,
    description TEXT,
    similarity_score FLOAT,
    surfaced BOOLEAN DEFAULT FALSE,
    surfaced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(item_a_id, item_b_id)
);

-- Indexes for knowledge_connections
CREATE INDEX IF NOT EXISTS idx_knowledge_connections_item_a ON knowledge_connections(item_a_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_connections_item_b ON knowledge_connections(item_b_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_connections_surfaced ON knowledge_connections(surfaced);

-- =============================================================================
-- SEMANTIC SEARCH FUNCTION
-- =============================================================================
CREATE OR REPLACE FUNCTION search_knowledge(
    query_embedding vector(384),
    match_threshold FLOAT DEFAULT 0.75,
    match_count INT DEFAULT 20,
    min_decay FLOAT DEFAULT 0.2,
    capture_types TEXT[] DEFAULT NULL,
    exclude_parent UUID DEFAULT NULL
)
RETURNS TABLE (
    chunk_id UUID,
    parent_id UUID,
    chunk_index INTEGER,
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
    access_count INTEGER,
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
        c.id AS chunk_id,
        c.parent_id,
        c.chunk_index,
        c.content AS chunk_content,
        1 - (c.embedding <=> query_embedding) AS similarity,
        i.content_type,
        i.capture_type,
        i.title,
        i.source_url,
        i.source_message_id,
        i.source_system,
        i.full_text,
        i.summary,
        i.topics,
        i.base_priority,
        i.last_accessed_at,
        i.access_count,
        i.decay_score,
        i.created_at,
        i.promoted_at,
        i.status
    FROM knowledge_chunks c
    JOIN knowledge_items i ON c.parent_id = i.id
    WHERE
        i.status = 'active'
        AND i.decay_score >= min_decay
        AND (capture_types IS NULL OR i.capture_type = ANY(capture_types))
        AND (exclude_parent IS NULL OR c.parent_id != exclude_parent)
        AND (1 - (c.embedding <=> query_embedding)) >= match_threshold
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$;

-- =============================================================================
-- TOPIC COUNTS FUNCTION
-- =============================================================================
CREATE OR REPLACE FUNCTION get_topic_counts()
RETURNS TABLE (topic TEXT, count BIGINT)
LANGUAGE sql
AS $$
    SELECT unnest(topics) AS topic, COUNT(*) AS count
    FROM knowledge_items
    WHERE status = 'active'
    GROUP BY topic
    ORDER BY count DESC;
$$;

-- =============================================================================
-- FADING BUT RELEVANT ITEMS FUNCTION
-- =============================================================================
CREATE OR REPLACE FUNCTION get_fading_but_relevant(item_limit INT DEFAULT 5)
RETURNS SETOF knowledge_items
LANGUAGE sql
AS $$
    SELECT ki.*
    FROM knowledge_items ki
    WHERE
        ki.status = 'active'
        AND ki.decay_score < 0.3
        AND ki.decay_score > 0.05
        AND EXISTS (
            SELECT 1
            FROM knowledge_connections kc
            WHERE (kc.item_a_id = ki.id OR kc.item_b_id = ki.id)
        )
    ORDER BY ki.decay_score DESC
    LIMIT item_limit;
$$;

-- =============================================================================
-- ROW LEVEL SECURITY (optional - enable if needed)
-- =============================================================================
-- ALTER TABLE knowledge_items ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE knowledge_connections ENABLE ROW LEVEL SECURITY;

-- Allow public read/write for anon key (adjust as needed)
-- CREATE POLICY "Allow all" ON knowledge_items FOR ALL USING (true);
-- CREATE POLICY "Allow all" ON knowledge_chunks FOR ALL USING (true);
-- CREATE POLICY "Allow all" ON knowledge_connections FOR ALL USING (true);

-- =============================================================================
-- UPDATED_AT TRIGGER
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_updated_at ON knowledge_items;
CREATE TRIGGER set_updated_at
    BEFORE UPDATE ON knowledge_items
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- GRANT PERMISSIONS
-- =============================================================================
GRANT ALL ON knowledge_items TO anon, authenticated;
GRANT ALL ON knowledge_chunks TO anon, authenticated;
GRANT ALL ON knowledge_connections TO anon, authenticated;
