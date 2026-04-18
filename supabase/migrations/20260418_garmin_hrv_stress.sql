-- Add HRV, stress, and sleep_score columns to garmin_daily_summary.
-- These power the fitness advisor's recovery assessment rules.
--
-- hrv_weekly_avg / hrv_last_night: from garth.DailyHRV (milliseconds)
-- hrv_status: Garmin's own status label (e.g. "BALANCED", "LOW")
-- avg_stress: from garth.DailyStress.overall_stress_level (0-100)
-- sleep_score: may already exist as a dynamic column from PostgREST
--   upserts; this ensures a proper typed column with a default.

ALTER TABLE garmin_daily_summary
  ADD COLUMN IF NOT EXISTS hrv_weekly_avg  INTEGER,
  ADD COLUMN IF NOT EXISTS hrv_last_night  INTEGER,
  ADD COLUMN IF NOT EXISTS hrv_status      TEXT,
  ADD COLUMN IF NOT EXISTS sleep_score     INTEGER;

-- avg_stress column already exists in the CREATE TABLE but was never populated.
-- No ALTER needed for it — just confirming it's there.

COMMENT ON COLUMN garmin_daily_summary.hrv_weekly_avg IS 'HRV 7-day rolling average (ms) from Garmin';
COMMENT ON COLUMN garmin_daily_summary.hrv_last_night IS 'HRV from last night (ms) from Garmin';
COMMENT ON COLUMN garmin_daily_summary.hrv_status IS 'Garmin HRV status label (BALANCED, LOW, etc.)';
