# Second Brain Health Diagnosis

## Overview

A health monitoring system for the Second Brain knowledge base that surfaces problems (stuck items, orphaned data, embedding failures, decay drift) through three channels: a CLI command, a daily Discord check, and a weekly Discord digest. The goal is to catch data quality issues early and give Chris confidence the system is working without manual inspection.

## Existing Building Blocks

| Module | What it provides |
|--------|-----------------|
| `domains/second_brain/admin.py` | CLI with `stats`, `search`, `seed`, `connections`, `view` subcommands |
| `domains/second_brain/embed.py` | In-memory `_EmbeddingStats` dataclass with `get_embedding_stats()` — tracks edge_ok/fail, hf_ok/fail, retries, cache hits. Never surfaced anywhere. |
| `domains/second_brain/db.py` | `get_pending_items()`, `get_fading_but_relevant_items()`, `get_most_accessed_item_since()`, `get_total_active_count()`, `get_total_connection_count()`, `get_items_since()` |
| `domains/second_brain/digest.py` | `generate_weekly_digest()` + `format_digest_for_discord()` — produces `DigestData` with new items, connections, fading items, stats |
| `domains/second_brain/config.py` | `SEARCH_MIN_DECAY = 0.2`, `DECAY_HALF_LIFE_DAYS = 90` |
| `domains/second_brain/types.py` | `ItemStatus` enum (`PENDING`, `ACTIVE`, `ARCHIVED`), `ConnectionType` enum, `DigestData` dataclass |
| `jobs/incremental_seed.py` | Pattern for registering APScheduler cron jobs and posting to `#alerts` (channel ID `1466019126194606286`) |
| `bot.py` | Scheduler setup in `on_ready`, registers jobs via `scheduler.add_job()` |

## Architecture

```
health.py (NEW)                 <-- shared health queries + report builder
    |
    +-- admin.py (EXTEND)       <-- `health` subcommand calls get_health_report()
    |
    +-- bot.py (EXTEND)         <-- two new APScheduler jobs:
            |                        daily_health_check  (7:00 AM UK)
            |                        weekly_health_digest (Sunday 9:00 AM UK)
            |
            +-- #alerts channel
```

A single `get_health_report()` function returns a `HealthReport` dataclass. The CLI prints it as text. The scheduled jobs format it for Discord. This avoids duplicating query logic.

---

## Done Criteria

### F1: `HealthReport` dataclass and `get_health_report()` function

Create `domains/second_brain/health.py` containing:

- `HealthReport` dataclass with all diagnostic fields (see Data Model below)
- `async get_health_report()` that runs all diagnostic queries and returns a populated `HealthReport`
- Health queries use Supabase REST API via the existing `_get_http_client()` / `_get_headers()` pattern from `db.py`

**Verification:** `get_health_report()` can be called standalone and returns a populated `HealthReport` with all fields. No query errors on the live database.

### F2: `admin.py health` CLI subcommand

Extend `admin.py` with a `health` subcommand that:
1. Calls `get_health_report()`
2. Prints a structured, colour-free text report to stdout
3. Report sections: Pending Items, Orphaned Items, Decay Distribution, Embedding Stats, Connection Coverage, Recent Capture Success Rate

**Verification:** `python -m domains.second_brain.admin health` prints a complete report with real data. No crashes on empty/missing data.

### F3: Daily Discord health check (scheduled job)

- Runs daily at 07:00 UK time (`Europe/London`)
- Calls `get_health_report()`
- Posts a compact message to `#alerts` (channel `1466019126194606286`)
- If all healthy: one-line summary
- If warnings: flags only the breached thresholds
- Uses the same `bot.get_channel()` / `bot.fetch_channel()` pattern as `incremental_seed.py`

**Verification:** Job registered in scheduler. Message posts to `#alerts`. Healthy state produces one-line message. Simulated threshold breach produces warning output.

### F4: Weekly Discord health digest (scheduled job)

- Runs Sunday at 09:00 UK time (`Europe/London`)
- Calls `get_health_report()` for health data
- Calls existing `generate_weekly_digest()` for content data (new items, connections, fading items)
- Combines both into a detailed weekly message posted to `#alerts`
- Replaces the need for a separate weekly digest trigger (the existing `digest.py` functions are reused, not replaced)

**Verification:** Job registered in scheduler. Message posts to `#alerts` with full breakdown sections. All data sections populated from live database.

### F5: Thresholds configurable via `config.py`

All warning thresholds defined as constants in `domains/second_brain/config.py`:

```python
# Health monitoring thresholds
HEALTH_PENDING_WARN: Final[int] = 0          # Warn if pending items > this
HEALTH_ORPHANED_WARN: Final[int] = 0         # Warn if orphaned items > this
HEALTH_DECAY_CRITICAL_PCT: Final[float] = 50 # Warn if >50% items below SEARCH_MIN_DECAY
HEALTH_EMBED_FAIL_RATE: Final[float] = 10    # Warn if >10% embedding failure rate (24h)
```

**Verification:** Changing a threshold constant changes the warning behaviour without code edits elsewhere.

---

## Data Model

```python
@dataclass
class HealthReport:
    """Complete health diagnostic for the Second Brain."""
    # Totals
    total_active: int
    total_connections: int

    # Pending items (embedding failures stuck in PENDING)
    pending_count: int
    pending_items: list[KnowledgeItem]  # up to 5, for display

    # Orphaned items (ACTIVE but zero chunks — unsearchable)
    orphaned_count: int
    orphaned_items: list[KnowledgeItem]  # up to 5, for display

    # Decay distribution
    decay_below_02: int      # items with decay_score < 0.2 (below search threshold)
    decay_02_to_05: int      # items with decay_score 0.2 - 0.5 (fading)
    decay_above_05: int      # items with decay_score > 0.5 (healthy)

    # Embedding pipeline stats (from in-memory counters)
    embedding_stats: dict    # output of get_embedding_stats()

    # Connection coverage
    items_with_zero_connections: int
    connection_type_breakdown: dict[str, int]  # {"semantic": 12, "topic_overlap": 8, ...}

    # Recent capture success rate (last 7 days)
    items_created_7d: int
    items_pending_7d: int    # created in last 7d and still PENDING

    # Timestamps
    generated_at: datetime
```

---

## Queries

### Q1: Pending items count

```
GET /rest/v1/knowledge_items?status=eq.pending&select=id,title,created_at&order=created_at.desc&limit=5
Headers: Prefer: count=exact
```

Count from `content-range` header, first 5 rows for display.

### Q2: Orphaned items (ACTIVE but zero chunks)

This requires identifying items that have no matching rows in `knowledge_chunks`. Two approaches:

**Option A — RPC function (preferred, single query):**

```sql
CREATE OR REPLACE FUNCTION get_orphaned_items(item_limit int DEFAULT 5)
RETURNS SETOF knowledge_items AS $$
  SELECT ki.*
  FROM knowledge_items ki
  LEFT JOIN knowledge_chunks kc ON kc.parent_id = ki.id
  WHERE ki.status = 'active'
    AND kc.id IS NULL
  ORDER BY ki.created_at DESC
  LIMIT item_limit;
$$ LANGUAGE sql STABLE;
```

**Option B — Two REST calls (fallback if RPC not deployed):**
1. Get all active item IDs
2. Get distinct parent_ids from chunks
3. Diff in Python

Use Option A. Deploy the RPC as a migration.

### Q3: Decay distribution

```sql
CREATE OR REPLACE FUNCTION get_decay_distribution()
RETURNS TABLE(bucket text, item_count bigint) AS $$
  SELECT
    CASE
      WHEN decay_score < 0.2 THEN 'below_02'
      WHEN decay_score < 0.5 THEN '02_to_05'
      ELSE 'above_05'
    END AS bucket,
    COUNT(*) AS item_count
  FROM knowledge_items
  WHERE status = 'active'
  GROUP BY bucket;
$$ LANGUAGE sql STABLE;
```

### Q4: Embedding pipeline stats

No query needed. Call `get_embedding_stats()` from `embed.py`. These are in-memory counters that reset on bot restart, so they reflect current-session health only. The daily check captures a snapshot. Note this limitation in the report.

### Q5: Connection coverage

```sql
CREATE OR REPLACE FUNCTION get_connection_coverage()
RETURNS TABLE(metric text, value bigint) AS $$
  -- Items with zero connections
  SELECT 'items_no_connections'::text, COUNT(*)::bigint
  FROM knowledge_items ki
  WHERE ki.status = 'active'
    AND NOT EXISTS (
      SELECT 1 FROM knowledge_connections kc
      WHERE kc.item_a_id = ki.id OR kc.item_b_id = ki.id
    )
  UNION ALL
  -- Breakdown by connection type
  SELECT connection_type, COUNT(*)
  FROM knowledge_connections
  GROUP BY connection_type;
$$ LANGUAGE sql STABLE;
```

### Q6: Recent capture success rate

Two REST calls with `Prefer: count=exact`:

```
# All items created in last 7 days (any status)
GET /rest/v1/knowledge_items?created_at=gte.{7_days_ago}&select=id&limit=1
Headers: Prefer: count=exact

# Items created in last 7 days that are still PENDING
GET /rest/v1/knowledge_items?created_at=gte.{7_days_ago}&status=eq.pending&select=id&limit=1
Headers: Prefer: count=exact
```

---

## Discord Message Formats

### Daily Health Check — All Healthy

```
:white_check_mark: Second Brain healthy — 247 items, 89 connections
```

One line. No noise.

### Daily Health Check — Warnings

```
:brain: Second Brain Health Check

:warning: 3 pending items (embedding failures)
:warning: 1 orphaned item (active but unsearchable)
:chart_with_downwards_trend: 54% of items below search threshold (decay < 0.2)

Totals: 247 items | 89 connections
```

Only sections with warnings appear. Healthy metrics are omitted.

### Weekly Health Digest

```
:brain: Weekly Second Brain Health Digest

**Overview**
247 active items | 89 connections | 12 new this week

**Decay Distribution**
:green_circle: Healthy (>0.5): 142 (57%)
:yellow_circle: Fading (0.2-0.5): 68 (28%)
:red_circle: Below threshold (<0.2): 37 (15%)

**Connections**
Coverage: 189/247 items connected (77%)
By type: semantic 52 | topic_overlap 31 | cross_domain 6

**Most Accessed This Week**
1. LEGO Investment Strategy Guide (8 accesses)
2. Japan Trip Planning Notes (5 accesses)
3. Marathon Training Plan (4 accesses)

**Faded Below Threshold**
- eBay Pricing Research (was 0.23, now 0.18)
- Brick Owl API Notes (was 0.21, now 0.16)

**Embedding Pipeline** (since last restart)
Edge function: 142 ok / 2 fail
HuggingFace: 3 ok / 0 fail
Retries: 5 | Cache hits: 89

**New This Week**
:inbox_tray: 12 items captured (10 active, 2 pending)
:link: 4 new connections discovered

---
Next digest: Sunday 9:00 AM
```

### Weekly Digest — Quiet Week

```
:brain: Weekly Second Brain Health Digest

**Overview**
247 active items | 89 connections | 0 new this week

**Decay Distribution**
:green_circle: Healthy (>0.5): 140 (57%)
:yellow_circle: Fading (0.2-0.5): 70 (28%)
:red_circle: Below threshold (<0.2): 37 (15%)

No new items or connections this week.
Use `/save` to capture knowledge!

---
Next digest: Sunday 9:00 AM
```

---

## Scheduler Registration

In `bot.py`, after the existing `reprocess_pending` job registration (~line 196):

```python
# Second Brain health check — daily at 7am UK
from domains.second_brain.health import get_health_report
# ... register daily_health_check job

# Second Brain weekly digest — Sunday 9am UK
# ... register weekly_health_digest job
```

Both jobs follow the pattern from `jobs/incremental_seed.py`:
- `scheduler.add_job()` with `'cron'` trigger
- `timezone="Europe/London"`
- `max_instances=1`, `coalesce=True`
- Pass `bot` as arg for channel posting
- Use `ALERTS_CHANNEL_ID = 1466019126194606286`

Daily job: `hour=7, minute=0`
Weekly job: `day_of_week='sun', hour=9, minute=0`

---

## Thresholds

| Threshold | Default | Meaning |
|-----------|---------|---------|
| `HEALTH_PENDING_WARN` | `0` | Any pending items trigger a warning |
| `HEALTH_ORPHANED_WARN` | `0` | Any orphaned items trigger a warning |
| `HEALTH_DECAY_CRITICAL_PCT` | `50` | Warn if >50% of items have decay < `SEARCH_MIN_DECAY` (0.2) |
| `HEALTH_EMBED_FAIL_RATE` | `10` | Warn if embedding failure rate >10% in current session |

The embedding failure rate is calculated from in-memory stats:
```python
total_attempts = stats["edge_ok"] + stats["edge_fail"] + stats["hf_single_ok"] + stats["hf_single_fail"]
fail_rate = (stats["edge_fail"] + stats["hf_single_fail"]) / max(total_attempts, 1) * 100
```

Note: edge failures that successfully fall back to HuggingFace are not counted as "failures" for the threshold — only items that ended up in PENDING status. The in-memory counters show retry/fallback health; the PENDING count shows actual data loss.

---

## Database Migrations Needed

One migration to add the three RPC functions:

```sql
-- Migration: add_health_rpc_functions

CREATE OR REPLACE FUNCTION get_orphaned_items(item_limit int DEFAULT 5)
RETURNS SETOF knowledge_items AS $$
  SELECT ki.*
  FROM knowledge_items ki
  LEFT JOIN knowledge_chunks kc ON kc.parent_id = ki.id
  WHERE ki.status = 'active'
    AND kc.id IS NULL
  ORDER BY ki.created_at DESC
  LIMIT item_limit;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION get_decay_distribution()
RETURNS TABLE(bucket text, item_count bigint) AS $$
  SELECT
    CASE
      WHEN decay_score < 0.2 THEN 'below_02'
      WHEN decay_score < 0.5 THEN '02_to_05'
      ELSE 'above_05'
    END AS bucket,
    COUNT(*) AS item_count
  FROM knowledge_items
  WHERE status = 'active'
  GROUP BY bucket;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION get_connection_coverage()
RETURNS TABLE(metric text, value bigint) AS $$
  SELECT 'items_no_connections'::text, COUNT(*)::bigint
  FROM knowledge_items ki
  WHERE ki.status = 'active'
    AND NOT EXISTS (
      SELECT 1 FROM knowledge_connections kc
      WHERE kc.item_a_id = ki.id OR kc.item_b_id = ki.id
    )
  UNION ALL
  SELECT connection_type, COUNT(*)
  FROM knowledge_connections
  GROUP BY connection_type;
$$ LANGUAGE sql STABLE;
```

---

## Files Changed

| File | Change |
|------|--------|
| `domains/second_brain/health.py` | **NEW** — `HealthReport` dataclass, `get_health_report()`, `format_daily_discord()`, `format_weekly_discord()` |
| `domains/second_brain/config.py` | Add 4 threshold constants |
| `domains/second_brain/admin.py` | Add `health` subcommand + `cmd_health()` |
| `domains/second_brain/__init__.py` | Export new health functions |
| `bot.py` | Register two APScheduler jobs |
| `migrations/NNN_add_health_rpc_functions.sql` | Three new RPC functions |

---

## Out of Scope

- Auto-remediation (e.g. auto-retrying pending items) — that already exists in `reprocess_pending` job
- Dashboard endpoint in `peter_dashboard` — can be added later using the same `get_health_report()`
- Historical health tracking / trend charts — just snapshots for now
- Alerting to channels other than `#alerts`

---

## Dependencies

- F1 must complete before F2, F3, F4 (they all call `get_health_report()`)
- F5 (config constants) should be done alongside or before F1
- Migration must be deployed before F1 can query orphaned items / decay distribution / connection coverage
- F3 and F4 are independent of each other

```
Migration --> F5 --> F1 --> F2
                       +--> F3
                       +--> F4
```
