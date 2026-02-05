# Remote Worker Reliability Plan

## Objective
Make peterbot memory capture reliable during worker outages while maintaining honest operation when context is unavailable.

## Revised Architecture

```
Discord Message
      ↓
router.py
      ↓
memory_client.py (consolidated)
      │
      ├── get_context()
      │       ↓
      │   Circuit Breaker
      │       ├── CLOSED → Worker → cache response locally
      │       └── OPEN → Return cached context + degraded mode flag
      │
      └── capture_pair()
              ↓
      Local SQLite: pending_captures.db
              ↓
      Background Processor (every 30s)
      - One capture at a time
      - 2-3s delay between sends
      - Respects circuit breaker
              ↓
      Worker (when available)
```

## Implementation Phases

### Phase 1: Consolidate & Persist (Foundation) ✅ COMPLETE
**Goal**: Single memory client, durable capture queue

- [x] Create `pending_captures.db` schema
- [x] Create `domains/peterbot/capture_store.py` - SQLite persistence layer
- [x] Refactor `memory.py`:
  - Write to local DB first (always succeeds)
  - Attempt immediate send (fire-and-forget)
  - Return success to caller immediately
- [x] Remove `domain.py:send_to_memory()` - use `memory.py` everywhere
- [x] Update `worker_health.py` to use `config.py` WORKER_URL (not hardcoded)
- [x] End-to-end tests passing (tests/test_phase1_e2e.py)

**Schema**:
```sql
CREATE TABLE pending_captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_message TEXT NOT NULL,
    assistant_response TEXT NOT NULL,
    channel TEXT DEFAULT 'peterbot',
    created_at INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending, sending, sent, failed
    retries INTEGER DEFAULT 0,
    last_error TEXT,
    sent_at INTEGER
);

CREATE INDEX idx_status ON pending_captures(status);
CREATE INDEX idx_created ON pending_captures(created_at);
```

### Phase 2: Circuit Breaker (Stability) ✅ COMPLETE
**Goal**: Stop hammering dead worker, graceful degradation

- [x] Create `domains/peterbot/circuit_breaker.py`
- [x] Wrap worker calls (both capture and context) with circuit breaker
- [x] States:
  - CLOSED: Normal operation
  - OPEN: Worker down, use fallbacks (5 consecutive failures → OPEN)
  - HALF_OPEN: Testing recovery after 30s (1 success → CLOSED, 1 failure → OPEN)
- [x] Add circuit state to health check output
- [x] Add circuit state to alerts (worker error, local queue building)
- [x] Comprehensive tests (test_circuit_breaker.py, test_worker_health.py, test_phase2_integration.py)

**Config additions** (`config.py`):
```python
# Circuit breaker
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RECOVERY_TIMEOUT = 30  # seconds
```

### Phase 3: Context Cache & Degraded Mode (Continuity) ✅ COMPLETE
**Goal**: Peter remains useful during outages, honest about limitations

- [x] Add context cache table:
```sql
CREATE TABLE context_cache (
    query_hash TEXT PRIMARY KEY,
    context TEXT NOT NULL,
    fetched_at INTEGER NOT NULL
);
```
- [x] Cache context responses (last 50 queries, expire after 1 hour)
- [x] When circuit OPEN:
  - Try cache first (stale OK)
  - If no cache hit, inject degraded mode notice
- [x] Degraded mode notice for Peter
- [x] get_memory_context returns tuple (context, is_degraded)
- [x] Cache stats exported via memory.get_cache_stats()
- [x] Comprehensive tests (test_context_cache.py - 12 tests)

**Config additions** (`config.py`):
```python
# Context cache
CONTEXT_CACHE_MAX_ENTRIES = 50
CONTEXT_CACHE_TTL_SECONDS = 3600  # 1 hour
DEGRADED_MODE_NOTICE = "..."
```

### Phase 4: Background Processor (Reliability) ✅ COMPLETE
**Goal**: Drain pending queue when worker available

- [x] Create `jobs/capture_processor.py`
- [x] Register with APScheduler (every 30 seconds)
- [x] Logic:
  1. Check circuit state - if OPEN, skip
  2. Get oldest pending capture
  3. Attempt send (with 5s timeout)
  4. On success: mark sent, update sent_at
  5. On failure: increment retries, log error
  6. If retries >= 5: mark as failed (stop trying)
  7. Wait 2 seconds before next item
  8. Process max 10 per cycle (prevent runaway)
- [x] Add cleanup job (daily at 3:00 AM):
  - Delete sent captures older than 7 days
  - Delete failed captures older than 30 days
  - Clean up expired context cache entries
- [x] Comprehensive tests (test_capture_processor.py - 10 tests)

**Config additions** (`config.py`):
```python
# Background capture processor
CAPTURE_PROCESSOR_INTERVAL = 30
CAPTURE_PROCESSOR_MAX_PER_CYCLE = 10
CAPTURE_PROCESSOR_DELAY_BETWEEN = 2
```

### Phase 5: Enhanced Monitoring (Visibility)
**Goal**: Know what's happening

- [ ] Increase health check frequency: 15min → 2min
- [ ] Add metrics to health check:
  - `queue_depth`: pending captures count
  - `circuit_state`: CLOSED/OPEN/HALF_OPEN
  - `success_rate_1h`: captures sent successfully in last hour
  - `oldest_pending_age`: seconds since oldest pending capture
- [ ] Alert thresholds:
  - queue_depth > 50 → WARNING
  - queue_depth > 200 → CRITICAL
  - oldest_pending_age > 3600 (1hr) → WARNING
  - circuit_state == OPEN for > 30min → CRITICAL

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `domains/peterbot/capture_store.py` | CREATE | SQLite persistence for captures + context cache |
| `domains/peterbot/circuit_breaker.py` | CREATE | Circuit breaker implementation |
| `domains/peterbot/memory.py` | REFACTOR | Use capture_store, add circuit breaker, context cache |
| `domains/peterbot/config.py` | MODIFY | Add circuit breaker config, DB paths |
| `domains/peterbot/domain.py` | MODIFY | Remove send_to_memory(), delegate to memory.py |
| `jobs/capture_processor.py` | CREATE | Background queue processor |
| `jobs/worker_health.py` | REFACTOR | Use config URL, add metrics, 2min interval |
| `jobs/__init__.py` | MODIFY | Register capture_processor job |

## Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| Message loss during 1hr outage | ~100% | <1% |
| Time to detect worker failure | 15 min | 2 min |
| Context during outage | None (amnesiac) | Cached/degraded mode |
| Code duplication | 2 implementations | 1 implementation |
| Capture queue visibility | None | Real-time metrics |

## Out of Scope (Deferred)

- **Automatic gap detection**: Compare Discord history vs captures to find missed messages. Revisit only if persistent queue proves insufficient.
- **Worker auto-restart**: Handled by systemd/supervisor, not the bot.
- **Multi-worker support**: Single worker is sufficient for current scale.

## Error Log

(Track errors encountered during implementation)

---
Created: 2026-02-02
