-- Optimize IVFFlat index: lists=100 -> lists=55 (sqrt of ~3000 rows)
-- Run in Supabase SQL Editor

-- Rebuild embedding index with optimal lists parameter
DROP INDEX IF EXISTS knowledge_chunks_embedding_idx;
CREATE INDEX knowledge_chunks_embedding_idx
ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 55);
