-- Subscriptions tracking tables (finance schema)
-- Covers both personal and Hadley Bricks business subscriptions

CREATE TABLE IF NOT EXISTS finance.subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  provider TEXT,
  scope TEXT NOT NULL CHECK (scope IN ('personal', 'business')),
  category TEXT,

  -- Billing
  amount NUMERIC(10,2) NOT NULL,
  currency TEXT DEFAULT 'GBP',
  frequency TEXT NOT NULL CHECK (frequency IN ('weekly', 'fortnightly', 'monthly', 'quarterly', 'termly', 'annual')),
  billing_day INT,
  next_renewal_date DATE,

  -- Contract
  start_date DATE,
  end_date DATE,
  auto_renew BOOLEAN DEFAULT TRUE,
  cancellation_notice_days INT,

  -- Payment
  payment_method TEXT,
  bank_description_pattern TEXT,

  -- Status
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'paused', 'cancelled', 'trial')),

  -- Metadata
  plan_tier TEXT,
  notes TEXT,
  url TEXT,

  -- Audit
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS finance.subscription_price_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subscription_id UUID REFERENCES finance.subscriptions(id) ON DELETE CASCADE,
  old_amount NUMERIC(10,2),
  new_amount NUMERIC(10,2),
  changed_at DATE NOT NULL,
  source TEXT
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_subscriptions_scope ON finance.subscriptions(scope);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON finance.subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_category ON finance.subscriptions(category);

-- Enable RLS
ALTER TABLE finance.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.subscription_price_history ENABLE ROW LEVEL SECURITY;

-- Service role has full access (dashboard uses service role key)
CREATE POLICY "Service role full access on subscriptions"
  ON finance.subscriptions FOR ALL
  USING (TRUE) WITH CHECK (TRUE);

CREATE POLICY "Service role full access on subscription_price_history"
  ON finance.subscription_price_history FOR ALL
  USING (TRUE) WITH CHECK (TRUE);
