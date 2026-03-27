# Discord-Messenger Project Instructions

## Architecture Reference

**READ FIRST**: See `docs/ARCHITECTURE.md` for comprehensive system architecture including:
- Windows vs WSL component mapping
- Skill execution flow diagrams
- Symlink strategy for wsl_config
- Job registration (skills vs legacy)
- Common pitfalls and debugging

### Critical: Local vs WSL

| Runs On | Components |
|---------|------------|
| **Windows (NSSM)** | Discord bot (`bot.py`), Hadley API, Dashboard |
| **WSL2 (tmux)** | 3 channel sessions: `peter-channel`, `whatsapp-channel`, `jobs-channel` |
| **Symlinked** | `wsl_config/` → `/home/chris_hadley/peterbot/` (changes sync automatically) |

### Channel Architecture (Primary — Mar 2026)

Three persistent Claude Code sessions handle all messaging via Anthropic's channels:
- `peter-channel/` — Discord conversations (discord.js gateway)
- `whatsapp-channel/` — WhatsApp conversations (HTTP :8102, via Evolution API)
- `jobs-channel/` — Scheduled jobs (HTTP :8103, synchronous reply pattern)

Fallback: `PETERBOT_USE_CHANNEL=0` / `WHATSAPP_USE_CHANNEL=0` / `JOBS_USE_CHANNEL=0` in `.env` reverts to router_v2 (`claude -p` per message). Smart fallback auto-detects dead channel sessions.

**Key Rule**: Skill files in `wsl_config/skills/` are symlinked to WSL. Changes are immediate - no sync needed.

## Plan Alignment

After every significant file write or edit, re-read the governing spec or task plan
before continuing to the next step. This prevents goal drift in long sessions.

- If a task_plan.md exists in the project root, re-read it after every 3+ file changes
- If working from a spec (@SECOND-BRAIN.md, @RESPONSE.md), re-read the current
  implementation phase section before starting the next phase
- After encountering an error, log it in task_plan.md before attempting a fix
- Never attempt the same failed approach twice - mutate the strategy

## Plan Requirements

When creating implementation plans, ALWAYS include a dedicated section for documentation updates:

### Documentation Locations

| File | Purpose |
|------|---------|
| `hadley_api/README.md` | API endpoint documentation - add new endpoints here |
| `domains/peterbot/wsl_config/CLAUDE.md` | Peter's instructions - reference APIs, don't duplicate |
| `domains/peterbot/wsl_config/PETERBOT_SOUL.md` | Personality and tone |
| `docs/playbooks/*.md` | Process and format guides for specific tasks |
| `domains/peterbot/wsl_config/skills/*/SKILL.md` | Behavior rules for specific capabilities |

### Plan Section Requirements

Every plan must explicitly list:
1. **API Documentation** - New endpoints to add to `hadley_api/README.md`
2. **Peter's Knowledge Updates** - What to add to CLAUDE.md (keep minimal, reference other docs)
3. **Skill/Playbook Changes** - New or modified skills and playbooks

This ensures Peter's knowledge base stays in sync with new features.

## Project Structure

- `bot.py` - Main Discord bot entry point, scheduler, auto-start for channel sessions
- `peter-channel/` - Discord channel MCP server (discord.js gateway + reply tool)
- `whatsapp-channel/` - WhatsApp channel MCP server (HTTP :8102 + reply/voice_reply tools)
- `jobs-channel/` - Scheduled jobs channel MCP server (HTTP :8103 + synchronous reply)
- `domains/peterbot/` - Peterbot domain (routing, scheduling, response pipeline)
  - `router_v2.py` - Stateless CLI routing (fallback when channels are down)
  - `scheduler.py` - APScheduler integration, routes jobs to channel or CLI
  - `memory.py` - Memory context injection, buffer management
  - `config.py` - Configuration constants
  - `response/` - Response pipeline (sanitise → classify → format → chunk)
  - `wsl_config/` - WSL-side config synced to ~/peterbot
    - `CLAUDE.md` - Peter's personality, instructions, and governance rules
    - `SCHEDULE.md` - Scheduled jobs definition
    - `skills/` - Skill definitions for scheduled jobs
- `domains/second_brain/` - Second Brain knowledge base (Supabase + pgvector)
  - `seed/adapters/` - Import adapters (email, calendar, GitHub, Garmin, recipes, finance)
- `peter_dashboard/` - Dashboard Web UI (port 5000)
- `hadley_api/` - REST API for external services (port 8100)
  - `peter_routes/` - Auto-discovered endpoints created by Peter
- `mcp_servers/` - MCP servers for Claude Desktop & Claude Code
  - `second_brain_mcp.py` - Knowledge base search & save (6 tools)
  - `financial_data_mcp.py` - Personal finance + Hadley Bricks business data (11 tools)
  - `financial_data/` - Financial data query modules
    - `config.py` - Env vars, date helpers
    - `supabase_client.py` - httpx async client (finance + public schema)
    - `personal_finance.py` - Net worth, budget, spending, savings, FIRE, transactions
    - `business_finance.py` - Platform revenue, P&L (eBay, Amazon, BrickLink, Brick Owl)
    - `formatters.py` - Currency/table formatting

## Key Patterns

- Use `asyncio.to_thread()` for blocking sync operations in async context
- Channel isolation via `_session_lock` and `/clear` on channel switch
- Response parsing uses screen diff extraction (before/after)
- Interim updates only when spinner is actually visible (SPINNER_CHARS at line start)

## Task Management

### Peterbot Development Tasks
When implementing Peterbot features:
1. Create tasks for each skill component (combined impl+verify)
2. Set dependencies: API → Skill → Schedule → Test
3. Use `CLAUDE_CODE_TASK_LIST_ID=pb-<feature>`

### Integration with Scheduler

**IMPORTANT**: Use skill-based jobs only. Do NOT use legacy `jobs/*.py` functions.

| Approach | Where | Use Case |
|----------|-------|----------|
| **Skill-based** (preferred) | `SCHEDULE.md` + `data_fetchers.py` + `skills/*/SKILL.md` | All scheduled output |
| **Infrastructure** | `bot.py` register_* | Capture cleanup, seeding (no Discord output) |
| **Legacy** (DO NOT USE) | `jobs/*.py` register_* | DEPRECATED - causes conflicts |

Scheduled job development (combined impl+verify):
- `F1: Add data fetcher` (no blockers, verify: fetcher returns data)
- `F2: Create skill SKILL.md` (blocked by F1, verify: skill executes)
- `F3: Add to SCHEDULE.md` (blocked by F2, verify: job registered)
- `F4: Test scheduled execution` (blocked by F3, verify: runs on schedule)

### Multi-System Changes
For changes spanning bot + API + dashboard:
```powershell
$env:CLAUDE_CODE_TASK_LIST_ID = "pb-cross-system"
```
All three can be worked on in parallel with proper blocking.

### Task-First Development
Before writing code, break the work into tasks:
1. Read the governing spec (done-criteria.md, feature-spec.md)
2. Create tasks for each implementation step (F1, F2, etc.)
3. Set dependencies with `addBlockedBy`
4. Execute tasks in order, verifying each before marking complete
