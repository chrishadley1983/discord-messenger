# MCP Tool & Web Search Guidelines

## Web Search/Fetch Priority
1. Built-in WebFetch/WebSearch for standard lookups
2. If WebFetch hangs, times out, or returns an error → immediately switch to searxng
3. Never wait more than 10s on a single fetch — switch tools
4. For sites that block bots (Waitrose, supermarkets, etc.) → prefer searxng

## API/Library Documentation
- Always use **context7** when looking up library docs, API references, or framework guides
- Use `resolve-library-id` first, then `get-library-docs`
- For APIs not indexed by Context7 (e.g. xAI management API) → fall back to searxng

## Tool Priority Order
1. **context7** → for library/framework docs
2. **Built-in WebFetch** → for known, reliable URLs
3. **searxng** → fallback for everything else, especially sites that block bots

**Important:** SearXNG fetches through search engine caches, bypassing bot-blocking entirely.

## Web Search Rules
- Quick lookups: single search, direct answer
- Research queries: read `docs/playbooks/RESEARCH.md` for full process
- NEVER just return a list of links — synthesize findings, sources at the end
