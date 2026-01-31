# Phase 6: Discord Bot Integration

## Overview

Wire peterbot-mem into the Discord bot so that:
1. Memory context is injected before messages go to Claude Code
2. Message pairs are captured async for observation extraction

**Scope:** `#peterbot` channel only. `#claude-code` remains a dumb tunnel.

---

## Architecture Flow

```
Discord message (#peterbot)
       ↓
router.py:
  1. Add message to recent_buffer (deque, maxlen=20)
  2. GET /api/context/inject → tiered memory observations
  3. Build full_context = memory + recent_buffer + current_message
  4. tools.send_prompt(full_context) → Claude Code via tmux
       ↓
Claude Code processes (with injected context)
       ↓
Response captured (screen scrape or webhook)
       ↓
router.py:
  1. Add response to recent_buffer
  2. POST /api/sessions/messages (async, fire-and-forget)
  3. Return response to Discord
```

---

## Files to Create/Modify

```
domains/peterbot/
├── domain.py        # Existing - modify to use memory
├── memory.py        # NEW - memory client module
├── router.py        # Existing or NEW - routing with context injection
└── config.py        # Existing - add memory settings
```

---

## 1. config.py additions

```python
# Memory integration
WORKER_URL = "http://localhost:37777"
MESSAGES_ENDPOINT = f"{WORKER_URL}/api/sessions/messages"
CONTEXT_ENDPOINT = f"{WORKER_URL}/api/context/inject"
SESSION_ID = "peterbot"
RECENT_BUFFER_SIZE = 20
FAILURE_QUEUE_MAX = 100
RETRY_INTERVAL_SECONDS = 60
MAX_RETRIES = 3
```

---

## 2. memory.py (NEW)

```python
"""
Memory integration for peterbot channel.
Handles context retrieval and message capture.
"""

import asyncio
import aiohttp
from collections import deque
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass, field

from .config import (
    MESSAGES_ENDPOINT,
    CONTEXT_ENDPOINT,
    SESSION_ID,
    RECENT_BUFFER_SIZE,
    FAILURE_QUEUE_MAX,
    RETRY_INTERVAL_SECONDS,
    MAX_RETRIES,
)

@dataclass
class FailedMessage:
    user_message: str
    assistant_response: str
    timestamp: str
    retries: int = 0

# Module state
recent_buffer: deque = deque(maxlen=RECENT_BUFFER_SIZE)
failure_queue: List[FailedMessage] = []
_retry_task: Optional[asyncio.Task] = None


def add_to_buffer(role: str, content: str) -> None:
    """Add a message to the recent buffer."""
    recent_buffer.append({
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow().isoformat()
    })


def get_recent_context() -> str:
    """Format recent buffer as context string."""
    if not recent_buffer:
        return ""
    
    lines = ["## Recent conversation:"]
    for msg in recent_buffer:
        prefix = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{prefix}: {msg['content']}")
    
    return "\n".join(lines)


async def get_memory_context(query: str) -> str:
    """Fetch tiered memory observations from worker."""
    try:
        async with aiohttp.ClientSession() as session:
            params = {
                "project": SESSION_ID,  # endpoint uses 'project' not 'sessionId'
                "query": query,
            }
            async with session.get(CONTEXT_ENDPOINT, params=params, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("context", "")
                else:
                    print(f"Memory context fetch failed: {resp.status}")
                    return ""
    except asyncio.TimeoutError:
        print("Memory context fetch timed out")
        return ""
    except Exception as e:
        print(f"Memory context fetch error: {e}")
        return ""


def build_full_context(current_message: str, memory_context: str) -> str:
    """Combine memory + recent buffer + current message."""
    parts = []
    
    if memory_context:
        parts.append(memory_context)
    
    recent = get_recent_context()
    if recent:
        parts.append(recent)
    
    parts.append(f"## Current message:\nUser: {current_message}")
    
    return "\n\n".join(parts)


async def capture_message_pair(user_message: str, assistant_response: str) -> None:
    """Send message pair to worker for observation extraction (fire-and-forget)."""
    payload = {
        "contentSessionId": SESSION_ID,
        "source": "discord",
        "channel": "#peterbot",
        "timestamp": datetime.utcnow().isoformat(),
        "userMessage": user_message,
        "assistantResponse": assistant_response,
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(MESSAGES_ENDPOINT, json=payload, timeout=5) as resp:
                if resp.status == 202:
                    return  # Success
                else:
                    print(f"Message capture failed: {resp.status}")
                    _queue_failed_message(user_message, assistant_response)
    except Exception as e:
        print(f"Message capture error: {e}")
        _queue_failed_message(user_message, assistant_response)


def _queue_failed_message(user_message: str, assistant_response: str) -> None:
    """Add failed message to retry queue."""
    if len(failure_queue) >= FAILURE_QUEUE_MAX:
        failure_queue.pop(0)  # Drop oldest
    
    failure_queue.append(FailedMessage(
        user_message=user_message,
        assistant_response=assistant_response,
        timestamp=datetime.utcnow().isoformat(),
    ))


async def _retry_failed_messages() -> None:
    """Background task to retry failed message captures."""
    while True:
        await asyncio.sleep(RETRY_INTERVAL_SECONDS)
        
        if not failure_queue:
            continue
        
        to_retry = failure_queue.copy()
        failure_queue.clear()
        
        for msg in to_retry:
            if msg.retries >= MAX_RETRIES:
                print(f"Dropping message after {MAX_RETRIES} retries")
                continue
            
            msg.retries += 1
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "contentSessionId": SESSION_ID,
                        "source": "discord",
                        "channel": "#peterbot",
                        "timestamp": msg.timestamp,
                        "userMessage": msg.user_message,
                        "assistantResponse": msg.assistant_response,
                    }
                    async with session.post(MESSAGES_ENDPOINT, json=payload, timeout=5) as resp:
                        if resp.status != 202:
                            failure_queue.append(msg)
            except Exception:
                failure_queue.append(msg)


def start_retry_task() -> None:
    """Start the background retry task. Call once on bot startup."""
    global _retry_task
    if _retry_task is None:
        _retry_task = asyncio.create_task(_retry_failed_messages())
```

---

## 3. router.py integration

Modify the peterbot router to use memory:

```python
"""
Peterbot channel router with memory integration.
"""

import asyncio
from . import memory
from ..claude_code.tools import send_prompt, capture_screen

async def handle_message(message: str) -> str:
    """
    Process a peterbot channel message with memory context.
    
    1. Add to recent buffer
    2. Fetch memory context
    3. Build full context
    4. Send to Claude Code
    5. Capture response
    6. Store pair for observation extraction
    7. Return response
    """
    
    # 1. Add user message to buffer
    memory.add_to_buffer("user", message)
    
    # 2. Fetch memory context (tiered retrieval)
    memory_context = await memory.get_memory_context(query=message)
    
    # 3. Build full context
    full_context = memory.build_full_context(message, memory_context)
    
    # 4. Send to Claude Code via tmux
    send_prompt(full_context)
    
    # 5. Wait and capture response
    # NOTE: This needs refinement - how do we know when Claude is done?
    # Options:
    #   a) Webhook notification from Claude Code
    #   b) Poll screen until stable
    #   c) Fixed delay (not recommended)
    await asyncio.sleep(2)  # Placeholder - replace with proper detection
    response = capture_screen()
    
    # 6. Add response to buffer
    memory.add_to_buffer("assistant", response)
    
    # 7. Capture pair async (fire-and-forget)
    asyncio.create_task(memory.capture_message_pair(message, response))
    
    # 8. Return response
    return response
```

---

## 4. domain.py integration

Add startup hook for retry task:

```python
# In domain.py or bot.py startup

from domains.peterbot import memory

# During bot startup
memory.start_retry_task()
```

---

## 5. Context Endpoint

**Confirm with peterbot-mem:** Does `/api/context/inject` exist?

Expected request:
```
GET /api/context/inject?project=peterbot&query=user+message+text
```

Expected response:
```json
{
  "context": "## Memory observations:\n- Chris runs Hadley Bricks...\n- Chris prefers direct answers...",
  "observationCount": 15
}
```

**If this endpoint doesn't exist, it needs to be added to Phase 5 or created now.**

---

## 6. Response Capture Challenge

The current flow has a gap: **How do we know when Claude Code has finished responding?**

Options:

| Option | Pros | Cons |
|--------|------|------|
| **A. Notification webhook** | Accurate, event-driven | Requires Claude Code hook setup |
| **B. Poll screen until stable** | Works now | Latency, complexity |
| **C. Fixed delay** | Simple | Unreliable, slow |
| **D. Claude Code streams to Discord directly** | Clean | Bypasses bot layer |

**Recommendation:** Start with **B (poll until stable)** for MVP, then add **A (webhook)** for production.

Polling implementation:
```python
async def wait_for_response(timeout: int = 60, poll_interval: float = 0.5) -> str:
    """Poll screen until output stabilizes."""
    last_content = ""
    stable_count = 0
    elapsed = 0
    
    while elapsed < timeout:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
        
        current = capture_screen()
        if current == last_content:
            stable_count += 1
            if stable_count >= 3:  # Stable for 1.5 seconds
                return current
        else:
            stable_count = 0
            last_content = current
    
    return last_content  # Timeout, return what we have
```

---

## Testing Checklist

| Test | How to verify |
|------|---------------|
| Memory context injected | Send message, check Claude Code sees observations |
| Recent buffer works | Send 3 messages, verify context includes all 3 |
| Message capture async | Response returns before worker confirms |
| Failure queue retries | Kill worker, send message, restart worker, verify captured |
| #claude-code unaffected | Verify dumb tunnel still works without memory |

---

## Success Criteria

1. ✅ Send message to #peterbot, Claude Code receives memory context
2. ✅ Claude Code response reflects knowledge from previous conversations
3. ✅ Message pairs appear in peterbot-mem database
4. ✅ Zero added latency from memory capture (async)
5. ✅ #claude-code channel unchanged

---

## Implementation Order

1. **Verify `/api/context/inject` endpoint exists** — if not, create it
2. **Create `memory.py`** — core module
3. **Modify `router.py`** — add context injection
4. **Add retry task startup** — in bot.py
5. **Implement response capture** — polling or webhook
6. **Test end-to-end**

---

## Open Question

The `/api/context/inject` endpoint — does it exist in Phase 5 deliverables?

Looking at Phase 5 summary:
- ✅ POST /api/sessions/messages (for capture)
- ❓ GET /api/context/inject (for retrieval)

**If missing:** Either add to worker, or call tiered retrieval directly via a different endpoint. Check `SearchRoutes.ts` or `ContextBuilder.ts` for existing endpoints.
