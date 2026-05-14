/**
 * Extract Channel — Claude Code channel for one-shot prompt extractions.
 *
 * Replaces the `claude -p` subprocess in hadley_api/claude_routes.py.
 * Same synchronous request/response contract:
 *   POST /extract  body: {prompt: string}  →  {response: string}
 *
 * Persistent Claude Code session running Haiku 4.5 (cheap, fast) ensures
 * every /claude/extract call goes through the subscription rather than
 * spawning a programmatic `claude -p`.
 */

import { createServer, IncomingMessage, ServerResponse } from "http";
import { randomUUID } from "crypto";
import { appendFileSync } from "fs";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

const LOG_FILE = "/tmp/extract-channel-app.log";
function log(msg: string) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.error(line);
  try { appendFileSync(LOG_FILE, line + "\n"); } catch {}
}

const HTTP_PORT = parseInt(process.env.HTTP_PORT || "8106", 10);
const REQUEST_TIMEOUT_MS = parseInt(process.env.REQUEST_TIMEOUT_MS || "90000", 10); // 90s default

let reqIn = 0;
let reqOut = 0;
const sessionStart = new Date().toISOString();

interface PendingRequest {
  resolve: (text: string) => void;
  timer: NodeJS.Timeout;
  startTime: number;
}

const pendingRequests = new Map<string, PendingRequest>();

const CHANNEL_INSTRUCTIONS = `
Extraction requests arrive as <channel source="extract-channel" request_id="...">.
The content is a raw prompt — no skill framing, no Discord formatting.

Read the prompt, produce the extraction result, then call the reply tool
with the request_id from the tag and your result text.

IMPORTANT:
- Output ONLY what the prompt asked for. No commentary, no explanation.
- Do NOT post to Discord or save to Second Brain — the caller handles output.
- The request_id MUST match the one from the channel tag.
- Keep responses focused — these are one-shot extractions, not conversations.
`.trim();

const mcp = new Server(
  { name: "extract-channel", version: "0.0.1" },
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

mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "reply",
      description:
        "Return the extraction result to the caller. MUST include the request_id from the channel tag.",
      inputSchema: {
        type: "object" as const,
        properties: {
          request_id: {
            type: "string",
            description: "The request_id from the channel tag (required for routing the response)",
          },
          text: {
            type: "string",
            description: "The extraction result text",
          },
        },
        required: ["request_id", "text"],
      },
    },
  ],
}));

mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  if (req.params.name !== "reply") {
    throw new Error(`Unknown tool: ${req.params.name}`);
  }

  const { request_id, text } = req.params.arguments as {
    request_id: string;
    text: string;
  };

  const pending = pendingRequests.get(request_id);
  if (pending) {
    const elapsed = Date.now() - pending.startTime;
    clearTimeout(pending.timer);
    pendingRequests.delete(request_id);
    pending.resolve(text || "");
    log(`Request completed in ${elapsed}ms (${text.length} chars)`);
  } else {
    log(`Reply for unknown request_id ${request_id} — may have timed out`);
  }

  return {
    content: [{ type: "text" as const, text: "delivered to caller" }],
  };
});

function parseBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c) => chunks.push(c));
    req.on("end", () => resolve(Buffer.concat(chunks).toString()));
    req.on("error", reject);
  });
}

const httpServer = createServer(async (req: IncomingMessage, res: ServerResponse) => {
  if (req.method === "GET" && req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      status: "ok",
      channel: "extract-channel",
      pending: pendingRequests.size,
      session_start: sessionStart,
      requests_in: reqIn,
      requests_out: reqOut,
    }));
    return;
  }

  if (req.method !== "POST" || req.url !== "/extract") {
    res.writeHead(404);
    res.end("not found");
    return;
  }

  let body: { prompt: string };
  try {
    body = JSON.parse(await parseBody(req));
  } catch {
    res.writeHead(400);
    res.end(JSON.stringify({ error: "invalid JSON" }));
    return;
  }

  const { prompt } = body;
  if (!prompt) {
    res.writeHead(400);
    res.end(JSON.stringify({ error: "prompt required" }));
    return;
  }

  const requestId = randomUUID();
  reqIn++;
  log(`Extract request: ${requestId} (${prompt.length} char prompt)`);

  try {
    const responsePromise = new Promise<string>((resolve) => {
      const timer = setTimeout(() => {
        pendingRequests.delete(requestId);
        log(`Request ${requestId} timed out after ${REQUEST_TIMEOUT_MS}ms`);
        resolve("");
      }, REQUEST_TIMEOUT_MS);

      pendingRequests.set(requestId, {
        resolve,
        timer,
        startTime: Date.now(),
      });
    });

    await mcp.notification({
      method: "notifications/claude/channel",
      params: {
        content: prompt,
        meta: {
          request_id: requestId,
        },
      },
    });

    log(`Request ${requestId} pushed to session, waiting for reply...`);
    const response = await responsePromise;

    reqOut++;
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ response }));
  } catch (err) {
    log(`Request ${requestId} error: ${err}`);
    res.writeHead(500);
    res.end(JSON.stringify({ error: String(err) }));
  }
});

async function main() {
  log("Starting extract-channel...");

  httpServer.listen(HTTP_PORT, "127.0.0.1", () => {
    log(`HTTP server listening on 127.0.0.1:${HTTP_PORT}`);
  });

  await mcp.connect(new StdioServerTransport());
  log("MCP server connected via stdio — ready for extractions!");
}

main().catch((err) => {
  log(`Fatal error: ${err}`);
  process.exit(1);
});
