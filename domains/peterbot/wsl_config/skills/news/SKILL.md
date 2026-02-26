---
name: news
description: Fetch and summarize news based on user request and preferences from memory
trigger:
  - "news"
  - "headlines"
  - "what's happening"
  - "what's going on"
scheduled: true
conversational: true
channel: #news
---

# News Skill

Fetch current news based on what the user asks for and what you know about them from memory.

## Memory Context

Before responding, check the injected memory context for:
- **Preferred sources** (newspapers, sites they trust)
- **Location** (for local news relevance)
- **Professional interests** (their business, industry)
- **Personal interests** (hobbies, topics they follow)
- **Past news discussions** (topics they've engaged with)

Use this to personalize - don't just dump generic headlines.

## Output Format

**MANDATORY: Use markdown link format. Raw URLs are FORBIDDEN.**

Every headline MUST be a clickable markdown link:

```
**📰 Morning News** - Friday, 31 January

**[Headline Text Here](https://source.com/article)**
Brief one-line summary of the story.

**[Another Headline](https://example.com/news)**
Context about why this matters.
```

## Format Rules

1. **Headline = Link**: `**[Headline Text](url)**` - the headline IS the link
2. **Short URLs**: Trim to domain + key path, no tracking params
3. **NO raw URLs**: Never `https://example.com/article` on its own line
4. **One-line summaries**: Brief context under each headline
5. **3-5 stories max**: Quality over quantity

## Search Efficiency

- Use **2-3 searches maximum** — don't iterate across every provider
- Prefer `brave_news_search` for headlines, fall back to others only if it fails
- Spend most of the time composing, not searching

## Deduplication

If a "Previously Covered Articles" section is injected below, **do not repeat those stories**.
Find fresh angles or different topics instead. It's fine to cover the same broad topic
if there's a genuinely new development, but don't rehash yesterday's headlines.

## Conversational vs Scheduled

**Conversational** (user asks for news):
- Tailor to their request + memory context
- Can ask clarifying questions if vague

**Scheduled** (7am daily to #news):
- Use memory context for their interests/location
- Mix topics based on what you know about them
- No preamble, just the news
- Keep it scannable for morning reading

## What NOT To Do

- ❌ Raw URLs that break on line wrap
- ❌ Ignore memory context - use what you know about them
- ❌ Long paragraphs - keep it brief
- ❌ "Here's your news..." preamble
- ❌ Sources section at the end (links are inline)
- ❌ Generic news that doesn't reflect their interests
- ❌ Repeating articles from the "Previously Covered" list
- ❌ Spending all the time searching — 2-3 searches then compose
