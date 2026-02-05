# Incident Analysis: 5 February 2026

## Summary

Peter appeared unresponsive this morning. Investigation revealed the bot was actually running and processing messages, but Claude Code responses were being extracted incorrectly, resulting in garbled output.

---

## Issue 1: Peter Not Responding Properly

### Symptoms
- Messages to Peter appeared to get no meaningful response
- Responses looked like shell prompts/paths instead of actual answers

### Root Cause
The response parser was extracting garbage from the Claude Code tmux session. Example from logs:

```
07:46:43 | Extracted response (135 chars): || echo "No g…)
/home/chris_hadley/.claude/projects/-home-chris-hadley-peterbot...
```

This pattern repeated at 07:47:57, 07:48:01, 07:48:16, 08:12:40, and 08:16:38.

### What Was Actually Happening
- Bot connected to Discord ✓
- Scheduler running ✓
- Messages being processed ✓
- **BUT**: Parser extracting shell prompts/tool output instead of Claude's actual responses

### Likely Cause
The Claude Code tmux session was in a bad state - possibly stuck mid-operation or showing tool output instead of the response area.

---

## Issue 2: Traffic Report (School Run) Didn't Send at 07:45

### Symptoms
- Thursday school-run scheduled for 07:45 did not produce a traffic report

### Timeline from Logs
```
07:45:00 | Executing scheduled job: School Run (Thu) (school-run)
07:45:01 | Current sessions: ['claude-discord', 'claude-peterbot'], looking for: claude-peterbot
07:45:12 | /clear verification timeout after 8.0s
07:45:25 | Empty response detected for scheduled job, attempting retry...
07:45:40 | /clear verification timeout after 10.0s
07:45:40 | Clear failed on retry attempt
07:45:53 | Retry also returned empty response
07:45:53 | No response from Claude Code for School Run (Thu)
07:45:54 | Error writing context file: [WinError 206] The filename or extension is too long
```

### Root Causes (Multiple)

1. **`/clear` command timing out** - The clear verification timed out at 8s, then again at 10s on retry
2. **Empty responses from Claude Code** - Both initial attempt and retry returned empty
3. **WinError 206** - Context file path too long, failed to write context

### Contributing Factors
- Morning briefing job at 07:44:46 was still processing (detected conversational skill)
- Multiple jobs competing for the single Claude Code session
- Clear command not completing before job execution

---

## Issue 3: Health Monitor Didn't Alert

### Symptoms
- No alert was sent despite Peter being effectively broken

### Root Cause
The worker health monitor only checks the **memory worker**, not Claude Code responsiveness:

```
08:06:43 | Worker health: queue=51, processing=True, local_pending=0, circuit=closed
```

From `jobs/worker_health.py`, the health check only monitors:
- Memory worker queue depth
- Whether worker is processing
- Local pending capture count
- Circuit breaker state

### What's NOT Monitored
- Whether Claude Code responds to messages
- Whether scheduled jobs succeed or fail
- Whether response parsing is working correctly
- `/clear` command success rate

---

## Timeline of Events

| Time | Event |
|------|-------|
| 06:57:19 | Bot started, loaded 24 scheduled jobs |
| 07:00:00 | Morning Briefing executed (with issues) |
| 07:01:00 | Heartbeat - clear timeout, empty response |
| 07:02:00 | News - clear timeout |
| 07:03:00 | Balance Monitor - empty responses |
| 07:06:17 | "No response from Claude Code for Balance Monitor" |
| 07:21:39 | Bot restarted (by user?) |
| 07:30:52 | User message processed |
| 07:31:00 | Heartbeat - clear timeout, empty response |
| 07:33:26 | Response extracted but heavily sanitized (1339→9 chars) |
| 07:44:46 | Morning briefing skill triggered by user message |
| **07:45:00** | **School Run job executed - FAILED** |
| 07:45:53 | "No response from Claude Code for School Run (Thu)" |
| 07:46:43 | Garbage response extracted (shell paths) |
| 07:55:00 | Health Digest ran (data fetched OK) |
| 08:01:00 | Heartbeat - clear timeout |
| 08:06:43 | Worker health check: "queue=51, processing=True" - reported healthy |
| 08:12:40 | User message got garbage response |
| 08:12:54 | Bot restarted again |

---

## Recommended Fixes

### Priority 1: Add Claude Code Health Monitoring
- Track scheduled job success/failure rate
- Alert when 2+ consecutive jobs fail
- Monitor response extraction quality (detect garbage patterns)

### Priority 2: Fix `/clear` Timeout Issues
- Investigate why clear consistently times out (8-10s)
- Consider longer timeout or different verification method
- Add metric tracking for clear success rate

### Priority 3: Fix WinError 206 (Path Too Long)
- Context file path exceeds Windows MAX_PATH (260 chars)
- Truncate or hash the path to fit within limits

### Priority 4: Add Response Parser Validation
- Detect when extracted content looks like shell prompts
- Pattern: paths starting with `/home/`, shell operators like `||`, `echo`
- Auto-retry or alert when garbage detected

### Priority 5: Job Scheduling Improvements
- Prevent job overlap when previous job still running
- Add job execution timeout
- Queue jobs if Claude Code session is busy

---

## Files Involved

| File | Role |
|------|------|
| `jobs/worker_health.py` | Health monitor (only checks memory worker) |
| `domains/peterbot/scheduler.py` | Scheduled job execution |
| `domains/peterbot/router.py` | Message routing, `/clear` handling |
| `domains/peterbot/capture_parser.py` | Response extraction from tmux |
