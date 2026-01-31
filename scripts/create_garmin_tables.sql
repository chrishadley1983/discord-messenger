-- Create Garmin tables for historical health data storage
-- Run this in Supabase SQL Editor

-- Daily summary table (steps, HR, calories, stress)
CREATE TABLE IF NOT EXISTS garmin_daily_summary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'chris',
    date DATE NOT NULL,
    steps INTEGER,
    steps_goal INTEGER DEFAULT 15000,
    resting_hr INTEGER,
    min_hr INTEGER,
    max_hr INTEGER,
    avg_hr INTEGER,
    total_calories INTEGER,
    active_calories INTEGER,
    avg_stress INTEGER,
    source TEXT DEFAULT 'garmin',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date)
);

-- Sleep data table
CREATE TABLE IF NOT EXISTS garmin_sleep (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'chris',
    date DATE NOT NULL,
    total_hours DECIMAL(4,1),
    quality_score INTEGER,
    deep_hours DECIMAL(4,1),
    light_hours DECIMAL(4,1),
    rem_hours DECIMAL(4,1),
    awake_hours DECIMAL(4,1),
    source TEXT DEFAULT 'garmin',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date)
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_garmin_daily_summary_date ON garmin_daily_summary(user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_garmin_sleep_date ON garmin_sleep(user_id, date DESC);

-- Grant access (adjust based on your RLS setup)
-- ALTER TABLE garmin_daily_summary ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE garmin_sleep ENABLE ROW LEVEL SECURITY;
