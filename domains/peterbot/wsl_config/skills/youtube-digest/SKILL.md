---
name: youtube-digest
description: Daily YouTube video recommendations in key interest areas
trigger:
  - "youtube"
  - "videos"
  - "anything good on youtube"
scheduled: true
conversational: true
channel: #youtube
---

# YouTube Daily Digest

## Purpose

Daily digest at 9am UK of interesting YouTube videos in Chris's interest areas:
- Lego Investing
- Bricklink Store tips
- Claude Code / AI coding
- AI News
- Interesting documentaries

## Pre-fetched Data

Videos are searched via Grok web_search for each category, filtered against Supabase to avoid duplicates.

```json
{
  "videos_by_category": {
    "lego_investing": [
      {"video_id": "abc123", "url": "https://youtube.com/watch?v=abc123", "title": "Video Title", "context": "Brief context"}
    ],
    "bricklink": [],
    "claude_code": [
      {"video_id": "def456", "url": "https://youtube.com/watch?v=def456", "title": "Claude Code Tutorial", "context": "..."}
    ],
    "ai_news": [],
    "documentaries": []
  },
  "categories": {
    "lego_investing": {"name": "Lego Investing", "emoji": "🧱💰"},
    "bricklink": {"name": "Bricklink Stores", "emoji": "🏪"},
    "claude_code": {"name": "Claude Code", "emoji": "🤖"},
    "ai_news": {"name": "AI News", "emoji": "📰"},
    "documentaries": {"name": "Interesting Documentaries", "emoji": "🎬"}
  },
  "fetch_time": "2026-01-31 09:00"
}
```

## Output Format

```
📺 **YouTube Digest** - Friday, 31 January

**🧱💰 Lego Investing**
• [Video Title](youtube-url) - Brief description
• [Video Title](youtube-url) - Brief description

**🤖 Claude Code**
• [Video Title](youtube-url) - Brief description

**🎬 Worth Watching**
• [Video Title](youtube-url) - Brief description

---
Happy watching! 🍿
```

## Rules

- Use the pre-fetched data - videos are already searched and deduplicated
- 1-2 videos per category max
- Skip categories with empty video arrays
- Use markdown links - NOT raw URLs
- Brief description based on title/context (under 10 words)
- Quality over quantity - pick the best from each category
- If ALL categories are empty, respond with `NO_REPLY`
- Total: 3-6 videos max
