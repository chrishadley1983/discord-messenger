-- Migration: Accountability Tracker tables
-- Goals (target + habit), milestones, and progress entries

-- ============================================================
-- GOALS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS accountability_goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'chris',

    -- Core
    title TEXT NOT NULL,
    description TEXT,
    goal_type TEXT NOT NULL CHECK (goal_type IN ('target', 'habit')),
    category TEXT NOT NULL DEFAULT 'general',

    -- Measurement
    metric TEXT NOT NULL,
    current_value NUMERIC DEFAULT 0,
    target_value NUMERIC NOT NULL,
    start_value NUMERIC DEFAULT 0,
    direction TEXT NOT NULL DEFAULT 'up' CHECK (direction IN ('up', 'down')),

    -- Habit-specific
    frequency TEXT CHECK (frequency IN ('daily', 'weekly', 'monthly')),

    -- Timeline
    start_date DATE NOT NULL DEFAULT CURRENT_DATE,
    deadline DATE,

    -- Status
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'abandoned')),
    completed_at TIMESTAMPTZ,

    -- Streaks (habits)
    current_streak INT DEFAULT 0,
    best_streak INT DEFAULT 0,
    last_hit_date DATE,

    -- Auto-update config
    auto_source TEXT,
    auto_query JSONB,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_accountability_goals_active
ON accountability_goals(user_id, status) WHERE status = 'active';

-- ============================================================
-- MILESTONES TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS accountability_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES accountability_goals(id) ON DELETE CASCADE,

    title TEXT NOT NULL,
    target_value NUMERIC NOT NULL,
    reached_at TIMESTAMPTZ,
    celebrated BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_milestones_goal ON accountability_milestones(goal_id);

-- ============================================================
-- PROGRESS TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS accountability_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES accountability_goals(id) ON DELETE CASCADE,

    value NUMERIC NOT NULL,
    delta NUMERIC,
    note TEXT,

    source TEXT NOT NULL DEFAULT 'manual',
    logged_at TIMESTAMPTZ DEFAULT NOW(),
    date DATE DEFAULT CURRENT_DATE
);

CREATE INDEX idx_progress_goal_date ON accountability_progress(goal_id, date DESC);
CREATE INDEX idx_progress_date ON accountability_progress(date DESC);

-- Prevent duplicate auto-updates per day per source
CREATE UNIQUE INDEX idx_progress_dedup
ON accountability_progress(goal_id, date, source)
WHERE source NOT IN ('manual', 'peter_chat');

-- ============================================================
-- Auto-update timestamp trigger
-- ============================================================
CREATE OR REPLACE FUNCTION update_accountability_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_goals_updated
    BEFORE UPDATE ON accountability_goals
    FOR EACH ROW EXECUTE FUNCTION update_accountability_timestamp();
