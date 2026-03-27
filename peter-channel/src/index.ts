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
import {
  Client,
  Events,
  GatewayIntentBits,
  Partials,
  TextChannel,
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

  // Push into Claude Code session
  try {
    await mcp.notification({
      method: "notifications/claude/channel",
      params: {
        content,
        meta: {
          chat_id: message.channelId,
          channel_name: (message.channel as TextChannel).name || "unknown",
          sender: message.author.username,
          sender_id: message.author.id,
          is_admin: String(ADMIN_DISCORD_IDS.has(message.author.id)),
        },
      },
    });
    log(`Forwarded message from ${message.author.username}: ${content.slice(0, 80)}...`);
  } catch (err) {
    log(`Failed to forward message: ${err}`);
  }
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

import { appendFileSync } from "fs";
const LOG_FILE = "/tmp/peter-channel-app.log";
function log(msg: string) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.error(line);
  try { appendFileSync(LOG_FILE, line + "\n"); } catch {}
}

async function main() {
  log("Starting peter-channel...");

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
