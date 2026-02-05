# Memory Systems Reference

Peter has two memory systems for different purposes.

## Overview

- **Peterbot-mem**: Conversation memory — things learned from past chats with Chris
- **Second Brain**: Saved knowledge — articles, ideas, notes Chris saved or were passively captured

---

## Peterbot-mem (Conversation Memory)

Contains observations extracted from past conversations: preferences, decisions, facts about Chris's life/work/projects.

### MCP Tools

Use the 3-layer workflow to minimize token usage:

**Layer 1: Search** — Get an index of matching observations
```
mcp__claude-mem__search
  query: "keyword or phrase"
  project: "peterbot"
  limit: 10
```
Returns observation IDs and summaries (~50-100 tokens each).

**Layer 2: Timeline** — Get context around interesting results
```
mcp__claude-mem__timeline
  anchor: <observation_id from search>
  depth_before: 3
  depth_after: 3
  project: "peterbot"
```
Shows what happened before/after a specific observation.

**Layer 3: Get Observations** — Fetch full details
```
mcp__claude-mem__get_observations
  ids: [<id1>, <id2>, ...]
  project: "peterbot"
```
Only fetch full details for filtered, relevant IDs.

### When to Use

- "What did Chris decide about X?"
- "What's Chris's preference for Y?"
- "What did we discuss regarding Z?"
- Context about Chris's routines, family, work, projects

---

## Second Brain (Saved Knowledge)

Contains articles, notes, ideas, and content Chris explicitly saved or that was passively captured from conversations.

### API Endpoint (use this mid-response)

**Search saved knowledge:**
```
GET http://localhost:8100/brain/search?query=<query>&limit=5
```
Returns JSON with titles, excerpts, similarity scores. Use this when you need to search while composing a response.

### Discord Commands (user-facing)

**Search saved knowledge:**
```
/recall <query>
```
Semantic search across all saved content. Returns titles, excerpts, similarity scores.

**Save new content:**
```
/save <url or text>
```
Explicitly save an article, idea, or note.

**Passive surfacing** happens automatically — relevant knowledge is injected into your context without action needed.

### When to Use

- "What article did Chris save about X?"
- "Find that note about Y"
- "What do I know about Z?" (saved content, not conversations)
- Research Chris previously collected

---

## Which System to Use

| Question Type | Use |
|--------------|-----|
| "What did Chris say/decide/prefer" | Peterbot-mem (MCP) |
| "What article/note/content was saved" | Second Brain (/brain/search) |
| Not sure | Try peterbot-mem first, then /brain/search |

### Important

- **Peterbot-mem**: Use MCP tools only (never curl)
- **Second Brain**: Use `/brain/search` API mid-response, or `/recall` for user-facing queries
- Always specify `project: "peterbot"` for MCP tools
- Start with search before fetching full details
