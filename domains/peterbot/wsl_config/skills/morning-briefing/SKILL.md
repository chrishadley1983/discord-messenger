---
name: morning-briefing
description: AI and Claude news morning briefing
trigger:
  - "ai news"
  - "claude news"
  - "briefing"
  - "ai briefing"
  - "morning briefing"
scheduled: true
conversational: true
channel: #ai-briefings
---

# AI Morning Briefing

## Purpose

Daily AI/Claude-focused news briefing. Curate pre-fetched search results into a polished, engaging briefing optimized for Discord.

## Pre-fetched Data Structure

```json
{
  "x_posts": [
    {
      "url": "https://x.com/...",
      "title": "Post summary",
      "context": "Surrounding context...",
      "handle": "@username",
      "markdown_link": "[Post summary](https://x.com/...)"
    }
  ],
  "reddit_posts": [
    {
      "url": "https://reddit.com/...",
      "title": "Discussion title",
      "context": "Discussion context...",
      "subreddit": "r/ClaudeAI",
      "markdown_link": "[Discussion title](https://reddit.com/...)"
    }
  ],
  "web_articles": [
    {
      "url": "https://example.com/...",
      "title": "Article headline",
      "context": "Article context...",
      "markdown_link": "[Article headline](https://example.com/...)"
    }
  ],
  "has_x_data": true,
  "has_reddit_data": true,
  "has_web_data": true,
  "fetch_time": "2026-02-05 07:00"
}
```

## Output Format

**CRITICAL: Use EXACTLY this format. Use the `markdown_link` field from the data - do NOT modify URLs.**

```
**☀️ AI Morning Briefing — Wed 05 Feb 2026**

**📰 NEWS HEADLINES**
> **[Article headline](url)** — Brief one-sentence summary
> **[Article headline](url)** — Brief one-sentence summary
> **[Article headline](url)** — Brief one-sentence summary

**🛠️ CLAUDE CODE CORNER**
> **[Post/article](url)** — One-liner about Claude Code/MCP
> **[Post/article](url)** — One-liner about Claude Code/MCP
> **[Post/article](url)** — One-liner about Claude Code/MCP

**💬 COMMUNITY BUZZ**
> **@handle:** [Summary](url)
> **@handle:** [Summary](url)
> **@handle:** [Summary](url)

**📢 REDDIT ROUNDUP**
> **[Discussion title](url)** (r/subreddit)
> **[Discussion title](url)** (r/subreddit)
> **[Discussion title](url)** (r/subreddit)
```

## Curation Rules

1. **MANDATORY: Use the `markdown_link` field exactly as provided**
   - This ensures URLs are clickable in Discord
   - Never use angle brackets `<url>`
   - Never output plain URLs

2. **3 items per section** (best items only)
   - More focused than 5 items, better readability
   - If fewer than 3 available, use all available

3. **One-liner summaries** -- single sentence, punchy, informative

4. **Section handling:**
   - If `has_x_data` is false: Use fallback for Community Buzz
   - If `has_reddit_data` is false: Use fallback for Reddit Roundup
   - If `has_web_data` is false: Use fallback for News Headlines

5. **Fallback text for empty sections:**
   - NEWS HEADLINES: "No major AI headlines today"
   - CLAUDE CODE CORNER: "Nothing Claude Code specific today -- submit your projects!"
   - COMMUNITY BUZZ: "X is quiet today"
   - REDDIT ROUNDUP: "No Reddit discussions found"

## Content Priorities

**NEWS HEADLINES** (from web_articles):
- Anthropic/Claude announcements first
- AI industry news
- Research findings

**CLAUDE CODE CORNER** (from any source):
- Claude Code features, tips, tools
- MCP servers and integrations
- Community projects using Claude Code
- @ClawdBot/@MoltBot/@OpenClaw mentions

**COMMUNITY BUZZ** (from x_posts):
- Use the `handle` field to show @username
- Interesting AI/Claude takes
- Viral AI coding content

**REDDIT ROUNDUP** (from reddit_posts):
- Use the `subreddit` field
- r/ClaudeAI, r/LocalLLaMA discussions

## Tone

Informative but engaging. Like a knowledgeable friend sharing the best AI news they found. Not robotic, not overly casual.
