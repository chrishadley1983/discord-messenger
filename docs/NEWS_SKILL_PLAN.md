# News Skill Plan

## Overview

A specialized skill for fetching, summarizing, and formatting news for Discord. Triggered by news-related queries, returns clean markdown-formatted summaries with proper source links.

---

## Trigger Patterns

The skill activates when the user's message matches:
- "what's the news"
- "latest news about [topic]"
- "news on [topic]"
- "what's happening with [topic]"
- "headlines"
- "/news [topic]" (explicit command)

---

## Architecture

```
User message → Peterbot router
                    ↓
            Detect news intent?
                    ↓ yes
            News Skill Handler
                    ↓
            1. Extract topic/scope
            2. Query peterbot-mem for preferences
               - Preferred sources (Guardian, BBC, etc.)
               - Topics of interest
               - Past news discussions
            3. Web search with preferred sources
            4. Fetch top 2-3 sources
            5. Summarize key stories
            6. Format for Discord
                    ↓
            Return formatted response
```

---

## Memory Integration

Query peterbot-mem before fetching news:

```
GET /api/context/inject?project=peterbot&query=news+sources+preferences
```

### What to look for in memory:
- **Source preferences**: "I prefer Guardian", "BBC is good", "Skip the Mail"
- **Topic interests**: User's business (LEGO), hobbies, local area (Tonbridge)
- **Past discussions**: Previous news topics discussed, follow-ups

### Example memory-aware behavior:
```
Memory says: User prefers Guardian, lives in Tonbridge, runs LEGO business

User asks: "What's the news?"

Skill behavior:
1. Prioritize Guardian as source
2. Include any Tonbridge/Kent local news
3. Check for LEGO/retail industry news
4. General UK headlines
```

---

## Output Format

```markdown
**[Topic] News** - [Date]

**Headline 1**
Brief 1-2 sentence summary of the story.

**Headline 2**
Brief 1-2 sentence summary of the story.

**Headline 3**
Brief 1-2 sentence summary of the story.

Sources:
• [Guardian](https://full-url-here)
• [BBC](https://full-url-here)
```

### Format Rules:
- Max 3-5 headlines per response
- Each summary: 1-2 sentences max
- Sources as markdown links (not raw URLs)
- Total response under 1500 chars (Discord limit buffer)
- No emojis in headlines
- Bold for headline titles only

---

## Implementation Options

### Option A: Prompt-Based (Quick)
Add news-specific instructions to PETERBOT_SOUL.md and let Claude Code handle it naturally with the existing flow.

**Pros:** No code changes, quick to test
**Cons:** Less control over format, relies on model following instructions

### Option B: Skill File (Medium)
Create a `/news` skill in the peterbot project that injects specialized prompts.

```
/home/chris_hadley/peterbot/.claude/skills/news/
├── SKILL.md          # Skill definition
└── prompt.md         # News-specific prompt template
```

**Pros:** Dedicated handling, consistent format
**Cons:** Requires skill setup, Claude Code skill system

### Option C: Pre-Processing in Router (Full Control)
Detect news intent in router.py, build specialized context, use different prompt.

```python
# In router.py
if is_news_request(message):
    context = build_news_context(message)
    prompt = NEWS_PROMPT_TEMPLATE.format(topic=extract_topic(message))
else:
    # Normal flow
```

**Pros:** Full control, can customize per-topic
**Cons:** More code, maintenance burden

---

## Recommended: Option B (Skill File)

Claude Code's skill system is designed for this. Create:

### `/home/chris_hadley/peterbot/.claude/skills/news/SKILL.md`

```markdown
---
name: news
description: Fetch and summarize news on a topic
trigger:
  - "news"
  - "headlines"
  - "what's happening"
---

# News Skill

When the user asks for news, search for current headlines and return a Discord-formatted summary.

## Steps
1. Check memory context for:
   - Preferred news sources (Guardian, BBC, etc.)
   - User's location (Tonbridge) for local news
   - User's interests (LEGO business, running, tech)
2. Extract the topic from the user's request (default: "UK news")
3. Web search prioritizing preferred sources:
   - "[topic] news today site:theguardian.com"
   - "[topic] news today site:bbc.co.uk"
   - General "[topic] news [current date]"
4. Fetch 2-3 top sources for details
5. Summarize the top 3-5 stories
6. If topic relates to user interests (LEGO, running), include relevant stories

## Output Format
- Use **bold** for headline titles
- 1-2 sentence summary per story
- End with "Sources:" section using markdown links
- Keep total response under 1500 characters

## Memory-Aware Examples

**Generic request:** "What's the news?"
→ UK headlines from preferred sources + any Tonbridge local news

**Topic request:** "LEGO news"
→ LEGO industry news, knowing user runs a resale business

**Follow-up:** "More on that farming thing"
→ Check recent conversation for context

## Example Output
**UK News** - Saturday, January 31

**Snow Disruption Continues**
Weather warnings remain in effect across northern regions with travel chaos expected through the weekend.

**Farmers Win Tax Relief**
Government raises inheritance tax threshold for agricultural property from £1m to £2.5m after lobbying pressure.

**Migration Numbers Fall**
Net migration drops to near pre-Covid levels according to new ONS figures.

Sources:
• [BBC News](https://bbc.co.uk/news/uk)
• [Guardian](https://theguardian.com/uk-news)
```

---

## Integration with Peterbot

Two approaches:

### A) Let Claude Code Handle It
The skill file exists in the peterbot project. When Claude Code sees a news request, it uses the skill naturally.

### B) Explicit Skill Invocation
Modify router.py to detect news requests and prepend skill invocation:

```python
def build_full_context(message: str, memory_context: str) -> str:
    # Check for news intent
    news_keywords = ['news', 'headlines', 'what\'s happening', 'latest on']
    if any(kw in message.lower() for kw in news_keywords):
        message = f"/news {message}"  # Prepend skill command

    # Rest of context building...
```

---

## Testing Plan

1. Create skill file in peterbot project
2. Kill peterbot session
3. Send: "What's the UK news today?"
4. Verify:
   - Headlines are bolded
   - Summaries are concise
   - Sources use markdown links
   - Total length reasonable

---

## Future Enhancements

- **Topic filtering**: Sports, politics, tech, local
- **Source preferences**: Preferred outlets per topic
- **Caching**: Don't re-fetch if asked again within X minutes
- **Rich embeds**: Discord embed format with images (requires bot code changes)
