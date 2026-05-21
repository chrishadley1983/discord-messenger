/**
 * WhatsApp Channel — Claude Code channel bridging WhatsApp to a persistent session.
 *
 * This MCP server:
 * 1. Declares claude/channel capability
 * 2. Runs an HTTP server (port 8102) receiving forwarded messages from Hadley API
 * 3. Pushes messages into Claude Code session via notifications
 * 4. Exposes reply() and voice_reply() tools that send back via Hadley API
 */

import { createServer, IncomingMessage, ServerResponse } from "http";
import { appendFileSync } from "fs";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

// ---------------------------------------------------------------------------
// Logging (file-based — stderr may not be captured by Claude Code)
// ---------------------------------------------------------------------------

const LOG_FILE = "/tmp/whatsapp-channel-app.log";
function log(msg: string) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.error(line);
  try { appendFileSync(LOG_FILE, line + "\n"); } catch {}
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const HTTP_PORT = parseInt(process.env.HTTP_PORT || "8102", 10);
const HADLEY_API = process.env.HADLEY_API || "http://172.19.64.1:8100";
const HADLEY_AUTH_KEY = process.env.HADLEY_AUTH_KEY || "";

// ---------------------------------------------------------------------------
// State: track last user message per sender (for Second Brain capture)
// ---------------------------------------------------------------------------

const lastUserMessage = new Map<string, string>();
const messageStartTime = new Map<string, number>();

// LRU cap so per-sender state maps don't grow unbounded across long sessions
const STATE_MAP_MAX = 1000;
function trimState<K, V>(m: Map<K, V>) {
  while (m.size > STATE_MAP_MAX) {
    const oldest = m.keys().next().value;
    if (oldest === undefined) break;
    m.delete(oldest);
  }
}

function hadleyHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json", ...extra };
  if (HADLEY_AUTH_KEY) h["x-api-key"] = HADLEY_AUTH_KEY;
  return h;
}

// Message volume tracking
let messagesIn = 0;
let messagesOut = 0;
const sessionStart = new Date().toISOString();

// Chris's WhatsApp number — used for is_admin flag (self-modification gate)
const ADMIN_WHATSAPP_NUMBERS = new Set(["447855620978"]);

// ---------------------------------------------------------------------------
// Channel instructions
// ---------------------------------------------------------------------------

const CHANNEL_INSTRUCTIONS = `
Messages from WhatsApp arrive as <channel source="whatsapp" phone="..." sender="..." is_voice="..." is_group="...">.
Reply using the reply tool with the phone number from the tag.
For voice messages (is_voice="true"), ALSO call voice_reply to send an audio response after the text reply.

You are Peter, the Hadley family assistant. WhatsApp formatting rules:
- Keep replies short (1-3 sentences for casual, longer for detailed requests)
- **bold** and _italic_ work on WhatsApp
- No markdown headers, code blocks, or bullet lists — use flowing sentences
- For voice replies: no formatting at all, pure conversational tone, 1-3 sentences max
- Never include tool outputs, raw JSON, or terminal artifacts

When a WhatsApp message arrives:
1. Check for active nag reminders: curl -s http://172.19.64.1:8100/reminders/active-nags?delivery=whatsapp:{sender_lowercase}
   If the message looks like acknowledgment ("done", "finished", "completed", "stop", etc.), acknowledge the nag via curl -s -X POST http://172.19.64.1:8100/reminders/{id}/acknowledge
2. Check for pending actions: curl -s http://172.19.64.1:8100/schedule/pending-actions
   If there are pending actions for this sender, present for confirmation
3. Otherwise, respond normally

Your terminal output is NOT visible on WhatsApp — only reply/voice_reply tool messages reach the user.
`.trim();

// ---------------------------------------------------------------------------
// MCP Server
// ---------------------------------------------------------------------------

const mcp = new Server(
  { name: "whatsapp-channel", version: "0.0.1" },
  {
    capabilities: {
      experimental: {
        "claude/channel": {},
      },
      tools: {},
    },
    instructions: CHANNEL_INSTRUCTIONS,
  }
);

// ---------------------------------------------------------------------------
// Tools: reply + voice_reply
// ---------------------------------------------------------------------------

mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "reply",
      description:
        "Send a text message back to WhatsApp via Hadley API. Use for all responses.",
      inputSchema: {
        type: "object" as const,
        properties: {
          phone: {
            type: "string",
            description: "Phone number or contact name (from the phone attribute in the channel tag)",
          },
          text: {
            type: "string",
            description: "The message to send",
          },
        },
        required: ["phone", "text"],
      },
    },
    {
      name: "voice_reply",
      description:
        "Send a voice note to WhatsApp (TTS). Use AFTER reply when the incoming message was a voice note (is_voice=true). Keep text short and conversational — no formatting.",
      inputSchema: {
        type: "object" as const,
        properties: {
          phone: {
            type: "string",
            description: "Phone number or contact name",
          },
          text: {
            type: "string",
            description: "Text to convert to speech and send as voice note. Keep short, no formatting.",
          },
        },
        required: ["phone", "text"],
      },
    },
  ],
}));

mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name } = req.params;
  const args = req.params.arguments as Record<string, string>;

  if (name === "reply") {
    return await handleReply(args.phone, args.text);
  } else if (name === "voice_reply") {
    return await handleVoiceReply(args.phone, args.text);
  }
  throw new Error(`Unknown tool: ${name}`);
});

// ---------------------------------------------------------------------------
// Reply handler — send text via Hadley API
// ---------------------------------------------------------------------------

async function handleReply(phone: string, text: string) {
  if (!text || !text.trim()) {
    return { content: [{ type: "text" as const, text: "empty message, skipped" }] };
  }

  try {
    const url = `${HADLEY_API}/whatsapp/send?to=${encodeURIComponent(phone)}&message=${encodeURIComponent(text.trim())}`;
    const headers: Record<string, string> = {};
    if (HADLEY_AUTH_KEY) headers["x-api-key"] = HADLEY_AUTH_KEY;
    const resp = await fetch(url, {
      method: "POST",
      headers,
      signal: AbortSignal.timeout(30000),
    });

    if (!resp.ok) {
      const body = await resp.text();
      log(`Reply failed: ${resp.status} ${body}`);
      return { content: [{ type: "text" as const, text: `Send failed: ${resp.status}` }] };
    }

    messagesOut++;
    log(`Reply sent to ${phone}: ${text.trim().slice(0, 80)}...`);
  } catch (err) {
    log(`Reply error: ${err}`);
    return { content: [{ type: "text" as const, text: `Send error: ${err}` }] };
  }

  // Fire-and-forget: capture to Second Brain
  const userMsg = lastUserMessage.get(phone);
  if (userMsg) {
    fetch(`${HADLEY_API}/response/capture`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: text.trim(),
        user_message: userMsg,
        channel_name: "#whatsapp",
      }),
      signal: AbortSignal.timeout(10000),
    })
      .then((r) => log(`Capture: ${r.status}`))
      .catch((e) => log(`Capture failed (non-blocking): ${e}`));
  }

  // Fire-and-forget: log channel turn for dashboard parity
  const startedAt = messageStartTime.get(phone);
  const durationMs = startedAt ? Date.now() - startedAt : 0;
  fetch(`${HADLEY_API}/response/cost`, {
    method: "POST",
    headers: hadleyHeaders(),
    body: JSON.stringify({
      source: "channel:whatsapp",
      channel: "WhatsApp",
      message_preview: (userMsg || "").slice(0, 80),
      duration_ms: durationMs,
      response_chars: text.trim().length,
    }),
    signal: AbortSignal.timeout(5000),
  }).catch((e) => log(`Cost log failed (non-blocking): ${e}`));

  return { content: [{ type: "text" as const, text: `Sent text to ${phone}` }] };
}

// ---------------------------------------------------------------------------
// Voice reply handler — TTS + send via Hadley API
// ---------------------------------------------------------------------------

async function handleVoiceReply(phone: string, text: string) {
  if (!text || !text.trim()) {
    return { content: [{ type: "text" as const, text: "empty voice, skipped" }] };
  }

  try {
    const url = `${HADLEY_API}/whatsapp/send-voice?to=${encodeURIComponent(phone)}&message=${encodeURIComponent(text.trim())}`;
    const headers: Record<string, string> = {};
    if (HADLEY_AUTH_KEY) headers["x-api-key"] = HADLEY_AUTH_KEY;
    const resp = await fetch(url, {
      method: "POST",
      headers,
      signal: AbortSignal.timeout(30000),
    });

    if (!resp.ok) {
      const body = await resp.text();
      log(`Voice reply failed: ${resp.status} ${body}`);
      return { content: [{ type: "text" as const, text: `Voice send failed: ${resp.status}` }] };
    }

    log(`Voice reply sent to ${phone}`);
  } catch (err) {
    log(`Voice reply error: ${err}`);
    return { content: [{ type: "text" as const, text: `Voice send error: ${err}` }] };
  }

  return { content: [{ type: "text" as const, text: `Sent voice note to ${phone}` }] };
}

// ---------------------------------------------------------------------------
// HTTP server — receives forwarded messages from Hadley API webhook
// ---------------------------------------------------------------------------

function parseBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks).toString()));
    req.on("error", reject);
  });
}

const httpServer = createServer(async (req: IncomingMessage, res: ServerResponse) => {
  // Health check
  if (req.method === "GET" && req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      status: "ok",
      session_start: sessionStart,
      messages_in: messagesIn,
      messages_out: messagesOut,
    }));
    return;
  }

  if (req.method !== "POST" || req.url !== "/whatsapp/message") {
    res.writeHead(404);
    res.end("not found");
    return;
  }

  try {
    const body = JSON.parse(await parseBody(req)) as {
      sender_name: string;
      sender_number: string;
      reply_to: string;
      is_group: boolean;
      text: string;
      is_voice: boolean;
    };

    const { sender_name, sender_number, reply_to, is_group, text, is_voice } = body;

    if (!text || !text.trim()) {
      res.writeHead(200);
      res.end(JSON.stringify({ status: "skipped", reason: "empty" }));
      return;
    }

    // Track last user message for Second Brain capture
    lastUserMessage.set(reply_to, text);
    messageStartTime.set(reply_to, Date.now());
    trimState(lastUserMessage);
    trimState(messageStartTime);

    // Pre-build full context via Hadley API for parity with router_v2:
    // Japan trip context, pending-actions block, Second Brain surfacing,
    // channel isolation, UK time. On failure fall back to raw text.
    let prebuiltContext = text;
    try {
      const resp = await fetch(`${HADLEY_API}/peter/build-context`, {
        method: "POST",
        headers: hadleyHeaders(),
        body: JSON.stringify({
          message: text,
          channel_name: "WhatsApp",
          sender_number: sender_number,
          is_whatsapp: true,
          include_surfacing: true,
        }),
        signal: AbortSignal.timeout(3000),
      });
      if (resp.ok) {
        const json = (await resp.json()) as { context?: string; blocks?: string[]; surfaced_count?: number };
        if (json.context) {
          prebuiltContext = json.context;
          log(`build-context: ${(json.blocks || []).join(",")} (surfaced=${json.surfaced_count || 0})`);
        }
      } else {
        log(`build-context returned ${resp.status} — using raw text`);
      }
    } catch (err) {
      log(`build-context fetch failed (${err}) — using raw text`);
    }

    // Push into Claude Code session
    await mcp.notification({
      method: "notifications/claude/channel",
      params: {
        content: prebuiltContext,
        meta: {
          phone: reply_to,
          sender: sender_name,
          sender_number: sender_number,
          is_voice: String(is_voice),
          is_group: String(is_group),
          is_admin: String(ADMIN_WHATSAPP_NUMBERS.has(sender_number)),
        },
      },
    });

    messagesIn++;
    log(`Forwarded WhatsApp from ${sender_name}: ${text.slice(0, 80)}...`);
    res.writeHead(200);
    res.end(JSON.stringify({ status: "forwarded" }));
  } catch (err) {
    log(`HTTP handler error: ${err}`);
    res.writeHead(500);
    res.end(JSON.stringify({ error: String(err) }));
  }
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

async function main() {
  log("Starting whatsapp-channel...");

  // Start HTTP server first (non-blocking)
  httpServer.listen(HTTP_PORT, "127.0.0.1", () => {
    log(`HTTP server listening on 127.0.0.1:${HTTP_PORT}`);
  });

  // Connect MCP server over stdio
  await mcp.connect(new StdioServerTransport());
  log("MCP server connected via stdio — ready for messages!");
}

main().catch((err) => {
  log(`Fatal error: ${err}`);
  process.exit(1);
});
