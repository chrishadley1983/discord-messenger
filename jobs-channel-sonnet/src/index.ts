/**
 * Jobs Channel (Sonnet) — Claude Code channel for Sonnet-tier scheduled jobs.
 *
 * Identical contract to jobs-channel/src/index.ts: scheduler POSTs to /job,
 * server pushes context into the running session, the `reply` tool resolves
 * the pending HTTP request synchronously.
 *
 * Different binding: HTTP port 8105 (vs 8103) and MCP server name
 * "jobs-channel-sonnet" so transcript tags say `<channel source="jobs-channel-sonnet">`.
 * The underlying Claude session is launched with --model claude-sonnet-4-6 by
 * launch.sh, so the model choice is at the session level, not in this server.
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

const LOG_FILE = "/tmp/jobs-channel-sonnet-app.log";
function log(msg: string) {
  const line = `[${new Date().toISOString()}] ${msg}`;
  console.error(line);
  try { appendFileSync(LOG_FILE, line + "\n"); } catch {}
}

const HTTP_PORT = parseInt(process.env.HTTP_PORT || "8105", 10);
const JOB_TIMEOUT_MS = parseInt(process.env.JOB_TIMEOUT_MS || "180000", 10);

let jobsIn = 0;
let jobsOut = 0;
const sessionStart = new Date().toISOString();

interface PendingJob {
  resolve: (text: string) => void;
  timer: NodeJS.Timeout;
  skill: string;
  startTime: number;
}

const pendingJobs = new Map<string, PendingJob>();

const CHANNEL_INSTRUCTIONS = `
Scheduled job requests arrive as <channel source="jobs-channel-sonnet" job_id="..." skill="...">.
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

const mcp = new Server(
  { name: "jobs-channel-sonnet", version: "0.0.1" },
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
        "Return the job output to the scheduler. MUST include the job_id from the channel tag.",
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
      channel: "jobs-channel-sonnet",
      pending_jobs: pendingJobs.size,
      session_start: sessionStart,
      jobs_in: jobsIn,
      jobs_out: jobsOut,
    }));
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
  jobsIn++;
  log(`Job received: ${skill} (${jobId})`);

  try {
    const responsePromise = new Promise<string>((resolve) => {
      const timer = setTimeout(() => {
        pendingJobs.delete(jobId);
        log(`Job ${skill} (${jobId}) timed out after ${JOB_TIMEOUT_MS}ms`);
        resolve("");
      }, JOB_TIMEOUT_MS);

      pendingJobs.set(jobId, {
        resolve,
        timer,
        skill,
        startTime: Date.now(),
      });
    });

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
    const response = await responsePromise;

    jobsOut++;
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ response }));
  } catch (err) {
    log(`Job ${skill} error: ${err}`);
    res.writeHead(500);
    res.end(JSON.stringify({ error: String(err) }));
  }
});

async function main() {
  log("Starting jobs-channel-sonnet...");

  httpServer.listen(HTTP_PORT, "127.0.0.1", () => {
    log(`HTTP server listening on 127.0.0.1:${HTTP_PORT}`);
  });

  await mcp.connect(new StdioServerTransport());
  log("MCP server connected via stdio — ready for jobs!");
}

main().catch((err) => {
  log(`Fatal error: ${err}`);
  process.exit(1);
});
