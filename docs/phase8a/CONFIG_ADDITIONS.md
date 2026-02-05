# Phase 8a Configuration Additions

## .env additions

```bash
# Google OAuth (for Gmail, Calendar, Drive)
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REFRESH_TOKEN=your_refresh_token

# Notion
NOTION_API_KEY=REDACTED_NOTION_TOKEN
NOTION_TODOS_DATABASE_ID=<get from database URL>
NOTION_IDEAS_DATABASE_ID=<get from database URL>
```

## config.py additions

```python
# === PHASE 8a: Google Integration ===
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

# === PHASE 8a: Notion Integration ===
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_TODOS_DATABASE_ID = os.getenv("NOTION_TODOS_DATABASE_ID")
NOTION_IDEAS_DATABASE_ID = os.getenv("NOTION_IDEAS_DATABASE_ID")
```

## Getting Notion Database IDs

1. Open each database in Notion
2. Copy the URL: `https://www.notion.so/your-workspace/{DATABASE_ID}?v=...`
3. The DATABASE_ID is the 32-character string before the `?`

Example:
- URL: `https://www.notion.so/hadley/abc123def456...?v=xyz`
- Database ID: `abc123def456...`

## MCP Server Configuration

The Google and Notion MCP servers need to be configured in Claude Code's MCP settings.

### For Claude Code (in peterbot WSL session)

Add to `~/.claude/mcp_servers.json` or equivalent:

```json
{
  "servers": {
    "google": {
      "command": "npx",
      "args": ["-y", "@anthropic/mcp-google"],
      "env": {
        "GOOGLE_CLIENT_ID": "${GOOGLE_CLIENT_ID}",
        "GOOGLE_CLIENT_SECRET": "${GOOGLE_CLIENT_SECRET}",
        "GOOGLE_REFRESH_TOKEN": "${GOOGLE_REFRESH_TOKEN}"
      }
    },
    "notion": {
      "command": "npx", 
      "args": ["-y", "@anthropic/mcp-notion"],
      "env": {
        "NOTION_API_KEY": "${NOTION_API_KEY}"
      }
    }
  }
}
```

Note: Check actual MCP server package names - these may be community packages like:
- `@modelcontextprotocol/server-google-drive`
- `@modelcontextprotocol/server-notion`
- `mcp-server-gmail`
