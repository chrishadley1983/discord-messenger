# Jobs Channel — Implementation Plan

## Architecture

Third persistent Claude Code session dedicated to scheduled jobs.
Scheduler.py keeps its orchestration role — the only change is the
execution engine (channel session instead of `claude -p`).

```
Session 1: Discord conversations    (peter-channel, tmux peter-channel)
Session 2: WhatsApp conversations   (whatsapp-channel, tmux whatsapp-channel)
Session 3: Scheduled jobs           (jobs-channel, tmux jobs-channel)
```

## Design: Synchronous HTTP Interface

Scheduler.py needs the response back to do its post-processing (NO_REPLY,
garbage check, job history, Discord posting). So the jobs-channel HTTP
endpoint must be SYNCHRONOUS — scheduler POSTs and waits for the response.

```
scheduler.py                    jobs-channel MCP server
    │                                   │
    ├── POST /job ─────────────────────►│
    │   {skill, context, target}        │
    │                                   ├── push notification to Claude
    │                                   │   <channel source="jobs-channel"
    │       (waiting...)                │    skill="morning-briefing" ...>
    │                                   │
    │                                   ├── Claude processes skill
    │                                   │   (tool calls, API access, etc.)
    │                                   │
    │                                   ├── Claude calls reply tool
    │                                   │   reply(text="briefing output")
    │                                   │
    │                                   ├── reply tool resolves pending request
    │   ◄──────────────────────────────┤
    │   {response: "briefing output"}   │
    │                                   │
    ├── Check NO_REPLY                  │
    ├── Check garbage                   │
    ├── Post to Discord channel         │
    ├── Record job history              │
    ├── Capture to Second Brain         │
    └── Done                            │
```

Key: scheduler.py keeps ALL its post-processing logic. The jobs-channel
just replaces the `claude -p` invocation. Same interface, different engine.

## What Changes in Scheduler

One method replacement. `_send_to_claude_code_v2()` currently calls
`router_v2.invoke_llm()`. Replace with an HTTP POST to the jobs-channel:

```python
async def _send_to_jobs_channel(self, context: str, job: JobConfig) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://127.0.0.1:8103/job",
            json={"context": context, "skill": job.skill},
            timeout=self.JOB_TIMEOUT_SECONDS + 30,  # Extra buffer
        )
        return resp.json().get("response", "")
```

With a fallback switch:
```python
if JOBS_USE_CHANNEL:
    response = await self._send_to_jobs_channel(context, job)
else:
    response, provider = await invoke_llm(context=context, ...)
```

## Jobs-Channel MCP Server

Simpler than Discord/WhatsApp channels — no messaging platform integration.
Just an HTTP server + MCP channel + reply tool.

### Components

1. **HTTP server on port 8103** — receives job requests from scheduler.py
2. **MCP channel capability** — pushes job context into Claude session
3. **reply tool** — Claude calls this with the skill output
4. **Synchronous coordination** — HTTP handler waits for reply tool call

### Reply Tool Behavior

The reply tool in the jobs channel is different from Discord/WhatsApp:
- It does NOT post to Discord (scheduler.py handles that)
- It does NOT fire Second Brain capture (scheduler.py handles that)
- It just RETURNS the response text to the waiting HTTP handler

This keeps scheduler.py's post-processing intact:
- NO_REPLY check
- Garbage/reasoning leak detection
- Discord channel routing (including dual-channel, WhatsApp forwarding)
- Job history recording
- Second Brain auto-save for allowed skills

### Synchronous Coordination Pattern

```typescript
// Pending job promises — HTTP handler waits, reply tool resolves
const pendingJobs = new Map<string, {
  resolve: (text: string) => void;
  timer: NodeJS.Timeout;
}>();

// HTTP handler
app.post('/job', async (req, res) => {
  const jobId = crypto.randomUUID();
  const { context, skill } = req.body;

  // Create promise that reply tool will resolve
  const response = await new Promise<string>((resolve) => {
    const timer = setTimeout(() => {
      pendingJobs.delete(jobId);
      resolve("");  // Empty = timeout
    }, TIMEOUT_MS);
    pendingJobs.set(jobId, { resolve, timer });
  });

  // Push job into Claude session
  await mcp.notification({
    method: 'notifications/claude/channel',
    params: {
      content: context,
      meta: { job_id: jobId, skill },
    },
  });

  // Wait for reply...
  // (promise resolves when reply tool is called)

  res.json({ response });
});

// Reply tool — resolves the pending promise
mcp.tool('reply', async ({ job_id, text }) => {
  const pending = pendingJobs.get(job_id);
  if (pending) {
    clearTimeout(pending.timer);
    pending.resolve(text);
    pendingJobs.delete(job_id);
  }
  return { text: 'delivered' };
});
```

IMPORTANT: The notification must be pushed BEFORE the await, and the
promise must be created BEFORE the notification. The flow is:
1. Create promise + store in pendingJobs
2. Push notification (Claude receives the job)
3. HTTP handler awaits the promise
4. Claude processes and calls reply tool
5. Reply tool resolves the promise
6. HTTP handler returns the response

## Channel Instructions

```
Job requests arrive as <channel source="jobs-channel" job_id="..." skill="...">.
The content contains the full skill instructions and pre-fetched data.

Execute the skill instructions. Produce output for Discord.
When done, call the reply tool with the job_id and your output.
If there is nothing to report, reply with "NO_REPLY".

Do not post to Discord yourself. Do not save to Second Brain yourself.
Just produce the output and call reply. The scheduler handles the rest.
```

## What Stays The Same

- scheduler.py orchestration: cron triggers, data fetching, quiet hours,
  queue management, job locking
- Post-processing: NO_REPLY, garbage check, reasoning leak detection
- Discord posting: _post_to_channel with channel resolution, embeds, files
- Job history: record_job_start, record_job_complete
- Second Brain auto-save: SECOND_BRAIN_SAVE_SKILLS check
- WhatsApp forwarding: job.whatsapp flag handling

## Fallback Switch

```python
# scheduler.py
JOBS_USE_CHANNEL = os.environ.get("JOBS_USE_CHANNEL", "0") == "1"
```

In _execute_job_internal(), replace:
```python
response = await self._send_to_claude_code_v2(context, job=job)
```
With:
```python
if JOBS_USE_CHANNEL:
    response = await self._send_to_jobs_channel(context, job)
else:
    response, provider = await self._send_to_claude_code_v2(context, job=job)
```

## Build Order

1. Create jobs-channel/ MCP server (HTTP + channel + synchronous reply)
2. Add _send_to_jobs_channel() to scheduler.py with fallback switch
3. Create launch script for third tmux session
4. Test with a single skill (e.g., system-health)
5. Test NO_REPLY suppression
6. Test timeout handling
7. Enable for all jobs

## File Structure

```
jobs-channel/
├── src/
│   └── index.ts     # MCP server + HTTP + synchronous reply coordination
├── package.json
├── tsconfig.json
├── launch.sh
├── .env
└── .gitignore
```
