/**
 * Jobs Channel — Claude Code channel for scheduled job execution.
 *
 * Provides a synchronous HTTP interface for scheduler.py:
 * 1. Scheduler POSTs job context to /job
 * 2. MCP server pushes context into persistent Claude Code session
 * 3. Claude processes the skill, calls reply tool with output
 * 4. Reply tool resolves the pending HTTP request
 * 5. Scheduler receives response synchronously
 *
 * The reply tool does NOT post to Discord or capture to Second Brain.
 * Scheduler.py handles all post-processing (same as today).
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

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------

const LOG_FILE = "/tmp/jobs-channel-app.log";
function log(msg: string) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.error(line);
  try { appendFileSync(LOG_FILE, line + "\n"); } catch {}
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const HTTP_PORT = parseInt(process.env.HTTP_PORT || "8103", 10);
const JOB_TIMEOUT_MS = parseInt(process.env.JOB_TIMEOUT_MS || "180000", 10); // 3 min default

// ---------------------------------------------------------------------------
// Synchronous coordination: pending jobs
// ---------------------------------------------------------------------------

interface PendingJob {
  resolve: (text: string) => void;
  timer: NodeJS.Timeout;
  skill: string;
  startTime: number;
}

const pendingJobs = new Map<string, PendingJob>();

// ---------------------------------------------------------------------------
// Channel instructions
// ---------------------------------------------------------------------------

const CHANNEL_INSTRUCTIONS = `
Scheduled job requests arrive as <channel source="jobs-channel" job_id="..." skill="...">.
The content contains the full skill instructions and any pre-fetched data.

Execute the skill instructions exactly. Produce output formatted for Discord.
When done, call the reply tool with the job_id from the tag and your output text.

If there is genuinely nothing to report, call reply with text "NO_REPLY".

IMPORTANT:
- Do NOT post to Discord yourself — the scheduler handles posting
- Do NOT save to Second Brain — the scheduler handles that
- Just produce the output and call reply with the job_id
- The job_id MUST match the one from the channel tag
`.trim();

// ---------------------------------------------------------------------------
// MCP Server
// ---------------------------------------------------------------------------

const mcp = new Server(
  { name: "jobs-channel", version: "0.0.1" },
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
// Reply tool — resolves the pending HTTP request
// ---------------------------------------------------------------------------

mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "reply",
      description:
        "Return the job output to the scheduler. MUST include the job_id from the channel tag. The scheduler handles Discord posting and Second Brain capture.",
      inputSchema: {
        type: "object" as const,
        properties: {
          job_id: {
            type: "string",
            description: "The job_id from the channel tag (required for routing the response)",
          },
          text: {
            type: "string",
            description: "The skill output text (or 'NO_REPLY' if nothing to report)",
          },
        },
        required: ["job_id", "text"],
      },
    },
  ],
}));

mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  if (req.params.name !== "reply") {
    throw new Error(`Unknown tool: ${req.params.name}`);
  }

  const { job_id, text } = req.params.arguments as {
    job_id: string;
    text: string;
  };

  const pending = pendingJobs.get(job_id);
  if (pending) {
    const elapsed = Date.now() - pending.startTime;
    clearTimeout(pending.timer);
    pendingJobs.delete(job_id);
    pending.resolve(text || "");
    log(`Job ${pending.skill} completed in ${elapsed}ms (${text.length} chars)`);
  } else {
    log(`Reply for unknown job_id ${job_id} — may have timed out`);
  }

  return {
    content: [{ type: "text" as const, text: "delivered to scheduler" }],
  };
});

// ---------------------------------------------------------------------------
// HTTP server — receives job requests from scheduler.py
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
    res.end(JSON.stringify({ status: "ok", pending_jobs: pendingJobs.size }));
    return;
  }

  if (req.method !== "POST" || req.url !== "/job") {
    res.writeHead(404);
    res.end("not found");
    return;
  }

  let body: { context: string; skill: string };
  try {
    body = JSON.parse(await parseBody(req));
  } catch {
    res.writeHead(400);
    res.end(JSON.stringify({ error: "invalid JSON" }));
    return;
  }

  const { context, skill } = body;
  if (!context || !skill) {
    res.writeHead(400);
    res.end(JSON.stringify({ error: "context and skill required" }));
    return;
  }

  const jobId = randomUUID();
  log(`Job received: ${skill} (${jobId})`);

  try {
    // Create promise that reply tool will resolve
    const responsePromise = new Promise<string>((resolve) => {
      const timer = setTimeout(() => {
        pendingJobs.delete(jobId);
        log(`Job ${skill} (${jobId}) timed out after ${JOB_TIMEOUT_MS}ms`);
        resolve(""); // Empty = timeout (scheduler handles this)
      }, JOB_TIMEOUT_MS);

      pendingJobs.set(jobId, {
        resolve,
        timer,
        skill,
        startTime: Date.now(),
      });
    });

    // Push job into Claude Code session
    await mcp.notification({
      method: "notifications/claude/channel",
      params: {
        content: context,
        meta: {
          job_id: jobId,
          skill,
        },
      },
    });

    log(`Job ${skill} (${jobId}) pushed to session, waiting for reply...`);

    // Wait for reply tool to resolve the promise
    const response = await responsePromise;

    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ response }));
  } catch (err) {
    log(`Job ${skill} error: ${err}`);
    res.writeHead(500);
    res.end(JSON.stringify({ error: String(err) }));
  }
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

async function main() {
  log("Starting jobs-channel...");

  // Start HTTP server
  httpServer.listen(HTTP_PORT, "127.0.0.1", () => {
    log(`HTTP server listening on 127.0.0.1:${HTTP_PORT}`);
  });

  // Connect MCP server over stdio
  await mcp.connect(new StdioServerTransport());
  log("MCP server connected via stdio — ready for jobs!");
}

main().catch((err) => {
  log(`Fatal error: ${err}`);
  process.exit(1);
});
