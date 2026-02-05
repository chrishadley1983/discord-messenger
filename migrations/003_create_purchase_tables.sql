-- Migration: Create purchase tables for browser-based purchasing
-- Phase 9: Browser-Based Purchasing for Peter

-- Spending limits configuration
CREATE TABLE IF NOT EXISTS purchase_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    limit_type TEXT NOT NULL CHECK (limit_type IN ('per_order', 'daily', 'weekly')),
    amount_gbp DECIMAL(10,2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(limit_type)
);

-- Default limits
INSERT INTO purchase_limits (limit_type, amount_gbp) VALUES
    ('per_order', 50.00),
    ('daily', 100.00),
    ('weekly', 250.00)
ON CONFLICT (limit_type) DO NOTHING;

-- Purchase transaction log
CREATE TABLE IF NOT EXISTS purchase_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    url TEXT,
    item_description TEXT,
    amount_gbp DECIMAL(10,2),
    currency TEXT DEFAULT 'GBP',
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'browsing', 'awaiting_confirmation', 'confirmed',
                          'completing', 'completed', 'cancelled', 'failed')),
    confirmation_message_id TEXT,
    user_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    order_reference TEXT,
    delivery_estimate TEXT,
    confirmed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Browser action audit log
CREATE TABLE IF NOT EXISTS browser_action_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_id UUID REFERENCES purchase_log(id) ON DELETE SET NULL,
    session_id TEXT NOT NULL,
    action_type TEXT NOT NULL,  -- navigate, click, type, scroll, screenshot, press, wait
    action_data JSONB,          -- {x, y, text, url, direction, key}
    screenshot_before TEXT,     -- base64 or storage URL
    screenshot_after TEXT,
    page_url TEXT,
    page_title TEXT,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Browser session tracking
CREATE TABLE IF NOT EXISTS browser_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'idle', 'closed', 'error')),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    last_action_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    action_count INTEGER DEFAULT 0,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_purchase_log_status ON purchase_log(status);
CREATE INDEX IF NOT EXISTS idx_purchase_log_created ON purchase_log(created_at);
CREATE INDEX IF NOT EXISTS idx_purchase_log_domain ON purchase_log(domain);
CREATE INDEX IF NOT EXISTS idx_purchase_log_user ON purchase_log(user_id);
CREATE INDEX IF NOT EXISTS idx_purchase_log_session ON purchase_log(session_id);

CREATE INDEX IF NOT EXISTS idx_action_log_session ON browser_action_log(session_id);
CREATE INDEX IF NOT EXISTS idx_action_log_purchase ON browser_action_log(purchase_id);
CREATE INDEX IF NOT EXISTS idx_action_log_created ON browser_action_log(created_at);
CREATE INDEX IF NOT EXISTS idx_action_log_type ON browser_action_log(action_type);

CREATE INDEX IF NOT EXISTS idx_browser_sessions_status ON browser_sessions(status);
CREATE INDEX IF NOT EXISTS idx_browser_sessions_domain ON browser_sessions(domain);
CREATE INDEX IF NOT EXISTS idx_browser_sessions_user ON browser_sessions(user_id);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for purchase_limits updated_at
DROP TRIGGER IF EXISTS update_purchase_limits_updated_at ON purchase_limits;
CREATE TRIGGER update_purchase_limits_updated_at
    BEFORE UPDATE ON purchase_limits
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- RLS policies (service role bypasses these)
ALTER TABLE purchase_limits ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE browser_action_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE browser_sessions ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY "Service role has full access to purchase_limits"
    ON purchase_limits FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role has full access to purchase_log"
    ON purchase_log FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role has full access to browser_action_log"
    ON browser_action_log FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role has full access to browser_sessions"
    ON browser_sessions FOR ALL
    USING (auth.role() = 'service_role');

-- View for spending summary (useful for limit checks)
CREATE OR REPLACE VIEW spending_summary AS
SELECT
    DATE_TRUNC('day', created_at) as date,
    domain,
    COUNT(*) as purchase_count,
    SUM(amount_gbp) as total_gbp
FROM purchase_log
WHERE status = 'completed'
GROUP BY DATE_TRUNC('day', created_at), domain;

-- Function to get remaining limits
CREATE OR REPLACE FUNCTION get_remaining_limits(p_user_id BIGINT DEFAULT NULL)
RETURNS TABLE (
    limit_type TEXT,
    limit_amount DECIMAL(10,2),
    spent DECIMAL(10,2),
    remaining DECIMAL(10,2)
) AS $$
DECLARE
    today_start TIMESTAMPTZ := DATE_TRUNC('day', NOW());
    week_start TIMESTAMPTZ := DATE_TRUNC('week', NOW());
BEGIN
    RETURN QUERY
    WITH limits AS (
        SELECT pl.limit_type, pl.amount_gbp
        FROM purchase_limits pl
    ),
    today_spending AS (
        SELECT COALESCE(SUM(amount_gbp), 0) as total
        FROM purchase_log
        WHERE status = 'completed'
        AND created_at >= today_start
        AND (p_user_id IS NULL OR user_id = p_user_id)
    ),
    week_spending AS (
        SELECT COALESCE(SUM(amount_gbp), 0) as total
        FROM purchase_log
        WHERE status = 'completed'
        AND created_at >= week_start
        AND (p_user_id IS NULL OR user_id = p_user_id)
    )
    SELECT
        l.limit_type,
        l.amount_gbp as limit_amount,
        CASE
            WHEN l.limit_type = 'per_order' THEN 0
            WHEN l.limit_type = 'daily' THEN (SELECT total FROM today_spending)
            WHEN l.limit_type = 'weekly' THEN (SELECT total FROM week_spending)
        END as spent,
        CASE
            WHEN l.limit_type = 'per_order' THEN l.amount_gbp
            WHEN l.limit_type = 'daily' THEN l.amount_gbp - (SELECT total FROM today_spending)
            WHEN l.limit_type = 'weekly' THEN l.amount_gbp - (SELECT total FROM week_spending)
        END as remaining
    FROM limits l;
END;
$$ LANGUAGE plpgsql;
