# Peter Channel Test — Feature Spec

## Summary

Build a custom Claude Code channel that bridges a dedicated Discord test channel to a persistent Claude Code session running in WSL. Messages from `#peter-channel-test` push directly into the session; Claude replies via a `reply()` tool. The session has access to Second Brain, financial data MCP servers, and Hadley API — the same capabilities as current Peter, but with raw persistent context instead of the stateless spawn-per-message model. No response pipeline (no sanitiser, formatter, or chunker). This is a raw comparison test.

## What We're Testing

1. Does persistent session context make conversations feel more natural?
2. How much terminal garbage leaks without the response pipeline?
3. Does Claude Code's auto-compression handle a day's worth of messages?
4. What's the latency difference (warm session vs cold CLI spawn)?

## Architecture

```
Discord #peter-channel-test
    ↓ (Discord.js gateway)
peter-channel/ MCP server (Node.js, runs in WSL)
    ↓ (mcp.notification → stdio)
Claude Code session (persistent, WSL)
    ├── CLAUDE.md (Peter personality + instructions)
    ├── .mcp.json (second-brain, financial-data)
    ├── Hadley API access (172.19.64.1:8100)
    └── Full filesystem access (~/peterbot)
    ↓ (Claude calls reply tool)
peter-channel/ MCP server
    ↓ (Discord.js send)
Discord #peter-channel-test
```

### Key Differences from Current Peter

| Aspect | Current (router_v2) | Channel Test |
|--------|---------------------|--------------|
| Session | Fresh process per message | Persistent session |
| Context | 20-msg buffer + Second Brain search | Full conversation in context window |
| Response processing | 5-stage pipeline (sanitise→format→chunk) | Raw — Claude output goes straight to Discord |
| Provider cascade | 3-tier failover | Single session, no failover |
| MCP servers | Loaded fresh each time | Connected once, stay alive |
| Discord formatting | Type-specific formatters | Prompt-only ("format for Discord") |
| Scheduled jobs | Supported | Not in scope (conversation only) |

## Discord Setup

### New Test Channel

- Create `#peter-channel-test` on existing Discord server
- Same server as current Peter channels (no new bot needed)
- **But**: Need a **separate Discord bot/app** for the channel MCP server
  - Current bot token is used by `bot.py` (NSSM service) — can't share gateway connections
  - Create `Peter Channel Test` bot in Discord Developer Portal
  - Add to same server with `Send Messages` + `Read Message History` + `View Channels` permissions
  - Restrict to `#peter-channel-test` channel only (channel permissions)

### Why a Separate Bot

Discord's gateway allows only one connection per bot token. The existing `bot.py` service holds that connection. The channel MCP server needs its own gateway connection, so it needs its own bot token. They coexist on the same server — different bots, different channels.

## Channel MCP Server

### Location

```
peter-channel/
├── package.json
├── tsconfig.json
├── src/
│   └── index.ts
└── .env              (gitignored)
```

Lives at `C:\Users\Chris Hadley\claude-projects\discord-messenger\peter-channel\` on Windows, but **runs in WSL** (Claude Code session is WSL-side).

WSL path: `/mnt/c/Users/Chris Hadley/claude-projects/discord-messenger/peter-channel/`

### Dependencies

```json
{
  "dependencies": {
    "@modelcontextprotocol/sdk": "latest",
    "discord.js": "^14.0.0"
  },
  "devDependencies": {
    "typescript": "^5.0.0",
    "tsx": "^4.0.0"
  }
}
```

### Server Implementation

The MCP server does three things:

1. **Declares `claude/channel` capability** — registers as a channel
2. **Listens to Discord gateway** — receives messages from `#peter-channel-test`
3. **Exposes `reply` tool** — Claude calls this to send messages back

```typescript
// Pseudocode structure — full implementation in build phase

const mcp = new Server({
  name: 'peter-channel',
  capabilities: {
    experimental: { 'claude/channel': {} },
    tools: {},
  },
  instructions: CHANNEL_INSTRUCTIONS,  // see below
})

// Discord gateway → push notifications
discord.on('messageCreate', async (msg) => {
  if (msg.channel.id !== TEST_CHANNEL_ID) return
  if (msg.author.bot) return
  if (!ALLOWED_USERS.has(msg.author.id)) return

  await mcp.notification({
    method: 'notifications/claude/channel',
    params: {
      content: msg.content,
      meta: {
        chat_id: msg.channelId,
        sender: msg.author.username,
      },
    },
  })
})

// Reply tool — Claude sends messages back
mcp.tool('reply', async ({ chat_id, text }) => {
  const channel = await discord.channels.fetch(chat_id)

  // Minimal chunking — respect Discord's 2000-char limit
  const chunks = splitAtBoundaries(text, 1950)
  for (const chunk of chunks) {
    await channel.send(chunk)
  }

  return { content: [{ type: 'text', text: 'sent' }] }
})
```

### Channel Instructions (injected into Claude's system prompt)

```
Messages from Discord arrive as <channel source="peter-channel" chat_id="..." sender="...">.
Reply using the reply tool with the chat_id from the tag.

You are Peter, the Hadley family assistant. Keep responses concise and Discord-friendly:
- No markdown tables (Discord can't render them)
- No headers (# Title) — use **bold** instead
- Keep messages under 1500 chars where possible
- Never include tool call outputs, file contents, or terminal artifacts in your reply
- Only reply with your actual response to the user

Your terminal output is NOT visible in Discord. Only reply tool messages reach the user.
```

### Minimal Chunking in Reply Tool

Since we're skipping the full pipeline, the reply tool needs basic 2000-char handling:

```typescript
function splitAtBoundaries(text: string, maxLen: number): string[] {
  if (text.length <= maxLen) return [text]
  const chunks: string[] = []
  let remaining = text
  while (remaining.length > 0) {
    if (remaining.length <= maxLen) {
      chunks.push(remaining)
      break
    }
    // Try paragraph, then newline, then sentence, then hard break
    let splitAt = remaining.lastIndexOf('\n\n', maxLen)
    if (splitAt < maxLen * 0.3) splitAt = remaining.lastIndexOf('\n', maxLen)
    if (splitAt < maxLen * 0.3) splitAt = remaining.lastIndexOf('. ', maxLen)
    if (splitAt < maxLen * 0.3) splitAt = maxLen
    chunks.push(remaining.slice(0, splitAt + 1))
    remaining = remaining.slice(splitAt + 1)
  }
  return chunks
}
```

## Claude Code Session Setup

### Working Directory

`~/peterbot` (same as current Peter) — this gives Claude Code access to:
- `CLAUDE.md` (Peter's personality + instructions)
- `PETERBOT_SOUL.md` (tone, identity)
- `playbooks/*.md` (task-specific instructions)
- `skills/manifest.json` (available skills)
- `.mcp.json` (Second Brain + financial data servers)

### Launch Command

```bash
cd ~/peterbot && claude \
  --dangerously-load-development-channels /mnt/c/Users/Chris\ Hadley/claude-projects/discord-messenger/peter-channel \
  --model opus \
  --permission-mode bypassPermissions
```

**Flags:**
- `--dangerously-load-development-channels` — loads our custom channel (research preview requirement)
- `--model opus` — same model as current Peter
- `--permission-mode bypassPermissions` — no permission prompts (trusted environment)

### MCP Servers Available (from ~/peterbot/.mcp.json)

| Server | Tools | Purpose |
|--------|-------|---------|
| second-brain | search_knowledge, save_to_brain, etc. | Memory/knowledge base |
| financial-data | get_net_worth, get_budget_status, etc. | Personal finance + Hadley Bricks |
| playwright | Browser automation | Fallback web scraping |

Plus the channel's own `reply` tool.

### What's NOT Available (vs current Peter)

- **No provider cascade** — if session dies, it dies
- **No response pipeline** — raw output only, formatting via prompt instructions
- **No interim updates** — no "Searching the web..." progress messages
- **No cost logging** — no per-message JSONL entries
- **No garbage detection** — no heuristic checks for non-answers
- **No scheduled jobs** — conversation only

## Build Order

### Step 1: Discord Setup (5 min)

1. Create `Peter Channel Test` bot in Discord Developer Portal
2. Generate bot token
3. Add bot to existing server
4. Create `#peter-channel-test` channel
5. Set channel permissions: bot can read + send, restrict to test channel only
6. Note the channel ID and Chris's Discord user ID for allowlist

### Step 2: Channel MCP Server (30 min)

1. Create `peter-channel/` directory
2. `npm init` + install dependencies (`@modelcontextprotocol/sdk`, `discord.js`, `typescript`, `tsx`)
3. Write `src/index.ts`:
   - MCP server with `claude/channel` capability
   - Discord.js client connecting to gateway
   - Message listener filtered to test channel + allowlisted users
   - `reply` tool with basic chunking
4. Create `.env` with `DISCORD_BOT_TOKEN` and `ALLOWED_DISCORD_IDS`
5. Build and test locally: `npx tsx src/index.ts` (verify Discord connection)

### Step 3: WSL Integration (15 min)

1. Ensure Node.js available in WSL (for running the channel server)
2. Run `npm install` from WSL path
3. Test the launch command:
   ```bash
   cd ~/peterbot && claude \
     --dangerously-load-development-channels /mnt/c/Users/Chris\ Hadley/claude-projects/discord-messenger/peter-channel \
     --model opus \
     --permission-mode bypassPermissions
   ```
4. Verify Claude Code starts and shows "Listening for channel messages"
5. Send test message in `#peter-channel-test`
6. Verify message arrives in Claude Code session
7. Verify reply appears in Discord

### Step 4: Smoke Test (15 min)

Test these scenarios to compare against current Peter:

| Test | What to Check |
|------|---------------|
| "Hello" | Basic reply, tone, no artifacts |
| "What's my net worth?" | Financial MCP tool works |
| "Search Second Brain for Japan restaurants" | Second Brain MCP works |
| Multi-turn conversation (5+ messages) | Context retained naturally |
| "What did I just say?" | Persistent context test |
| Long response (ask for detailed analysis) | Chunking works, no truncation |
| Ask about something from 20 messages ago | Context window vs buffer comparison |

### Step 5: Document Findings (10 min)

After testing, note:
- Latency comparison (first message warm-up vs subsequent)
- Response quality (with vs without pipeline)
- Terminal artifact leakage (how much junk gets through)
- Context retention (does it remember earlier conversation?)
- Any crashes, disconnections, or context saturation

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Terminal artifacts leak to Discord | Medium | Strong instructions in channel `instructions` field + CLAUDE.md already says "format for Discord" |
| Session crashes overnight | Low (test only) | Manual restart — not production |
| Context window fills up | Low (test) | Claude Code auto-compresses; we're testing if this works |
| Discord.js conflicts with bot.py's connection | None | Separate bot token, separate gateway |
| `--dangerously-load-development-channels` warning | Low | Accept once per session |
| Node.js not available in WSL | Low | Install if needed: `sudo apt install nodejs npm` |

## Success Criteria

This is a **test**, not a production migration. Success means:

1. Messages flow both ways (Discord ↔ Claude Code session)
2. Second Brain and financial MCP tools work in the session
3. We have enough experience to judge whether persistent sessions are worth pursuing
4. We identify what the response pipeline is actually protecting against (empirically, not theoretically)

## Status: READY_FOR_BUILD
