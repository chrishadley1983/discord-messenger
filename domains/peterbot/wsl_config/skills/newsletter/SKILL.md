---
name: newsletter
description: Merged daily morning newsletter — AI news, Claude Code, community, tech, UK, F1, YouTube
trigger:
  - "newsletter"
  - "daily newsletter"
  - "morning newsletter"
  - "ai news"
  - "briefing"
scheduled: true
conversational: true
channel: #ai-news
---

# Daily Newsletter

## Purpose

One merged morning newsletter for the #ai-news channel, replacing the old
separate morning-briefing / news / RSS-briefing / youtube-digest posts.
Curate the pre-fetched data into a single, polished, scannable digest.
It can be long — quality and completeness beat brevity — but every item
must earn its place.

## Pre-fetched Data Structure

```json
{
  "ai_news":     [{"title", "url", "source", "published"}],
  "claude_code": [{"title", "url", "source", "published", "context"}],
  "community":   {"reddit": [{"title", "url", "subreddit"}], "bluesky": [{"title", "url", "handle", "likes"}], "x": [{"url", "text", "context"}]},
  "tech":        [{"title", "url", "source"}],
  "uk":          [{"title", "url", "source"}],
  "sport":       [{"title", "url", "source"}],
  "youtube":     [{"category": "...", "videos": [{"title", "url", "channel_name", "published", "length_minutes", "views"}]}],
  "source_status": {"x": "ok|unavailable...", "reddit": "...", "youtube": "...", "ai_news": "..."},
  "fetch_time":  "YYYY-MM-DD HH:MM"
}
```

All items are already deduplicated against the last 10 days of posts and
filtered for junk domains. URLs are real and verified — use them exactly.

## Output Format

**CRITICAL LINK RULE: every link must be written as `[Title](<url>)` — with
angle brackets INSIDE the parentheses.** This keeps links clickable but
suppresses Discord's preview embeds, which otherwise flood the channel.
Never output a bare URL. Never omit the angle brackets.

```
**☀️ Daily Newsletter — Thursday 2 July 2026**

**🤖 AI NEWS**
• **[Title](<url>)** — one-sentence summary (Source)
• **[Title](<url>)** — one-sentence summary (Source)
(3-5 items)

**🛠️ CLAUDE CODE**
• **[Title](<url>)** — one-sentence summary
(2-4 items — ONLY items genuinely about Claude Code, Claude, MCP, or agentic
coding. Generic HN launches don't belong here; omit the section rather than
pad it with off-topic items)

**💬 COMMUNITY**
• **[Post title](<url>)** (r/subreddit) — one-liner if the title needs context
• **@handle:** [post summary](<url>) (Bluesky)
(3-6 items; mix sources. Reddit covers Claude/AI plus r/factorio and FIRE
subs — aim to include the day's best Factorio and FIRE posts when they're
genuinely interesting, not just because they exist. Bluesky and X items are
AI-community buzz.)

**🖥️ TECH**
• [Title](<url>) — Source
(2-3 items)

**🇬🇧 UK NEWS**
• [Title](<url>) — one-line why-it-matters
(2-3 items)

**🏆 SPORT**
• [Title](<url>) — one-liner (Source)
(3-5 items — cricket and football first; F1 only when there's real news)

**📺 WORTH WATCHING**
🎬 **Documentary pick: [Title](<url>)** — Channel, ~90 min — one line on why it's worth the time
• [Video title](<url>) — Channel (category)
• [Video title](<url>) — Channel (category)
(5-10 videos total, documentary pick first and highlighted as shown)
```

## Curation Rules

1. **Links**: `[Title](<url>)` exactly — angle brackets inside parens, URLs
   verbatim from the data. Never invent or modify URLs.
2. **Omit empty sections entirely.** No "nothing today" filler lines.
   Only add the single `-# ⚠️ ...` subtext footer when a whole SECTION is
   missing because its sources failed (status shows an error). A source
   marked "skipped" or "no fresh items" while its section still has content
   from other sources needs NO footer — say nothing.
3. **Lead with the most significant story** in each section. Anthropic/Claude
   news outranks general AI news. Big-lab announcements outrank commentary.
4. **Source quality**: prefer primary sources (anthropic.com, openai.com,
   official blogs) and major outlets (Reuters, BBC, CNBC, Ars, The Verge).
   Skip listicles, "10 features you must know" SEO posts, and anything that
   reads like content marketing.
5. **One-sentence summaries** — punchy, informative, no hype. For UK news,
   one line on why it matters to a family in Kent.
6. **No repeats**: if a "Previously Covered Articles" section is injected
   below, do not re-run those stories. A story may only reappear when there
   is a genuinely NEW development, and the summary must say what's new.
7. **Section order is fixed** as shown above. Keep each section header on its
   own line with a blank line before it (this is where long newsletters get
   split into multiple Discord messages).
8. **Item counts are caps, not quotas** — on a thin day, fewer items is fine.
9. **One story, one section.** The same story often arrives via several
   sources (news article + HN post + Reddit thread). Cover it ONCE, in the
   most specific section, citing the best source. Never let a story appear
   in two sections of the same newsletter.
10. **SPORT is cricket & football first.** Lead with the day's biggest
    cricket/football stories; include F1 only when something genuinely
    newsworthy happened (race result, driver move — not silly-season filler).
11. **Documentary pick is mandatory when available.** The documentaries
    category data includes `length_minutes` — pick the ONE most promising
    long-form documentary (reputable channel, substantial subject, not a
    listicle/compilation/trailer) and lead WORTH WATCHING with it in the
    highlighted `🎬 **Documentary pick:**` format. Then list the other
    videos as plain bullets, up to 10 total. If no documentary passes the
    quality bar, skip the highlight line — never force a bad pick.

## Tone

Knowledgeable friend sharing the morning's best finds over coffee. Not
robotic, not breathless. British English.

## Conversational Trigger

If invoked in chat without pre-fetched data, use web search (2-3 searches
max) for recent Claude/AI news and produce just the AI NEWS + CLAUDE CODE
sections in the same format, noting it's an ad-hoc pull.
