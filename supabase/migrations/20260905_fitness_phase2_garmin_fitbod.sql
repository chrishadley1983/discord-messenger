-- Migration: Fitness Phase 2 — Garmin activities + import provenance
--
--   1. garmin_activities — per-activity sync from Garmin Connect (type,
--      duration, HR, calories). Until now only daily aggregates were stored;
--      per-activity data was prose in knowledge_items. Cardio logs link to
--      these by date + modality so the coach sees real load, not self-report.
--   2. source / garmin_activity_id on workout + cardio sessions so imports
--      (Fitbod CSV, Garmin auto-created cardio) are traceable and dedupable.
--
-- See docs/features/reset-cut-training-log/spec.md (Phase 2)

CREATE TABLE IF NOT EXISTS garmin_activities (
    activity_id TEXT PRIMARY KEY,               -- Garmin's numeric id as text
    user_id TEXT NOT NULL DEFAULT 'chris',
    start_time_local TIMESTAMPTZ NOT NULL,
    date DATE NOT NULL,
    activity_type TEXT NOT NULL,                -- garth type_key: walking, indoor_cycling, stair_climbing, strength_training...
    name TEXT,
    duration_s INT,
    moving_duration_s INT,
    distance_m INT,
    avg_hr INT,
    max_hr INT,
    calories INT,
    elevation_gain_m INT,
    steps INT,
    raw JSONB,
    synced_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_garmin_activities_user_date
    ON garmin_activities(user_id, date DESC);

ALTER TABLE fitness_workout_sessions
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'peter',   -- peter / fitbod / garmin
    ADD COLUMN IF NOT EXISTS external_id TEXT,                        -- fitbod row hash / garmin activity id
    ADD COLUMN IF NOT EXISTS garmin_activity_id TEXT;

ALTER TABLE fitness_cardio_sessions
    ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'peter';    -- peter / garmin

CREATE INDEX IF NOT EXISTS idx_workout_sessions_external
    ON fitness_workout_sessions(user_id, source, external_id);
CREATE INDEX IF NOT EXISTS idx_cardio_sessions_garmin
    ON fitness_cardio_sessions(garmin_activity_id);
