-- Subscription exclusions: patterns flagged as "not a subscription" so the
-- health check stops alerting on them.
CREATE TABLE IF NOT EXISTS finance.subscription_exclusions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description_pattern TEXT NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS
ALTER TABLE finance.subscription_exclusions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow full access via service key"
    ON finance.subscription_exclusions
    FOR ALL
    USING (true)
    WITH CHECK (true);
