/**
 * Peter Channel — Claude Code channel bridging Discord to a persistent session.
 *
 * This MCP server:
 * 1. Declares claude/channel capability (registers as a channel)
 * 2. Connects to Discord gateway and listens to #peter-channel-test
 * 3. Pushes messages into Claude Code session via notifications
 * 4. Exposes a reply() tool so Claude can send messages back to Discord
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { createServer, IncomingMessage, ServerResponse } from "http";
import {
  Client,
  Events,
  GatewayIntentBits,
  Partials,
  TextChannel,
  EmbedBuilder,
  AttachmentBuilder,
} from "discord.js";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const DISCORD_TOKEN = process.env.DISCORD_BOT_TOKEN;
if (!DISCORD_TOKEN) {
  throw new Error("DISCORD_BOT_TOKEN environment variable is required");
}

const CHANNEL_IDS = new Set(
  (process.env.DISCORD_CHANNEL_IDS || "").split(",").filter(Boolean)
);
if (CHANNEL_IDS.size === 0) {
  throw new Error("DISCORD_CHANNEL_IDS must contain at least one channel ID");
}

const ALLOWED_USERS = new Set(
  (process.env.ALLOWED_DISCORD_IDS || "").split(",").filter(Boolean)
);

// Chris's sender IDs — used for is_admin flag (self-modification gate)
const ADMIN_DISCORD_IDS = new Set(["1354023957677871156"]);
if (ALLOWED_USERS.size === 0) {
  throw new Error("ALLOWED_DISCORD_IDS must contain at least one user ID");
}

// ---------------------------------------------------------------------------
// Channel instructions — injected into Claude's system prompt
// ---------------------------------------------------------------------------

const CHANNEL_INSTRUCTIONS = `
Messages from Discord arrive as <channel source="peter-channel" chat_id="..." sender="...">.
Reply using the reply tool with the chat_id from the channel tag.

You are Peter, the Hadley family assistant. When replying via Discord:
- No markdown tables (Discord cannot render them) — use bullet lists instead
- No markdown headers (# Title) — use **bold** for emphasis
- Keep messages under 1500 characters where possible
- Never include tool call outputs, raw JSON, file contents, or terminal artifacts in your reply
- Never include thinking/reasoning narration ("Let me check...", "I'll look that up...")
- Only send your actual response to the user via the reply tool
- Your terminal output is NOT visible in Discord — only reply tool messages reach the user
- If you use tools (Second Brain, financial data, web search), summarise the results naturally

For multi-part responses, send one reply tool call with all the content — the tool handles chunking.
`.trim();

// ---------------------------------------------------------------------------
// MCP Server
// ---------------------------------------------------------------------------

const mcp = new Server(
  { name: "peter-channel", version: "0.0.1" },
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
// State: track last user message per channel (for Second Brain capture)
// ---------------------------------------------------------------------------

const lastUserMessage = new Map<string, string>();

// Message volume tracking for cost visibility
let messagesIn = 0;   // Messages received from Discord
let messagesOut = 0;  // Messages sent via reply tool
const sessionStart = new Date().toISOString();

// Hadley API base URL (accessible from WSL via host gateway)
const HADLEY_API = "http://172.19.64.1:8100";

// ---------------------------------------------------------------------------
// Reply tool — Claude calls this to send messages back to Discord
// ---------------------------------------------------------------------------

mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "reply",
      description:
        "Send a message back to the Discord channel. Handles chunking for messages over 2000 characters automatically.",
      inputSchema: {
        type: "object" as const,
        properties: {
          chat_id: {
            type: "string",
            description: "Discord channel ID (from the chat_id attribute in the channel tag)",
          },
          text: {
            type: "string",
            description: "The message to send",
          },
        },
        required: ["chat_id", "text"],
      },
    },
  ],
}));

mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  if (req.params.name !== "reply") {
    throw new Error(`Unknown tool: ${req.params.name}`);
  }

  const { chat_id, text } = req.params.arguments as {
    chat_id: string;
    text: string;
  };

  if (!text || text.trim().length === 0) {
    return { content: [{ type: "text" as const, text: "empty message, skipped" }] };
  }

  const channel = await discord.channels.fetch(chat_id);
  if (!channel || !(channel instanceof TextChannel)) {
    throw new Error(`Cannot send to channel ${chat_id} — not a text channel`);
  }

  // Chunk and send to Discord
  const chunks = splitAtBoundaries(text.trim(), 1950);
  for (const chunk of chunks) {
    await channel.send(chunk);
  }
  messagesOut++;

  // Fire-and-forget: capture conversation to Second Brain
  const userMsg = lastUserMessage.get(chat_id);
  if (userMsg) {
    fetch(`${HADLEY_API}/response/capture`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: text.trim(),
        user_message: userMsg,
        channel_id: chat_id,
        channel_name: channel.name ? `#${channel.name}` : undefined,
      }),
      signal: AbortSignal.timeout(10000),
    })
      .then((r) => log(`Capture: ${r.status}`))
      .catch((e) => log(`Capture failed (non-blocking): ${e}`));
  }

  return {
    content: [
      {
        type: "text" as const,
        text: `Sent ${chunks.length} message(s) to Discord`,
      },
    ],
  };
});

// ---------------------------------------------------------------------------
// Message chunking — respect Discord's 2000 char limit
// ---------------------------------------------------------------------------

function splitAtBoundaries(text: string, maxLen: number): string[] {
  if (text.length <= maxLen) return [text];

  const chunks: string[] = [];
  let remaining = text;

  while (remaining.length > 0) {
    if (remaining.length <= maxLen) {
      chunks.push(remaining);
      break;
    }

    // Try to split at natural boundaries (search backwards from maxLen)
    let splitAt = -1;

    // 1. Paragraph break
    const paraIdx = remaining.lastIndexOf("\n\n", maxLen);
    if (paraIdx > maxLen * 0.3) {
      splitAt = paraIdx + 2; // include the double newline
    }

    // 2. Single newline
    if (splitAt === -1) {
      const nlIdx = remaining.lastIndexOf("\n", maxLen);
      if (nlIdx > maxLen * 0.3) {
        splitAt = nlIdx + 1;
      }
    }

    // 3. Sentence end
    if (splitAt === -1) {
      const sentenceEnd = Math.max(
        remaining.lastIndexOf(". ", maxLen),
        remaining.lastIndexOf("! ", maxLen),
        remaining.lastIndexOf("? ", maxLen)
      );
      if (sentenceEnd > maxLen * 0.3) {
        splitAt = sentenceEnd + 2;
      }
    }

    // 4. Hard break
    if (splitAt === -1) {
      splitAt = maxLen;
    }

    chunks.push(remaining.slice(0, splitAt));
    remaining = remaining.slice(splitAt);
  }

  return chunks;
}

// ---------------------------------------------------------------------------
// Discord client
// ---------------------------------------------------------------------------

const discord = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
  ],
  partials: [Partials.Channel],
});

discord.on(Events.ClientReady, () => {
  log(`Discord connected as ${discord.user?.tag} — listening to ${CHANNEL_IDS.size} channels`);
});

discord.on(Events.MessageCreate, async (message) => {
  // Ignore bots (including ourselves)
  if (message.author.bot) return;

  // Only listen to configured channels
  if (!CHANNEL_IDS.has(message.channelId)) return;

  // Sender allowlist — prevents prompt injection from other users
  if (!ALLOWED_USERS.has(message.author.id)) {
    log(`Ignored message from non-allowed user: ${message.author.username} (${message.author.id})`);
    return;
  }

  // Build message content including any attachment URLs
  let content = message.content || "";
  if (message.attachments.size > 0) {
    const attachmentList = message.attachments
      .map((a) => `[${a.name}](${a.url})`)
      .join("\n");
    content += `\n\nAttachments:\n${attachmentList}`;
  }

  if (!content.trim()) return;

  // Track last user message per channel (for Second Brain capture in reply tool)
  lastUserMessage.set(message.channelId, content);

  // Fetch recent channel history so Claude has context of what was previously
  // said in this channel — critical for replies to scheduled job output that
  // bypasses Claude's session (posted directly via HTTP :8104).
  let recentHistory = "";
  try {
    const channel = message.channel as TextChannel;
    const history = await channel.messages.fetch({ limit: 6, before: message.id });
    if (history.size > 0) {
      const lines: string[] = [];
      // Reverse to chronological order (oldest first)
      const sorted = [...history.values()].reverse();
      for (const msg of sorted) {
        const who = msg.author.bot ? "Peter" : msg.author.username;
        const text = msg.content || "";
        if (!text.trim()) continue;
        // Truncate long messages (scheduled job output can be huge)
        // 1500 chars keeps enough context for skill follow-ups (e.g. pocket money grid)
        const truncated = text.length > 1500 ? text.slice(0, 1500) + "..." : text;
        lines.push(`${who}: ${truncated}`);
      }
      if (lines.length > 0) {
        recentHistory = "\n\n[Recent channel history for context]\n" + lines.join("\n");
      }
    }
  } catch (err) {
    log(`Failed to fetch channel history: ${err}`);
  }

  // Check for active skill context from a recent conversational scheduled job.
  // When a job like pocket-money-weekly posts output, Chris may reply in this
  // channel. The skill instructions tell Claude how to handle the follow-up
  // (e.g. how to credit balances). Without this, Claude has no skill context.
  let skillContext = "";
  try {
    if (existsSync(ACTIVE_SKILL_CONTEXT_PATH)) {
      const raw = readFileSync(ACTIVE_SKILL_CONTEXT_PATH, "utf-8");
      const ctx = JSON.parse(raw);
      const age = (Date.now() - new Date(ctx.timestamp).getTime()) / 60000;
      const ttl = ctx.ttl_minutes || 60;
      if (age <= ttl) {
        skillContext =
          `\n\n[Active scheduled skill: ${ctx.skill}]\n` +
          `This skill recently posted output to this channel. ` +
          `The user may be responding to it. Follow the skill instructions below to handle their reply.\n\n` +
          ctx.skill_content;
        log(`Injected active skill context: ${ctx.skill} (${Math.round(age)}m old)`);
      }
    }
  } catch (err) {
    log(`Failed to read active skill context: ${err}`);
  }

  // Push into Claude Code session
  try {
    await mcp.notification({
      method: "notifications/claude/channel",
      params: {
        content: content + recentHistory + skillContext,
        meta: {
          chat_id: message.channelId,
          channel_name: (message.channel as TextChannel).name || "unknown",
          sender: message.author.username,
          sender_id: message.author.id,
          is_admin: String(ADMIN_DISCORD_IDS.has(message.author.id)),
        },
      },
    });
    messagesIn++;
    log(`Forwarded message from ${message.author.username}: ${content.slice(0, 80)}...`);
  } catch (err) {
    log(`Failed to forward message: ${err}`);
  }
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

import { appendFileSync, readFileSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __filename_local = fileURLToPath(import.meta.url);
const __dirname_local = dirname(__filename_local);
const PROJECT_ROOT = resolve(__dirname_local, "..", "..");
const ACTIVE_SKILL_CONTEXT_PATH = resolve(PROJECT_ROOT, "data", "active_skill_context.json");

const LOG_FILE = "/tmp/peter-channel-app.log";
function log(msg: string) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.error(line);
  try { appendFileSync(LOG_FILE, line + "\n"); } catch {}
}

// ---------------------------------------------------------------------------
// HTTP server — scheduler.py posts pre-processed messages here for delivery
// ---------------------------------------------------------------------------

const HTTP_PORT = parseInt(process.env.HTTP_PORT || "8104", 10);

function parseBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks).toString()));
    req.on("error", reject);
  });
}

interface PostRequest {
  channel_id: string;
  chunks: string[];
  embed?: Record<string, any>;
  embeds?: Record<string, any>[];
  files?: Array<{ data: string; filename: string }>;
}

const httpServer = createServer(async (req: IncomingMessage, res: ServerResponse) => {
  // Health check
  if (req.method === "GET" && req.url === "/health") {
    const discordOk = discord.isReady();
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      status: "ok",
      discord: discordOk ? "connected" : "disconnected",
      session_start: sessionStart,
      messages_in: messagesIn,
      messages_out: messagesOut,
    }));
    return;
  }

  // Post message to Discord channel
  if (req.method === "POST" && req.url === "/post") {
    let body: PostRequest;
    try {
      body = JSON.parse(await parseBody(req));
    } catch {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "invalid JSON" }));
      return;
    }

    const { channel_id, chunks, embed, embeds, files } = body;
    if (!channel_id || !chunks || !Array.isArray(chunks)) {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "channel_id and chunks[] required" }));
      return;
    }

    try {
      const channel = await discord.channels.fetch(channel_id);
      if (!channel || !(channel instanceof TextChannel)) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: `Channel ${channel_id} not found or not a text channel` }));
        return;
      }

      let messagesSent = 0;

      // Build file attachments from base64
      const attachments: AttachmentBuilder[] = [];
      if (files && files.length > 0) {
        for (const f of files) {
          attachments.push(new AttachmentBuilder(Buffer.from(f.data, "base64"), { name: f.filename }));
        }
      }

      // Send text chunks
      for (let i = 0; i < chunks.length; i++) {
        const chunk = chunks[i];
        if (!chunk.trim()) continue;

        if (i === 0) {
          // First chunk: attach embed and files
          const opts: any = {};
          if (embed) opts.embeds = [new EmbedBuilder(embed)];
          if (attachments.length > 0) opts.files = attachments;
          await channel.send({ content: chunk, ...opts });
        } else {
          await channel.send(chunk);
        }
        messagesSent++;
      }

      // Send additional embeds after all text chunks
      if (embeds && embeds.length > 0) {
        for (const e of embeds) {
          await channel.send({ embeds: [new EmbedBuilder(e)] });
          messagesSent++;
        }
      }

      log(`POST /post: sent ${messagesSent} messages to ${channel_id}`);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true, messages_sent: messagesSent }));
    } catch (err) {
      log(`POST /post error: ${err}`);
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: String(err) }));
    }
    return;
  }

  res.writeHead(404);
  res.end("not found");
});

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  log("Starting peter-channel...");

  // Start HTTP server for scheduler delivery
  httpServer.listen(HTTP_PORT, "127.0.0.1", () => {
    log(`HTTP server listening on 127.0.0.1:${HTTP_PORT}`);
  });

  // Start Discord login first (non-blocking — gateway handshake runs in background)
  const discordReady = discord.login(DISCORD_TOKEN);
  log("Discord login initiated...");

  // Connect MCP server over stdio (Claude Code spawns us as subprocess)
  // This must complete for Claude Code to recognize us as a channel
  await mcp.connect(new StdioServerTransport());
  log("MCP server connected via stdio");

  // Wait for Discord to finish connecting
  await discordReady;
  log("Discord gateway connected — ready for messages!");
}

main().catch((err) => {
  console.error("[peter-channel] Fatal error:", err);
  process.exit(1);
});
