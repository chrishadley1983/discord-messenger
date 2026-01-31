-- Create table for tracking shown YouTube videos
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS youtube_shown_videos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    channel_name TEXT,
    category TEXT NOT NULL,
    video_url TEXT NOT NULL,
    summary TEXT,
    shown_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for efficient duplicate checking
CREATE INDEX IF NOT EXISTS idx_youtube_video_id ON youtube_shown_videos(video_id);

-- Index for recency queries
CREATE INDEX IF NOT EXISTS idx_youtube_shown_at ON youtube_shown_videos(shown_at DESC);

-- Index for category-based queries
CREATE INDEX IF NOT EXISTS idx_youtube_category ON youtube_shown_videos(category);
