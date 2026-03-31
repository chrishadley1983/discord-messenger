-- Migration: Mood tracking + Daily journal tables

CREATE TABLE IF NOT EXISTS mood_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'chris',
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    score INT NOT NULL CHECK (score BETWEEN 1 AND 10),
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date)
);

CREATE INDEX idx_mood_date ON mood_entries(user_id, date DESC);

CREATE TABLE IF NOT EXISTS journal_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL DEFAULT 'chris',
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, date)
);

CREATE INDEX idx_journal_date ON journal_entries(user_id, date DESC);

CREATE TRIGGER trg_mood_updated
    BEFORE UPDATE ON mood_entries
    FOR EACH ROW EXECUTE FUNCTION update_accountability_timestamp();

CREATE TRIGGER trg_journal_updated
    BEFORE UPDATE ON journal_entries
    FOR EACH ROW EXECUTE FUNCTION update_accountability_timestamp();
