# WhatsApp Channel — Implementation Plan

## Architecture

Separate persistent Claude Code session with a WhatsApp channel MCP server.
Runs alongside the Discord channel session — isolated, no concurrency risk.
Both share Second Brain for cross-platform memory.

```
Session 1: claude --channels server:discord-channel    ~/peterbot
Session 2: claude --channels server:whatsapp-channel   ~/peterbot
```

## Current Flow (What We're Replacing)

```
Evolution API webhook
  → hadley_api/whatsapp_webhook.py (debounce, dedup, voice transcription)
  → POST 127.0.0.1:8101/whatsapp/message
  → bot.py _whatsapp_handler
    → nag acknowledgment check (regex)
    → tag message: [WhatsApp DM from Chris]
    → inject pending actions + japan context
    → handle_peterbot() → router_v2 → spawn claude -p
    → send_text() / send_audio() back to WhatsApp
```

## New Flow

```
Evolution API webhook
  → hadley_api/whatsapp_webhook.py (debounce, dedup, voice transcription — UNCHANGED)
  → POST 127.0.0.1:8102/whatsapp/message  ← NEW PORT (channel MCP server)
  → WhatsApp channel MCP server
    → push notification to Claude Code session
    → Claude processes (has CLAUDE.md, tools, Second Brain)
    → Claude calls whatsapp:reply tool
      → send_text() to Evolution API
      → fire-and-forget POST /response/capture (Second Brain)
    → OR Claude calls whatsapp:voice_reply tool
      → synthesise() → send_audio() to Evolution API
```

## What Stays The Same

- **hadley_api/whatsapp_webhook.py** — debouncing, deduplication, voice note
  transcription, sender identification. All stays. Just change the forward URL.
- **integrations/whatsapp.py** — send_text(), send_audio() functions. Reused
  by the channel MCP server (imported or called via Hadley API).
- **WHATSAPP.md** — Response rules. Loaded by CLAUDE.md in the session.
- **voice_engine.py** — transcribe() and synthesise(). Already in Hadley API.

## What Changes

### 1. Webhook Forward URL

In `hadley_api/whatsapp_webhook.py`, change the forward target:

```python
# Old:
DISCORDBOT_WHATSAPP_URL = "http://127.0.0.1:8101/whatsapp/message"

# New (with fallback switch):
WHATSAPP_USE_CHANNEL = os.getenv("WHATSAPP_USE_CHANNEL", "0") == "1"
DISCORDBOT_WHATSAPP_URL = (
    "http://127.0.0.1:8102/whatsapp/message"  # Channel MCP server
    if WHATSAPP_USE_CHANNEL else
    "http://127.0.0.1:8101/whatsapp/message"  # bot.py handler (original)
)
```

Fallback: set `WHATSAPP_USE_CHANNEL=0` → routes back to bot.py.

### 2. WhatsApp Channel MCP Server

New file: `whatsapp-channel/src/index.ts`

Components:
- **MCP server** with `claude/channel` capability
- **HTTP server on port 8102** receiving forwarded messages from Hadley API
- **reply tool** — calls Hadley API `/whatsapp/send` to send text
- **voice_reply tool** — calls Hadley API `/whatsapp/send-voice` to send audio
- **Channel instructions** — WhatsApp-specific formatting rules
- **Last user message tracking** — for Second Brain capture

### 3. Send Functions — Use Hadley API, Not Direct Evolution

The channel MCP server runs in WSL. Instead of importing Python's
`integrations/whatsapp.py` directly, call the existing Hadley API endpoints:

```
POST http://172.19.64.1:8100/whatsapp/send?to={number}&message={text}
POST http://172.19.64.1:8100/whatsapp/send-voice (with body)
```

These already exist and handle markdown conversion, retry logic, etc.

### 4. Nag Acknowledgment

Currently handled in bot.py with regex BEFORE sending to Claude.
In the channel model: **Claude handles it natively.**

Claude already knows about nags (CLAUDE.md documents the API). When "done"
arrives on WhatsApp, Claude:
1. Checks active nags: `curl /reminders/active-nags?delivery=whatsapp:chris`
2. If found: `curl -X POST /reminders/{id}/acknowledge`
3. Replies: "Nice one, ticked off ✅"

The regex pre-check in bot.py becomes unnecessary. Claude is smarter about
edge cases ("yeah I'm done with that", "finished the physio").

### 5. Pending Actions

Currently injected into context by memory.py for WhatsApp messages.
In the channel model: Claude fetches them via API when relevant.

The channel instructions should tell Claude:
```
For WhatsApp messages, check for pending actions:
curl -s http://172.19.64.1:8100/schedule/pending-actions
If there are pending actions for this sender, present them for confirmation.
```

Or: the channel MCP server could pre-fetch pending actions and include them
in the notification meta.

### 6. Japan Context

Currently injected by memory.py during April 3-19 trip dates.
In the channel model: CLAUDE.md already references the JAPAN.md playbook.
Claude knows to check Japan context when relevant.

For active injection during the trip, the channel MCP server could:
- Check if current date is within trip range
- Pre-fetch japan context from Hadley API
- Include in notification meta or as a separate context push

### 7. Voice Input/Output

**Transcription** happens in hadley_api/whatsapp_webhook.py (faster-whisper)
BEFORE the message reaches the channel. The channel MCP server receives
already-transcribed text with `is_voice: true` flag.

**TTS reply** is triggered by the `voice_reply` tool:
```
POST http://172.19.64.1:8100/whatsapp/send-voice
Body: {"to": "chris", "text": "response text"}
```
Hadley API handles Kokoro TTS + Evolution API send.

## File Structure

```
whatsapp-channel/
├── .claude-plugin/
│   └── plugin.json
├── src/
│   └── index.ts          # MCP server + HTTP receiver + reply tools
├── package.json
├── tsconfig.json
├── .env
├── .gitignore
└── launch.sh             # WSL launch script
```

## Channel Instructions

```
Messages from WhatsApp arrive as:
<channel source="whatsapp" phone="447855620978" sender="Chris" is_voice="false">
Message text here
</channel>

Reply using the reply tool with the phone number from the tag.
For voice messages (is_voice="true"), also call voice_reply to send an audio response.

WhatsApp formatting rules:
- Keep replies short (1-3 sentences for casual, longer for requests)
- No markdown headers or code blocks
- **bold** works, _italic_ works, ~strikethrough~ works
- No bullet lists — use flowing sentences
- For voice replies: no formatting at all, conversational tone, 1-3 sentences max

When a message arrives, check for active nag reminders:
curl -s http://172.19.64.1:8100/reminders/active-nags?delivery=whatsapp:{sender_lowercase}
If the message looks like an acknowledgment ("done", "finished", etc.), acknowledge the nag.

Check for pending actions that need confirmation:
curl -s http://172.19.64.1:8100/schedule/pending-actions
```

## Build Order

1. **Create whatsapp-channel package** — package.json, tsconfig, deps
2. **Build MCP server** — channel capability, HTTP receiver on 8102, reply + voice_reply tools
3. **Add fallback switch** to whatsapp_webhook.py — WHATSAPP_USE_CHANNEL env var
4. **Create launch script** — separate tmux session for WhatsApp channel
5. **Test end-to-end** — send WhatsApp message, verify reply arrives
6. **Test voice** — send voice note, verify text + audio reply
7. **Test nag acknowledgment** — send "done", verify nag cleared
8. **Test Second Brain capture** — verify conversations captured

## Risks

| Risk | Mitigation |
|------|------------|
| Session crashes | launch.sh restart loop, same as Discord channel |
| Voice transcription delay | Transcription stays in Hadley API (unchanged) |
| Nag acknowledgment misses | Claude is smarter than regex — handles more patterns |
| Port 8102 conflict | Check at startup, fail loudly |
| Evolution API down | Same as today — send functions have retry logic |

## Rollback

Set `WHATSAPP_USE_CHANNEL=0` in .env, restart Hadley API.
WhatsApp routes back to bot.py handler instantly.
