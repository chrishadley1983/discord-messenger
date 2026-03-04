# Memory System Reference

Peter uses **Second Brain** as a unified memory system for all knowledge — conversations, articles, notes, ideas, and passively captured content.

---

## How It Works

Every conversation with Chris is automatically captured into Second Brain after each exchange:

1. **Auto-capture**: Each message pair (user + assistant) is processed through the pipeline
2. **Structured extraction**: Facts and concepts are extracted using AI
3. **Embedding**: Content is embedded for semantic search (384-dim gte-small vectors)
4. **Connection discovery**: Related items are automatically linked

### What Gets Stored

For each conversation capture:
- **Title**: Auto-generated summary title
- **Summary**: 2-3 sentence summary of the exchange
- **Topics**: Extracted tags (e.g., hadley-bricks, running, family)
- **Facts**: Concrete factual statements (dates, decisions, numbers)
- **Concepts**: Insights with types (how-it-works, why-it-exists, gotcha, pattern, trade-off)
- **Full text**: Complete conversation for later retrieval
- **Embeddings**: For semantic search across all content

---

## Accessing Memory

### Automatic Context Injection

Relevant knowledge is automatically injected into your context before each response. This includes:
- Previous conversation facts and summaries
- Related articles and notes
- Connected knowledge items

### MCP Tools (for explicit searches)

Use these MCP tools when you need to actively search or save:

| Tool | Purpose |
|------|---------|
| `search_knowledge` | Semantic search across all saved content |
| `get_recent_items` | Browse items by date |
| `browse_topics` | List topics by item count |
| `get_item_detail` | Full text + facts + concepts + connections |
| `save_to_brain` | Save new content (URL, text, or note) |
| `list_items` | Paginated browse with filters |

### Discord Commands (user-facing)

- `/recall <query>` — Semantic search across all saved content
- `/save <url or text>` — Explicitly save an article, idea, or note

---

## When to Use

| Question Type | How to Access |
|--------------|---------------|
| "What did Chris say/decide/prefer" | Check auto-injected context, or `search_knowledge` |
| "What article/note/content was saved" | `search_knowledge` MCP tool |
| "Save this for later" | `save_to_brain` MCP tool |
| Not sure | Check auto-injected context first, then search |

---

## Important Notes

- **All conversations are captured automatically** — no manual action needed
- Facts and concepts are extracted for structured retrieval
- Content decays over time (90-day half-life) but is boosted when accessed
- Cross-domain connections are discovered automatically (e.g., linking a business decision to a family event)
- MCP tools are available from Claude Desktop and Claude Code sessions too
