-- Create reminders table for one-off scheduled notifications
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    channel_id BIGINT NOT NULL,
    task TEXT NOT NULL,
    run_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    fired_at TIMESTAMPTZ
);

-- Index for fetching pending reminders (startup reload)
CREATE INDEX IF NOT EXISTS idx_reminders_pending
ON reminders(run_at)
WHERE fired_at IS NULL;

-- Index for user's reminders
CREATE INDEX IF NOT EXISTS idx_reminders_user
ON reminders(user_id, run_at)
WHERE fired_at IS NULL;

-- Enable RLS (optional, depends on your security model)
-- ALTER TABLE reminders ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE reminders IS 'One-off reminders set via /remind command or natural language';
COMMENT ON COLUMN reminders.id IS 'Unique reminder ID (remind_XXXXXXXX format)';
COMMENT ON COLUMN reminders.user_id IS 'Discord user ID who set the reminder';
COMMENT ON COLUMN reminders.channel_id IS 'Discord channel ID to post reminder in';
COMMENT ON COLUMN reminders.task IS 'The reminder message/task';
COMMENT ON COLUMN reminders.run_at IS 'When to fire the reminder (UTC)';
COMMENT ON COLUMN reminders.created_at IS 'When the reminder was created';
COMMENT ON COLUMN reminders.fired_at IS 'When the reminder was fired (NULL if pending)';
