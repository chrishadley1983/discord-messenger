# Self-Reflect Fix Plan

## Status: FIXED (2026-02-02)

The actual root cause was different from initially suspected.

## Problem Summary

Peter identified that peterbot conversations aren't being captured by the self-reflect memory system. Investigation reveals:

1. ~~**Queue is stuck** - 477 pending messages, 0 being processed~~ (Queue is processing fine)
2. ~~**Generators not running** - Active sessions have no active generators~~ (Generators are running)
3. **Recent observations missing** - Last peterbot observation: Feb 1 18:00, nothing since

## Actual Root Cause (FOUND)

The `capture_message_pair()` function in `domains/peterbot/memory.py` was **missing the `project` field** in its API payload:

```python
# BEFORE (missing project field)
payload = {
    "contentSessionId": session_id,
    "source": "discord",
    "channel": "peterbot",
    "userMessage": user_message,
    "assistantResponse": assistant_response,
    "metadata": {}
}

# AFTER (with project field)
payload = {
    "contentSessionId": session_id,
    "project": PROJECT_ID,  # Critical: identifies observations as peterbot project
    "source": "discord",
    "channel": "peterbot",
    ...
}
```

Without the project field, observations were being created but not associated with the "peterbot" project, so queries for `project=peterbot` returned nothing.

## Original (Incorrect) Root Cause Analysis

The `peterbot-mem` worker at `localhost:37777` is receiving messages but not processing them:

```
Queue Status:
- Total: 477 messages
- Pending: 477
- Processing: 0
- Failed: 0
- Active Generators: 0
```

The observation capture itself works (738 total observations exist, including peterbot ones from Feb 1). The issue is that **generator processes aren't starting** to process the queue.

Likely causes:
1. Worker may need restart after running for extended period
2. Generator crash without proper restart
3. Session initialization issue preventing generator start

## Fix Plan

### A. Immediate Fix (Unstick the Queue)

1. **Restart the peterbot-mem worker**
   ```bash
   # In WSL, find and restart the worker
   pkill -f "peterbot-mem.*worker"
   cd /home/chris_hadley/peterbot-mem
   bun run src/services/worker-service.ts &
   ```

2. **Verify processing resumes**
   ```bash
   curl -s http://localhost:37777/api/processing-status
   # Should show: isProcessing: true, queueDepth decreasing
   ```

3. **Monitor the queue drain**
   ```bash
   watch -n 5 'curl -s http://localhost:37777/api/processing-status'
   ```

### B. Investigate Root Cause

1. Check worker logs for generator errors:
   ```bash
   # Look for recent errors in worker output
   journalctl -u peterbot-mem --since "1 hour ago" | grep -i error
   ```

2. Check if Claude SDK agent can start:
   - Verify `claude` CLI is accessible from worker
   - Check for API key issues
   - Verify model availability

3. Add monitoring/alerting for queue depth:
   - Alert if queue depth > 100 for more than 10 minutes
   - Alert if processing status shows 0 processing for > 5 minutes

### C. Backfill Missing Conversations

Once the queue is processing again, historical conversations need backfilling:

1. **Identify missing conversations**
   - Discord messages from Feb 1 18:00 onwards
   - Filter to #peterbot channel only

2. **Backfill script approach**
   ```python
   # Use Discord API to fetch messages since last observation
   import requests

   CHANNEL_ID = 1415741789758816369
   LAST_OBS_TIME = "2026-02-01T18:00:00Z"

   # Fetch messages since then
   messages = fetch_discord_messages(CHANNEL_ID, after=LAST_OBS_TIME)

   # Pair user/assistant messages
   pairs = pair_messages(messages)

   # Send to memory endpoint
   for pair in pairs:
       send_to_memory(pair['user_id'], pair['user_msg'], pair['assistant_msg'])
   ```

3. **Backfill location**: `scripts/backfill_memory.py`

## Implementation Steps

### Phase 1: Immediate (Today)
- [ ] Restart worker to unstick queue
- [ ] Verify processing resumes
- [ ] Monitor until queue depth < 50

### Phase 2: Short-term (This Week)
- [ ] Add queue monitoring to peter_dashboard
- [ ] Add worker health check to scheduled jobs
- [ ] Create backfill script for missed conversations

### Phase 3: Long-term
- [ ] Investigate generator crash root cause
- [ ] Add auto-restart mechanism for stuck generators
- [ ] Add queue depth alerting to #alerts channel

## Files to Modify

| File | Change |
|------|--------|
| `scripts/backfill_memory.py` | NEW - Backfill script |
| `jobs/worker_health.py` | NEW - Health check job |
| `peter_dashboard/app.py` | Add queue status widget |

## Testing

1. After restart, send a test message to Peter
2. Wait 2-3 minutes
3. Check `/api/observations?project=peterbot&limit=1`
4. Verify new observation appears

## Notes

- The FK constraint issue Peter mentioned appears resolved (sessions are being created correctly)
- The issue is generator lifecycle, not database schema
- 477 pending messages will take time to process (estimate: 1-2 hours depending on provider rate limits)
