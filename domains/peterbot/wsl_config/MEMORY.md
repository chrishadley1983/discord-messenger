# Memory Systems Reference

Peter has two memory systems for different purposes.

## Overview

- **Peterbot-mem**: Conversation memory — things learned from past chats with Chris (auto-injected via hooks)
- **Second Brain**: Saved knowledge — articles, ideas, notes Chris saved or were passively captured

---

## Peterbot-mem (Conversation Memory)

Contains observations extracted from past conversations: preferences, decisions, facts about Chris's life/work/projects.

### How It Works

Peterbot-mem runs as a **claude-mem plugin** with lifecycle hooks. It does NOT expose MCP tools.

- **Auto-injection**: Relevant memories are automatically injected into your context at session start
- **Auto-capture**: Observations are automatically extracted from conversations via PostToolUse hooks
- **No manual search**: You cannot query peterbot-mem on demand — it works passively

### API Endpoint (for manual search when needed)

If you need to actively search conversation memory, use the claude-mem worker API:
```
GET http://172.19.64.1:37777/api/context/inject?project=peterbot&query=<query>
```

### When It Helps

- Context about Chris's routines, family, work, projects
- Previous decisions and preferences
- Things discussed in past conversations
- Automatically provided — no action needed in most cases

---

## Second Brain (Saved Knowledge)

Contains articles, notes, ideas, and content Chris explicitly saved or that was passively captured from conversations.

### API Endpoints (use curl mid-response)

**Search saved knowledge:**
```bash
curl "http://172.19.64.1:8100/brain/search?query=<query>&limit=5"
```
Returns JSON with titles, excerpts, similarity scores.

**Save new content:**
```bash
curl -X POST http://172.19.64.1:8100/brain/save \
  -H "Content-Type: application/json" \
  -d '{"source": "<text>", "note": "<optional>", "tags": "<optional comma-separated>"}'
```

**Get stats:**
```bash
curl http://172.19.64.1:8100/brain/stats
```

### Discord Commands (user-facing)

- `/recall <query>` — Semantic search across all saved content
- `/save <url or text>` — Explicitly save an article, idea, or note

**Passive surfacing** happens automatically — relevant knowledge is injected into your context without action needed.

### When to Use

- "What article did Chris save about X?"
- "Find that note about Y"
- "What do I know about Z?" (saved content, not conversations)
- Research Chris previously collected

---

## Which System to Use

| Question Type | How to Access |
|--------------|---------------|
| "What did Chris say/decide/prefer" | Auto-injected by peterbot-mem hooks |
| "What article/note/content was saved" | `curl http://172.19.64.1:8100/brain/search?query=...` |
| Not sure | Check auto-injected context first, then curl /brain/search |

### Important

- **Peterbot-mem**: Passive — context is auto-injected. Use the worker API at 172.19.64.1:37777 only if you need to actively search.
- **Second Brain**: Use `curl` to the HadleyAPI at `172.19.64.1:8100`. Use the `/brain/search` endpoint.
- Both systems use `172.19.64.1` (Windows host IP from WSL), NOT `localhost`.

---

## MCP Server Access (Claude Desktop & Claude Code)

The Second Brain is also accessible via MCP (Model Context Protocol) from Claude Desktop and Claude Code sessions outside the bot. This provides direct tool access without needing curl or the Hadley API.

**Available tools:** `search_knowledge`, `get_recent_items`, `browse_topics`, `get_item_detail`, `save_to_brain`, `list_items`

Configuration is in `.mcp.json` (Claude Code) and `%APPDATA%\Claude\claude_desktop_config.json` (Claude Desktop).

Note: Peterbot-mem is NOT accessible via MCP — it uses lifecycle hooks and auto-injection only.
