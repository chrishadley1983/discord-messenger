# Channel Architecture

Comprehensive reference for the three persistent Claude Code channel sessions that handle all messaging for Peter, the Hadley family assistant.

**Related docs:** [ARCHITECTURE.md](./ARCHITECTURE.md) (system overview), [CORE_BOT.md](./CORE_BOT.md) (bot.py reference)

---

## Table of Contents

1. [Overview](#1-overview)
2. [How Channels Work](#2-how-channels-work)
3. [peter-channel (Discord)](#3-peter-channel-discord)
4. [whatsapp-channel (WhatsApp)](#4-whatsapp-channel-whatsapp)
5. [jobs-channel (Scheduled Jobs)](#5-jobs-channel-scheduled-jobs)
6. [Session Lifecycle](#6-session-lifecycle)
7. [Fallback and Resilience](#7-fallback-and-resilience)
8. [Channel vs Router V2](#8-channel-vs-router-v2)
9. [Configuration Reference](#9-configuration-reference)
10. [Debugging and Logs](#10-debugging-and-logs)
11. [Adding a New Channel](#11-adding-a-new-channel)

---

## 1. Overview

Three persistent Claude Code sessions run in WSL2 tmux, each bridging a different message source to a long-lived Claude session via the MCP channel protocol. Every channel is a TypeScript MCP server that:

1. Declares the `claude/channel` experimental capability
2. Receives messages from its source (Discord gateway, HTTP webhook, or scheduler POST)
3. Pushes messages into Claude Code via `notifications/claude/channel`
4. Exposes reply tool(s) so Claude can send responses back to the source

All three sessions share the same working directory (`~/peterbot` in WSL), the same `CLAUDE.md` personality file, and the same MCP tool servers (Second Brain, financial data, Brave Search, SearXNG, etc.).

```
                          Windows (NSSM)                    WSL2 (tmux sessions)
                    +---------------------------+     +---------------------------+
                    |                           |     |                           |
 Discord users ---->| bot.py (Discord gateway)  |     |  tmux: peter-channel      |
                    |   Checks Peter H online   |     |    Claude Code session    |
                    |   Falls back if offline   |     |    + peter-channel MCP    |
                    |                           |     |    + discord.js client    |
                    +---------------------------+     +---------------------------+
                                                              |           ^
                                                     notification    reply tool
                                                              v           |
                                                      +-------------------+
                                                      | Claude (Opus 4.6) |
                                                      +-------------------+

                    +---------------------------+     +---------------------------+
 WhatsApp users --->| Evolution API :8085       |     |  tmux: whatsapp-channel   |
                    |   |                       |     |    Claude Code session    |
                    |   v                       |     |    + whatsapp-channel MCP |
                    | Hadley API :8100          |---->|    HTTP server :8102      |
                    |   /whatsapp/webhook       |     +---------------------------+
                    |   (debounce + forward)    |
                    +---------------------------+

                    +---------------------------+     +---------------------------+
 Cron schedule ---->| bot.py APScheduler        |     |  tmux: jobs-channel       |
                    |   scheduler.py            |---->|    Claude Code session    |
                    |   POST /job               |     |    + jobs-channel MCP     |
                    |   (waits synchronously)   |<----|    HTTP server :8103      |
                    +---------------------------+     +---------------------------+
```

---

## 2. How Channels Work

Channels use Anthropic's MCP channel protocol -- an experimental extension to the Model Context Protocol. The key mechanism:

### MCP Channel Capability

Each server declares `claude/channel` in its capabilities:

```typescript
const mcp = new Server(
  { name: "peter-channel", version: "0.0.1" },
  {
    capabilities: {
      experimental: { "claude/channel": {} },
      tools: {},
    },
    instructions: CHANNEL_INSTRUCTIONS,
  }
);
```

### Notification Push

When a message arrives, the server pushes it into the Claude Code session:

```typescript
await mcp.notification({
  method: "notifications/claude/channel",
  params: {
    content: "the user's message text",
    meta: {
      chat_id: "channel-id",
      sender: "username",
      is_admin: "true",
      // ... source-specific metadata
    },
  },
});
```

Claude receives this as a `<channel>` tag in its context, with the metadata as XML attributes. The `instructions` field from the server declaration is injected into Claude's system prompt, telling it how to interpret the tags and use the reply tools.

### Reply Tools

Each channel exposes one or more tools that Claude calls to send responses back. The tool implementations handle the actual delivery (Discord API, HTTP to Evolution API, resolving a pending promise, etc.).

### Transport

All three channels use **stdio transport** -- Claude Code spawns the MCP server as a subprocess and communicates via stdin/stdout. The `--dangerously-load-development-channels server:<name>` flag tells Claude Code to treat this MCP server as a channel source.

---

## 3. peter-channel (Discord)

**Location:** `peter-channel/`
**Transport:** stdio (MCP) + Discord gateway (discord.js)
**tmux session:** `peter-channel`

### Purpose

Bridges Discord messages to a persistent Claude Code session. Discord users send messages in configured channels; Claude reads them via MCP notification and replies via the `reply` tool, which posts back to Discord.

### Source Files

| File | Purpose |
|------|---------|
| `src/index.ts` | MCP server + Discord client (~330 lines) |
| `launch.sh` | tmux launch script with restart loop |
| `.env` | Discord bot token, channel IDs, allowed user IDs |
| `package.json` | Dependencies: `@modelcontextprotocol/sdk`, `discord.js` |

### Message Flow

```
1. User sends message in Discord #peterbot
2. discord.js MessageCreate event fires
3. Sender checked against ALLOWED_DISCORD_IDS allowlist
4. Message content + attachment URLs assembled
5. MCP notification pushed: notifications/claude/channel
   - meta: { chat_id, channel_name, sender, sender_id, is_admin }
6. Claude processes message, calls reply tool
7. reply tool:
   a. Chunks text at natural boundaries (paragraph > newline > sentence)
   b. Sends chunks to Discord via channel.send() (2000 char limit)
   c. Fire-and-forget: POST /response/capture to Hadley API (Second Brain)
8. User sees response in Discord
```

### Tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `reply` | `chat_id` (string), `text` (string) | Send message to Discord channel. Auto-chunks at 1950 chars. |

### Key Implementation Details

- **Sender allowlist:** Only `ALLOWED_DISCORD_IDS` can trigger notifications. Other users' messages are silently ignored. This prevents prompt injection from untrusted users.
- **Admin gate:** Chris's Discord ID (`1354023957677871156`) sets `is_admin: "true"` in the notification metadata. Claude uses this to gate self-modification requests.
- **Attachment handling:** Discord attachments are appended as markdown links (`[filename](url)`) to the message content.
- **Message chunking:** The `splitAtBoundaries` function splits long responses at paragraph breaks, newlines, or sentence boundaries -- never mid-word. Max chunk size is 1950 chars (50-char buffer under Discord's 2000 limit).
- **Second Brain capture:** After each reply, the tool POSTs the conversation pair (user message + response) to `http://172.19.64.1:8100/response/capture` for knowledge base storage. This is fire-and-forget with a 10-second timeout -- failures do not block the reply.
- **Channel instructions:** Claude is told to avoid markdown tables (Discord renders them poorly), keep messages under 1500 chars, and never expose tool outputs or thinking narration.

### Environment Variables

| Variable | Example | Required |
|----------|---------|----------|
| `DISCORD_BOT_TOKEN` | `MTQ4NzA4...` | Yes |
| `DISCORD_CHANNEL_IDS` | `1234567890,9876543210` | Yes |
| `ALLOWED_DISCORD_IDS` | `1354023957677871156` | Yes |

---

## 4. whatsapp-channel (WhatsApp)

**Location:** `whatsapp-channel/`
**Transport:** stdio (MCP) + HTTP server on port 8102
**tmux session:** `whatsapp-channel`

### Purpose

Bridges WhatsApp messages to a persistent Claude Code session. Messages flow from WhatsApp through Evolution API, through the Hadley API webhook (which debounces and forwards), to this channel's HTTP server, into Claude, and back via the Hadley API send endpoints.

### Source Files

| File | Purpose |
|------|---------|
| `src/index.ts` | MCP server + HTTP receiver (~320 lines) |
| `launch.sh` | tmux launch script with restart loop |
| `.env` | HTTP port, Hadley API URL |
| `package.json` | Dependencies: `@modelcontextprotocol/sdk` (no WhatsApp SDK needed) |

### Message Flow

```
1. User sends WhatsApp message
2. Evolution API fires MESSAGES_UPSERT webhook to Hadley API
3. hadley_api/whatsapp_webhook.py:
   a. Deduplicates (OrderedDict of recent message IDs, 5-min TTL)
   b. Checks sender against ALLOWED_SENDERS (Chris + Abby only)
   c. Handles voice messages (downloads audio, transcribes via Whisper)
   d. Debounces: buffers messages per sender for 3s, then batches
   e. Forwards to http://127.0.0.1:8102/whatsapp/message
4. whatsapp-channel HTTP server receives POST /whatsapp/message
   - Payload: { sender_name, sender_number, reply_to, is_group, text, is_voice }
5. MCP notification pushed: notifications/claude/channel
   - meta: { phone, sender, sender_number, is_voice, is_group, is_admin }
6. Claude processes message, calls reply and/or voice_reply tools
7. reply tool: POST to Hadley API /whatsapp/send -> Evolution API -> WhatsApp
8. voice_reply tool: POST to Hadley API /whatsapp/send-voice -> TTS -> Evolution API -> WhatsApp
9. Fire-and-forget: POST /response/capture (Second Brain)
```

### Tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `reply` | `phone` (string), `text` (string) | Send text message via Hadley API -> Evolution API -> WhatsApp |
| `voice_reply` | `phone` (string), `text` (string) | TTS to voice note via Hadley API -> Evolution API -> WhatsApp |

### Key Implementation Details

- **No direct WhatsApp SDK:** This channel has zero WhatsApp dependencies. All WhatsApp interaction goes through Hadley API endpoints (`/whatsapp/send`, `/whatsapp/send-voice`), which in turn call Evolution API. This keeps the channel server lightweight.
- **Admin gate:** Chris's number (`447855620978`) sets `is_admin: "true"`. Abby can message Peter but cannot trigger self-modification.
- **Voice message handling:** When `is_voice: "true"`, the channel instructions tell Claude to call `voice_reply` in addition to `reply`, so the user gets both a text and audio response.
- **Debounce at Hadley API:** The webhook receiver buffers rapid messages from the same sender for 3 seconds before forwarding. This prevents Claude from responding to a partial multi-message sequence.
- **Nag reminder check:** Channel instructions tell Claude to check `/reminders/active-nags` on each incoming message, enabling "did you do X?" reminder acknowledgment via WhatsApp.
- **WhatsApp formatting:** Claude is instructed to use `**bold**` and `_italic_` (which WhatsApp supports) but avoid headers, code blocks, and bullet lists.
- **HTTP health check:** `GET /health` returns `{ status: "ok" }` for liveness probing.

### Environment Variables

| Variable | Default | Required |
|----------|---------|----------|
| `HTTP_PORT` | `8102` | No |
| `HADLEY_API` | `http://172.19.64.1:8100` | No |

### External Dependencies

| Component | Location | Purpose |
|-----------|----------|---------|
| Evolution API | `localhost:8085` | WhatsApp gateway (Docker container) |
| Hadley API | `172.19.64.1:8100` | Message forwarding, send endpoints, TTS |
| Whisper (via Hadley API) | -- | Voice message transcription |

---

## 5. jobs-channel (Scheduled Jobs)

**Location:** `jobs-channel/`
**Transport:** stdio (MCP) + HTTP server on port 8103
**tmux session:** `jobs-channel`

### Purpose

Executes scheduled skills in a persistent Claude Code session. Unlike the other channels, this one uses a **synchronous request-response pattern**: the scheduler POSTs a job, the HTTP request blocks until Claude finishes processing and calls the reply tool, then the response is returned to the scheduler.

### Source Files

| File | Purpose |
|------|---------|
| `src/index.ts` | MCP server + HTTP receiver + sync coordination (~260 lines) |
| `launch.sh` | tmux launch script with restart loop |
| `.env` | HTTP port, job timeout |
| `package.json` | Dependencies: `@modelcontextprotocol/sdk` only |

### Message Flow

```
1. APScheduler fires job (via scheduler.py in bot.py)
2. scheduler.py checks JOBS_USE_CHANNEL=1
3. _send_to_jobs_channel():
   a. POST to http://127.0.0.1:8103/job
   b. Payload: { context: "<skill instructions + data>", skill: "morning-briefing" }
   c. HTTP request blocks, waiting for response
4. jobs-channel HTTP server receives POST /job:
   a. Generates UUID job_id
   b. Creates PendingJob with Promise + timeout timer
   c. Pushes MCP notification: notifications/claude/channel
      - meta: { job_id, skill }
   d. Awaits the Promise (blocks the HTTP response)
5. Claude processes skill instructions, calls reply tool
6. reply tool:
   a. Looks up job_id in pendingJobs map
   b. Resolves the Promise with Claude's output text
   c. Clears the timeout timer
7. Promise resolution unblocks the HTTP handler
8. HTTP response: { response: "Claude's output" }
9. scheduler.py receives response, handles:
   - NO_REPLY suppression
   - Garbage response detection
   - Discord channel posting
   - WhatsApp forwarding (if configured)
   - Second Brain capture
   - Job history recording
```

### Tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `reply` | `job_id` (string), `text` (string) | Return skill output to scheduler. Must use the job_id from the channel tag. |

### Key Implementation Details

- **Synchronous pattern:** The core mechanism is a `Map<string, PendingJob>` where each entry holds a Promise resolve function. The HTTP handler creates the Promise and awaits it; the reply tool resolves it. This turns the async MCP notification + tool call pattern into a synchronous HTTP request-response.
- **Timeout handling:** Default 3 minutes (`JOB_TIMEOUT_MS=180000`). If Claude does not call the reply tool within the timeout, the Promise resolves with an empty string and the scheduler treats it as a timeout. The scheduler adds a 30-second buffer on top of this for HTTP overhead.
- **No Discord posting:** The reply tool does NOT post to Discord. The `scheduler.py` handles all post-processing: chunking, Discord posting, WhatsApp forwarding, Second Brain capture, and job history recording. This keeps the channel focused on execution.
- **No Second Brain capture:** Same reason -- the scheduler handles this uniformly regardless of whether the job ran through the channel or through router_v2.
- **NO_REPLY convention:** If a skill determines there is nothing to report (e.g., a monitoring check with no issues), Claude calls reply with `text: "NO_REPLY"`. The scheduler suppresses output.
- **Health check:** `GET /health` returns `{ status: "ok", pending_jobs: N }` -- the pending job count is useful for debugging stuck jobs.

### Environment Variables

| Variable | Default | Required |
|----------|---------|----------|
| `HTTP_PORT` | `8103` | No |
| `JOB_TIMEOUT_MS` | `180000` (3 min) | No |

---

## 6. Session Lifecycle

### Auto-Start

When `bot.py` fires `on_ready`, it calls `_launch_channel_sessions()`:

1. For each channel (`peter-channel`, `whatsapp-channel`, `jobs-channel`):
   a. Checks if a tmux session with that name already exists (`tmux has-session`)
   b. If running, skips it (idempotent)
   c. If not running, launches: `tmux new-session -d -s <name> "bash launch.sh"`
2. Sessions are launched via `wsl bash -c "tmux ..."` from Windows (bot.py runs on Windows via NSSM)

### Launch Script Internals

Each `launch.sh` follows the same pattern:

1. Read environment variables from `.env` (handles Windows line endings with `tr -d "\r\n"`)
2. Write a temporary MCP config JSON to `/tmp/<name>-mcp.json`
3. `cd ~/peterbot` (shared working directory with all Peter config)
4. Enter infinite restart loop:
   ```bash
   while true; do
     claude \
       --mcp-config /tmp/<name>-mcp.json \
       --dangerously-load-development-channels server:<name> \
       --model claude-opus-4-6 \
       --effort medium \
       --dangerously-skip-permissions || true
     sleep 10
   done
   ```
5. If Claude Code exits (crash, error, OOM), it restarts after 10 seconds
6. Restart attempts are logged to `/tmp/<name>-restarts.log`

### Claude Code Flags

| Flag | Purpose |
|------|---------|
| `--mcp-config` | Points to the temporary MCP JSON with the channel server definition |
| `--dangerously-load-development-channels server:<name>` | Tells Claude Code to treat this MCP server as a channel source |
| `--model claude-opus-4-6` | Uses Opus 4.6 (1M context) for all channel sessions |
| `--effort medium` | Balances quality and cost for interactive use |
| `--dangerously-skip-permissions` | No confirmation prompts (required for unattended operation) |

### Process Tree

```
tmux server
  |-- tmux: peter-channel
  |     |-- bash launch.sh
  |           |-- claude (Claude Code CLI)
  |                 |-- npx tsx peter-channel/src/index.ts  (MCP subprocess)
  |                       |-- discord.js WebSocket (gateway)
  |
  |-- tmux: whatsapp-channel
  |     |-- bash launch.sh
  |           |-- claude (Claude Code CLI)
  |                 |-- npx tsx whatsapp-channel/src/index.ts  (MCP subprocess)
  |                       |-- HTTP server :8102
  |
  |-- tmux: jobs-channel
        |-- bash launch.sh
              |-- claude (Claude Code CLI)
                    |-- npx tsx jobs-channel/src/index.ts  (MCP subprocess)
                          |-- HTTP server :8103
```

---

## 7. Fallback and Resilience

Each channel has an independent fallback mechanism so that if a channel session dies, messages are still processed.

### Discord Fallback (Smart Detection)

```
bot.py on_message:
  if PETERBOT_USE_CHANNEL=1:
    Check if Peter H bot (ID 1487089363757043893) is online in the guild
    if online: return (let channel handle it)
    if offline: log warning, fall through to router_v2
  Process via router_v2 (stateless claude -p)
```

The "Peter H" Discord bot is the discord.js client inside peter-channel. When the channel session dies, the Discord bot goes offline, which bot.py detects via `guild.get_member().status`. This means fallback is automatic with no polling or health checks needed.

### WhatsApp Fallback (Port Routing)

```
hadley_api/whatsapp_webhook.py:
  if WHATSAPP_USE_CHANNEL=1:
    Forward to http://127.0.0.1:8102/whatsapp/message  (channel)
  else:
    Forward to http://127.0.0.1:8101/whatsapp/message  (bot.py handler)
```

The WhatsApp fallback is configured at startup via environment variable. If the channel is down, the HTTP POST to port 8102 fails and the message is lost. For true automatic fallback, set `WHATSAPP_USE_CHANNEL=0` and use the bot.py handler.

### Jobs Fallback (Exception-Based)

```python
# scheduler.py _send_to_jobs_channel()
try:
    resp = await client.post("http://127.0.0.1:8103/job", ...)
    return resp.json()["response"]
except httpx.TimeoutException:
    raise asyncio.TimeoutError(...)
except Exception as e:
    logger.error(f"Jobs channel error: {e}, falling back to CLI")
    return await self._send_to_claude_code_v2(context, job=job)
```

If the jobs-channel HTTP server is unreachable (connection refused, etc.), the scheduler automatically falls back to `_send_to_claude_code_v2()` which spawns an independent `claude -p` process. Timeouts are NOT retried via fallback -- they propagate as `asyncio.TimeoutError`.

### Fallback Summary

| Channel | Detection | Fallback Target | Automatic? |
|---------|-----------|-----------------|------------|
| Discord | Peter H bot online status | router_v2 (`claude -p`) | Yes |
| WhatsApp | Env var at startup | bot.py handler (:8101) | No (config change) |
| Jobs | HTTP connection error | `claude -p` per job | Yes |

---

## 8. Channel vs Router V2

| Aspect | Channels (Default) | Router V2 (Fallback) |
|--------|-------------------|---------------------|
| **Execution model** | Persistent session | New `claude -p` process per message |
| **Conversation state** | Maintained across messages | Rebuilt from memory buffer each time |
| **Startup overhead** | None (already running) | ~3-5s process spawn + model load |
| **Context window** | Accumulates over session lifetime | Fresh 200K context per request |
| **MCP tools** | Full access (loaded once) | Full access (loaded each time) |
| **Concurrency** | One message at a time per channel | Unlimited parallel processes |
| **Cost** | Lower (session reuse) | Higher (process overhead per message) |
| **Reliability** | Crash = 10s restart gap | Each request independent |
| **Memory** | Can reference earlier conversation | Must rely on Second Brain + buffer |

### When Channels Win

- Interactive conversations where context matters (follow-up questions)
- Rapid message sequences (no process spawn overhead)
- Scheduled jobs (session already warm, tools loaded)

### When Router V2 Wins

- Burst of concurrent messages (channels serialize)
- After context window fills up (fresh context is cleaner)
- Debugging (each request is isolated)

---

## 9. Configuration Reference

### Environment Variables (.env in project root)

| Variable | Values | Default | Effect |
|----------|--------|---------|--------|
| `PETERBOT_USE_CHANNEL` | `0` or `1` | `0` | Route Discord through peter-channel |
| `WHATSAPP_USE_CHANNEL` | `0` or `1` | `0` | Route WhatsApp through whatsapp-channel |
| `JOBS_USE_CHANNEL` | `0` or `1` | `0` | Route scheduled jobs through jobs-channel |

### Channel-Specific .env Files

**peter-channel/.env:**
```
DISCORD_BOT_TOKEN=<token for Peter H bot>
DISCORD_CHANNEL_IDS=<comma-separated channel IDs>
ALLOWED_DISCORD_IDS=<comma-separated user IDs>
```

**whatsapp-channel/.env:**
```
HTTP_PORT=8102
HADLEY_API=http://172.19.64.1:8100
```

**jobs-channel/.env:**
```
HTTP_PORT=8103
JOB_TIMEOUT_MS=180000
```

### Port Allocation

| Port | Service | Runs On |
|------|---------|---------|
| 8085 | Evolution API (WhatsApp) | Windows (Docker) |
| 8100 | Hadley API | Windows (NSSM) |
| 8101 | bot.py WhatsApp handler | Windows (NSSM) |
| 8102 | whatsapp-channel | WSL2 (tmux) |
| 8103 | jobs-channel | WSL2 (tmux) |

Note: `172.19.64.1` is the WSL2 host gateway IP, used by channel servers in WSL to reach Windows services.

---

## 10. Debugging and Logs

### Log Files

| File | Channel | Contents |
|------|---------|----------|
| `/tmp/peter-channel-app.log` | Discord | Message forwarding, reply sends, capture results |
| `/tmp/whatsapp-channel-app.log` | WhatsApp | Message forwarding, reply/voice sends |
| `/tmp/jobs-channel-app.log` | Jobs | Job receipt, completion times, timeouts |
| `/tmp/peter-channel-restarts.log` | Discord | Session start/exit timestamps |
| `/tmp/whatsapp-channel-restarts.log` | WhatsApp | Session start/exit timestamps |
| `/tmp/jobs-channel-restarts.log` | Jobs | Session start/exit timestamps |

All application logs use the format: `[ISO-8601] message`

### tmux Commands

```bash
# Attach to a channel session (read-only observation)
wsl bash -c "tmux attach -t peter-channel"
wsl bash -c "tmux attach -t whatsapp-channel"
wsl bash -c "tmux attach -t jobs-channel"

# Check if sessions are running
wsl bash -c "tmux ls"

# Kill a specific session (will auto-restart via bot.py on next on_ready)
wsl bash -c "tmux kill-session -t peter-channel"

# View recent log output
wsl bash -c "tail -50 /tmp/peter-channel-app.log"
wsl bash -c "tail -50 /tmp/jobs-channel-app.log"
```

### Health Checks

```bash
# WhatsApp channel
curl http://127.0.0.1:8102/health
# -> { "status": "ok" }

# Jobs channel
curl http://127.0.0.1:8103/health
# -> { "status": "ok", "pending_jobs": 0 }

# Discord channel has no HTTP server -- check via tmux or bot status
```

### Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Peter H bot offline in Discord | peter-channel session crashed | Check tmux, review `/tmp/peter-channel-restarts.log` |
| WhatsApp messages not reaching Peter | Channel session down or port 8102 blocked | Check `curl localhost:8102/health`, verify `WHATSAPP_USE_CHANNEL=1` |
| Jobs timing out | Claude taking too long, or session stuck | Check `/tmp/jobs-channel-app.log`, increase `JOB_TIMEOUT_MS` |
| Duplicate Discord responses | Both channel and router_v2 processing | Verify `PETERBOT_USE_CHANNEL=1` and Peter H is online |
| Messages lost after restart | 10s restart gap between session death and restart | Expected behavior; fallback should catch most |
| "Unknown tool" error in logs | MCP protocol mismatch | Rebuild with `npm install` in channel directory |

---

## 11. Adding a New Channel

To add a fourth channel (e.g., Telegram, email), follow this pattern:

1. **Create directory:** `<name>-channel/` with `src/index.ts`, `package.json`, `launch.sh`, `.env`

2. **MCP server structure:**
   ```typescript
   const mcp = new Server(
     { name: "<name>-channel", version: "0.0.1" },
     {
       capabilities: {
         experimental: { "claude/channel": {} },
         tools: {},
       },
       instructions: "<channel-specific instructions>",
     }
   );
   ```

3. **Message ingestion:** Either Discord gateway (like peter-channel) or HTTP server (like whatsapp/jobs)

4. **Reply tool(s):** Register tools that send responses back to the source

5. **Launch script:** Copy from an existing channel, update paths and env vars

6. **Register in bot.py:** Add to the `sessions` list in `_launch_channel_sessions()`

7. **Add fallback:** Add env var `<NAME>_USE_CHANNEL` and fallback logic in the appropriate handler

8. **Dependencies:** `npm install @modelcontextprotocol/sdk` plus any source-specific SDK
