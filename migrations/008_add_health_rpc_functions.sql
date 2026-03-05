-- Migration 008: Add health monitoring RPC functions
-- Used by domains/second_brain/health.py for health diagnostics

-- Q2: Find active items with zero chunks (unsearchable)
CREATE OR REPLACE FUNCTION get_orphaned_items(item_limit int DEFAULT 5)
RETURNS SETOF knowledge_items AS $$
  SELECT ki.*
  FROM knowledge_items ki
  LEFT JOIN knowledge_chunks kc ON kc.parent_id = ki.id
  WHERE ki.status = 'active'
    AND kc.id IS NULL
  ORDER BY ki.created_at DESC
  LIMIT item_limit;
$$ LANGUAGE sql STABLE;

-- Q3: Decay score distribution across active items
CREATE OR REPLACE FUNCTION get_decay_distribution()
RETURNS TABLE(bucket text, item_count bigint) AS $$
  SELECT
    CASE
      WHEN decay_score < 0.2 THEN 'below_02'
      WHEN decay_score < 0.5 THEN '02_to_05'
      ELSE 'above_05'
    END AS bucket,
    COUNT(*) AS item_count
  FROM knowledge_items
  WHERE status = 'active'
  GROUP BY bucket;
$$ LANGUAGE sql STABLE;

-- Q5: Connection coverage (items with no connections + type breakdown)
CREATE OR REPLACE FUNCTION get_connection_coverage()
RETURNS TABLE(metric text, value bigint) AS $$
  SELECT 'items_no_connections'::text, COUNT(*)::bigint
  FROM knowledge_items ki
  WHERE ki.status = 'active'
    AND NOT EXISTS (
      SELECT 1 FROM knowledge_connections kc
      WHERE kc.item_a_id = ki.id OR kc.item_b_id = ki.id
    )
  UNION ALL
  SELECT connection_type, COUNT(*)
  FROM knowledge_connections
  GROUP BY connection_type;
$$ LANGUAGE sql STABLE;
