-- Second Brain Audit Fixes
-- Run in Supabase SQL Editor
-- Fixes: RLS, schema consolidation, missing columns, topic counts limit, unused RPC

-- =============================================================================
-- FIX 1: ENABLE ROW LEVEL SECURITY
-- =============================================================================

ALTER TABLE knowledge_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_connections ENABLE ROW LEVEL SECURITY;

-- Single-user system: allow full access via service_role key and authenticated users
-- anon key gets read-only (safety net if key leaks)
CREATE POLICY "service_role_all_items" ON knowledge_items
    FOR ALL USING (auth.role() IN ('service_role', 'authenticated'))
    WITH CHECK (auth.role() IN ('service_role', 'authenticated'));

CREATE POLICY "anon_read_items" ON knowledge_items
    FOR SELECT USING (auth.role() = 'anon');

CREATE POLICY "service_role_all_chunks" ON knowledge_chunks
    FOR ALL USING (auth.role() IN ('service_role', 'authenticated'))
    WITH CHECK (auth.role() IN ('service_role', 'authenticated'));

CREATE POLICY "anon_read_chunks" ON knowledge_chunks
    FOR SELECT USING (auth.role() = 'anon');

CREATE POLICY "service_role_all_connections" ON knowledge_connections
    FOR ALL USING (auth.role() IN ('service_role', 'authenticated'))
    WITH CHECK (auth.role() IN ('service_role', 'authenticated'));

CREATE POLICY "anon_read_connections" ON knowledge_connections
    FOR SELECT USING (auth.role() = 'anon');

-- =============================================================================
-- FIX 2: CONSOLIDATE SCHEMA — add missing columns from domain migration
-- =============================================================================

-- Add columns that exist in domain migration but not in main migration
ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS user_note TEXT;
ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS site_name TEXT;
ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS word_count INTEGER DEFAULT 0;
ALTER TABLE knowledge_items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Add missing columns to knowledge_chunks
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS start_word INTEGER;
ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS end_word INTEGER;

-- Add updated_at trigger (idempotent)
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

-- Add source_url index for dedup lookups (if missing)
CREATE INDEX IF NOT EXISTS idx_knowledge_items_source_url ON knowledge_items(source_url);

-- =============================================================================
-- FIX 3: REPLACE get_topic_counts WITH LIMIT PARAMETER
-- =============================================================================

CREATE OR REPLACE FUNCTION get_topic_counts(max_topics INT DEFAULT 100)
RETURNS TABLE (topic TEXT, count BIGINT)
LANGUAGE sql
AS $$
    SELECT unnest(topics) AS topic, COUNT(*) AS count
    FROM knowledge_items
    WHERE status = 'active'
    GROUP BY topic
    ORDER BY count DESC
    LIMIT max_topics;
$$;

-- =============================================================================
-- FIX 4: REMOVE UNUSED generate_embedding RPC
-- (embed.py uses Edge Function + HuggingFace, not this RPC)
-- =============================================================================

DROP FUNCTION IF EXISTS generate_embedding(TEXT);

-- =============================================================================
-- FIX 5: CLEAN UP DUPLICATE INDEXES
-- Drop domain-migration duplicates that overlap with main migration indexes
-- =============================================================================

-- These are equivalent to existing indexes, just different names:
-- idx_knowledge_items_status ≈ knowledge_items_capture_type_idx (partial overlap)
-- idx_knowledge_items_capture_type ≈ knowledge_items_capture_type_idx
-- idx_knowledge_items_decay_score ≈ knowledge_items_decay_idx
-- idx_knowledge_chunks_parent_id ≈ knowledge_chunks_parent_idx

-- Keep the main migration indexes (more specific composite versions)
-- Only drop true duplicates
DROP INDEX IF EXISTS idx_knowledge_chunks_parent_id;  -- duplicate of knowledge_chunks_parent_idx
DROP INDEX IF EXISTS idx_knowledge_connections_surfaced;  -- duplicate of knowledge_connections_unsurfaced_idx (partial)
