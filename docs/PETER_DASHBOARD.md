# Peter Dashboard -- Monitoring UI

## Overview

FastAPI web application running on port 5000 via NSSM service `PeterDashboard`. Provides real-time monitoring of all Peter services including process status, log viewing, job tracking, service control, and health alerting.

## Directory Structure

```
peter_dashboard/
  app.py                 # FastAPI application (main entry point)
  service_manager.py     # Process control (start/stop/restart via NSSM + PID tracking)
  job_history.db         # SQLite database for job execution history
  requirements.txt       # Python dependencies
  start.bat              # Startup batch script
  start-dashboard.bat    # Alternative startup script
  stop-dashboard.bat     # Stop script
  api/
    jobs.py              # Job execution tracking and SCHEDULE.md parsing
    logs.py              # Unified log aggregation across all sources
    subscriptions.py     # Personal/business subscription management
  templates/
    index.html           # Dashboard UI (Jinja2 template, v2 redesign)
  static/
    css/main.css         # Dashboard styles
    js/app.js            # Main dashboard JavaScript
    js/api-explorer.js   # Hadley API interactive explorer
    js/mind-map.js       # Knowledge graph visualisation
```

## Tech Stack

- **FastAPI** with Jinja2 templates and static file serving
- **WebSocket** for real-time status updates (5-second polling)
- **SQLite** (`job_history.db`) for job execution history
- **slowapi** for rate limiting
- **httpx** for async HTTP health checks
- **CORS** restricted to localhost (ports 5000 and 8100)

## Service Health Monitor

An independent background task runs on startup (via FastAPI lifespan) that continuously monitors all services:

| Service | Check Type | Critical |
|---------|-----------|----------|
| Hadley API | HTTP `/health` on :8100 | Yes |
| Discord Bot | Process status via service_manager | Yes |
| Second Brain | HTTP to Supabase REST API | Yes |
| Hadley Bricks | HTTP any response on :3000 | No |
| Peterbot Session | Router V2 (on-demand CLI) | Yes |
| Discord Channel | tmux session `peter-channel` | Yes |
| WhatsApp Channel | HTTP `/health` on :8102 | Yes |
| Jobs Channel | HTTP `/health` on :8103 | Yes |

**Alert rules:**
- Check interval: 60 seconds
- Alert threshold: down for 5 minutes (300s)
- Re-alert interval: 30 minutes
- Alerts post to Discord `#alerts` webhook (no bot token required)

## Service Manager

`service_manager.py` provides reliable process control with:

- **NSSM detection** (preferred for `HadleyAPI`, `DiscordBot`, `PeterDashboard`)
- **PID file tracking** for exact process identification (`.pids/` directory)
- **Port availability checks** before starting services
- **Orphan detection** -- finds processes using ports without tracked PIDs

Managed services: `hadley_api` (:8100), `discord_bot`, `hadley_bricks` (:3000), `peter_dashboard` (:5000).

## API Endpoints

### Core Status

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Dashboard HTML (v2 template or v1 fallback) |
| GET | `/health` | Dashboard health check |
| GET | `/api/status` | Full system status (parallel health checks) |
| GET | `/api/service-status` | Individual service statuses |
| GET | `/api/health-history` | Historical health check data |
| POST | `/api/health-history/clear/{service}` | Clear health history for a service |

### Service Control

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/restart/{service}` | Restart a specific service |
| POST | `/api/restart-all` | Restart all services |
| POST | `/api/stop/{service}` | Stop a specific service |

### Job Tracking (`api/jobs.py`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/jobs` | List scheduled jobs with execution history |
| GET | `/api/jobs/executions` | Recent executions (filterable by job_id, status, hours) |
| GET | `/api/jobs/{job_id}/history` | Execution history for a specific job |
| GET | `/api/jobs/{job_id}/logs` | Logs for a specific job |
| GET | `/api/job-stats` | Aggregate statistics (success rate, counts, recent failures) |
| POST | `/api/jobs/{job_id}/run` | Manual trigger (returns Discord command instructions) |

### Unified Logs (`api/logs.py`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/logs/unified` | Aggregated logs from all sources |
| GET | `/api/logs/histogram` | Log volume over time |
| GET | `/api/logs/facets` | Faceted filtering options |
| GET | `/api/logs/context` | Surrounding context for a log entry |
| GET | `/api/logs/sources` | Available log sources |
| GET | `/api/logs/tail` | Quick tail view for a source |
| GET | `/api/logs/errors` | Error aggregation across sources |
| GET | `/api/logs/stats` | Log statistics |

### Subscriptions (`api/subscriptions.py`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/subscriptions` | List all with filters + summary stats |
| GET | `/api/subscriptions/upcoming` | Next 30 days renewals |
| GET | `/api/subscriptions/health` | Health check (price changes, missed payments) |
| POST | `/api/subscriptions` | Create or update a subscription |
| PUT | `/api/subscriptions/{id}` | Update a subscription |
| DELETE | `/api/subscriptions/{id}` | Delete a subscription |
| GET | `/api/subscriptions/{id}/transactions` | Transaction history |

### Memory and Knowledge

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/memory/peter` | Peter's memory state |
| GET | `/api/memory/claude` | Claude memory context |
| GET | `/api/memory/recent` | Recent memory entries |
| GET | `/api/memory/graph` | Knowledge graph data |
| GET | `/api/search/memory` | Search memory |
| GET | `/api/search/second-brain` | Search Second Brain |
| GET | `/api/search/second-brain/list` | List Second Brain items |
| GET | `/api/search/second-brain/stats` | Second Brain statistics |

### Skills and Files

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/skills` | List all skills |
| GET | `/api/skill/{name}` | Get skill details |
| GET | `/api/skills/directory` | Skills directory listing |
| GET | `/api/skills/directory/{skill_id}` | Specific skill directory entry |
| GET | `/api/files` | List viewable files |
| GET | `/api/file/{file_type}/{file_name}` | Read a file |
| POST | `/api/file/append/{file_type}/{file_name}` | Append to a file |
| PUT | `/api/file/write/{file_type}/{file_name}` | Write/overwrite a file |

### Hadley API Explorer

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/hadley/openapi` | Hadley API OpenAPI spec |
| GET | `/api/hadley/endpoints` | Hadley API endpoint listing |

### Parser and Diagnostics

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/parser/debug` | Parser debug info |
| GET | `/api/parser/status` | Parser status |
| GET | `/api/parser/fixtures` | Parser test fixtures |
| GET | `/api/parser/captures` | Captured parser outputs |
| GET | `/api/parser/feedback` | Parser feedback log |
| GET | `/api/parser/cycles` | Parser improvement cycles |
| GET | `/api/parser/drift` | Parser drift detection |
| POST | `/api/parser/run-regression` | Run parser regression tests |
| POST | `/api/parser/mark-reviewed` | Mark captures as reviewed |
| POST | `/api/parser/feedback/{id}/resolve` | Resolve feedback item |

### Other

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/peter/state` | Peter's current state |
| GET | `/api/peter/quote` | Random Peter quote |
| GET | `/api/costs` | CLI cost tracking data |
| GET | `/api/claude-code-health` | Claude Code session health |
| GET | `/api/heartbeat/status` | Heartbeat monitoring status |
| POST | `/api/heartbeat/ran` | Record heartbeat execution |
| GET | `/api/logs/bot` | Bot log file content |
| GET | `/api/screen/{session}` | tmux session screen capture |
| POST | `/api/send/{session}` | Send input to tmux session |
| GET | `/api/context` | Current context messages |
| GET | `/api/captures` | Response captures |
| WS | `/ws` | Real-time status WebSocket (pushes every 5s) |

## Database

- **File**: `peter_dashboard/job_history.db` (SQLite)
- **Tables**:
  - `job_executions` -- start time, completion time, status, duration_ms, output (truncated to 500 chars), error message
  - `job_logs` -- timestamp, level (DEBUG/INFO/WARNING/ERROR), message
- **Indexes**: on `job_id` and `started_at DESC` for both tables
- **Cleanup**: `cleanup_old_records(days=30)` utility removes records older than 30 days

## Job Failure Alerting

`record_job_complete()` in `api/jobs.py` fires a background thread to post to Discord `#alerts` webhook on ANY job failure. The alert includes the job name, error message (truncated to 300 chars), and timestamp.

## SCHEDULE.md Integration

The jobs API parses `domains/peterbot/wsl_config/SCHEDULE.md` to discover all scheduled jobs. Each job entry includes:
- Name, skill, schedule expression, channel, enabled/disabled status
- WhatsApp flag (`+whatsapp`), quiet hours exemption (`!quiet`)
- Next run time calculation (supports daily, hourly, half-hourly, day-specific, monthly schedules)

## Access

- **URL**: `http://localhost:5000`
- **NSSM Service**: `PeterDashboard`
- **Dependencies**: `fastapi`, `uvicorn`, `httpx`, `websockets`, `slowapi`, `jinja2`, `pydantic`
