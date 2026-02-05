# Phase 7: Peterbot Scheduler System - Implementation Summary

**Date:** 31 January 2026
**Status:** Complete (pending bot restart for filter changes)

---

## Core Deliverables

### 1. Peterbot Scheduler (`domains/peterbot/scheduler.py`)

Parses `SCHEDULE.md` markdown tables and registers jobs with APScheduler.

**Features:**
- Cron expression parsing (e.g., `08:00 UK`, `15:00 Sat,Sun UK`)
- Interval parsing (e.g., `30m`, `1h`)
- Channel routing via `PETERBOT_CHANNELS` mapping
- Quiet hours (23:00-06:00 UK) with `!quiet` exemption flag
- Auto-generates `manifest.json` on reload
- `!reload-schedule` command to hot-reload without bot restart

**Key Data Structures:**
```python
@dataclass
class JobConfig:
    name: str
    skill: str
    schedule: str
    channel: str
    needs_data: bool
    exempt_quiet_hours: bool = False
```

### 2. Data Fetchers (`domains/peterbot/data_fetchers.py`)

Pre-fetch functions that call APIs before skill execution, injecting data into context.

**Implemented Fetchers:**
| Fetcher | API/Source | Data Returned |
|---------|------------|---------------|
| `get_health_digest_data()` | Garmin + Withings | Sleep, weight, steps, HR, yesterday comparison |
| `get_hydration_data()` | Garmin | Water intake, steps, goals |
| `get_weekly_health_data()` | Supabase | 7-day averages, trends, grades |
| `get_monthly_health_data()` | Supabase | 30-day summary, long-term trends |
| `get_youtube_digest_data()` | YouTube + Grok | Videos by category, descriptions |
| `get_football_scores_data()` | Football-Data.org | Today's PL matches by status |
| `get_balance_data()` | Claude/Moonshot APIs | Credit balances |

**Registration:**
```python
SKILL_DATA_FETCHERS = {
    "health-digest": get_health_digest_data,
    "hydration": get_hydration_data,
    # ... etc
}
```

### 3. Skill Execution Flow

```
SCHEDULE.md triggers job
        ↓
scheduler.py: _execute_job()
        ↓
Check quiet hours (skip if not exempt)
        ↓
Load SKILL.md from skills/{name}/
        ↓
Call data fetcher (if needs_data=true)
        ↓
Write context.md with skill + data
        ↓
Send to Claude Code via tmux
        ↓
Extract response, post to Discord channel
```

### 4. Skills Directory Structure

```
skills/
├── _template/SKILL.md
├── api-usage/SKILL.md
├── balance-monitor/SKILL.md
├── football-scores/SKILL.md      # NEW
├── health-digest/SKILL.md
├── heartbeat/SKILL.md
├── hydration/SKILL.md
├── monthly-health/SKILL.md
├── morning-briefing/SKILL.md
├── news/SKILL.md
├── nutrition-summary/SKILL.md
├── school-pickup/SKILL.md
├── school-run/SKILL.md
├── self-reflect/SKILL.md         # NEW
├── weekly-health/SKILL.md
├── whatsapp-keepalive/SKILL.md
├── youtube-digest/SKILL.md
└── manifest.json                 # Auto-generated
```

---

## Scope Creeps

### A. Output Filtering (`router.py`)

**Problem:** Claude Code UI elements leaking into Discord output.

**Filters Added:**
| Pattern | Example |
|---------|---------|
| Version lines | `Claude Code v2.1.27` |
| Model lines | `▘ Opus 4.5 · Claude Max` |
| Path lines | `▘▘ ~/peterbot` |
| Status lines | `✽ Creating… (1m 14s · ↓ 198 tokens · thinking)` |
| Thinking indicators | `Contemplating`, `Cerebrating`, `Levitating` |
| Token counts | `2.5k tokens`, `cost: $0.03` |
| Hook output | `Ran 2 hooks`, `1 stop hook` |
| Keyboard hints | `ctrl+o`, `? for shortcuts` |
| Feedback prompt | `How is Claude doing this session?` |
| Rating options | `1: Bad 2: Fine 3: Good 0: Dismiss` |
| Edit diffs | `Update(/path/file)`, `+from .module import` |
| Line numbers with code | `12 from .foo import bar` |

### B. Quiet Hours Exemption

**Problem:** Heartbeat and self-reflect need to run during quiet hours (23:00-06:00).

**Solution:** Added `!quiet` suffix in SCHEDULE.md channel column.

```markdown
| Heartbeat | heartbeat | 30m | #peterbot!quiet | yes |
| Self-Reflect | self-reflect | 12:00,18:00,23:00 UK | #alerts!quiet | yes |
```

**Implementation:**
```python
if "!quiet" in channel.lower():
    exempt_quiet_hours = True
    channel = channel.replace("!quiet", "").strip()
```

### C. Self-Reflect Skill (NEW)

**Purpose:** 3x daily self-improvement review - Peter adds items to HEARTBEAT.md.

**Schedule:** 12:00, 18:00, 23:00 UK (exempt from quiet hours)

**Categories:**
- `[SKILL]` - Skill improvements
- `[INTEGRATION]` - New API/data source ideas
- `[IDEAS]` - Feature suggestions
- `[FIX]` - Bug fixes noticed
- `[MEMORY]` - Memory system improvements

**Output Channel:** #alerts (1466019126194606286)

### D. Football Scores Skill (NEW)

**API:** Football-Data.org (free tier, 10 req/min)

**Config Added:**
```python
# .env
FOOTBALL_DATA_API_KEY=e53ffd0116ac4d838d2de3719485638d

# config.py
FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
```

**Data Fetcher:** `get_football_scores_data()` - fetches today's PL matches, groups by status (LIVE → FINISHED → SCHEDULED)

**Conversational:** Yes (uses web search when no pre-fetched data)

### E. Peter Identity (`PETERBOT_SOUL.md`)

**Added Identity Section:**
- Name: Peter
- Birthday: 29th January 2026
- Creator: Chris (with Claude's help)
- Home: The Snug PC in Tonbridge
- Purpose: Hadley family assistant

**Key Phrases:**
- "Claude's my brain, but I'm Peter"
- "Born 29th January 2026 - just a few days old!"

**Never Say:**
- "I'm Claude, made by Anthropic"
- References to model versions or neural networks

### F. BUILDING.md (Governance Document)

**Purpose:** Prevent Peter from creating incorrect architecture (like jobs/*.py files).

**Key Rules:**
1. Data fetchers go in `data_fetchers.py`, NOT `jobs/*.py`
2. All output flows through Claude Code, no direct Discord posting
3. Schedules defined in `SCHEDULE.md`, not APScheduler direct calls
4. New integrations/schedules need Chris approval via HEARTBEAT.md

**Triggered By:** Peter incorrectly created `jobs/football_scores.py` with direct APScheduler registration and Discord posting.

### G. Memory Training Inserts

Added to peterbot-mem for context injection:
1. Skill usage patterns (read SKILL.md, don't use Skill tool)
2. Skill file locations (`skills/` not `.claude/skills/`)
3. BUILDING.md patterns
4. Peter identity

### H. WSL Symlinks

Created symlinks from WSL to Windows for file access:
```
/home/chris_hadley/peterbot/
├── BUILDING.md → /mnt/c/.../wsl_config/BUILDING.md
├── HEARTBEAT.md → /mnt/c/.../wsl_config/HEARTBEAT.md
├── skills/ → /mnt/c/.../wsl_config/skills/
└── .claude/settings.local.json  # Wide permissions for peterbot
```

### I. Garmin Data Backfill

**Problem:** Weekly/monthly health skills lacked accurate data.

**Root Cause:** `garmin_daily_summary` table missing columns: `sleep_hours`, `sleep_score`, `resting_hr`

**Fix:**
1. ALTER TABLE to add columns
2. Created `scripts/backfill_health_data.py` to populate from Garmin API

---

## Files Modified

### New Files Created
| File | Purpose |
|------|---------|
| `domains/peterbot/wsl_config/BUILDING.md` | Architecture governance |
| `domains/peterbot/wsl_config/skills/football-scores/SKILL.md` | Football skill |
| `domains/peterbot/wsl_config/skills/self-reflect/SKILL.md` | Self-improvement skill |
| `scripts/backfill_health_data.py` | Garmin data backfill |

### Files Modified
| File | Changes |
|------|---------|
| `domains/peterbot/scheduler.py` | Added `exempt_quiet_hours`, `!quiet` parsing |
| `domains/peterbot/router.py` | Added 15+ output filters |
| `domains/peterbot/data_fetchers.py` | Added football scores fetcher, fixed youtube-digest |
| `domains/peterbot/config.py` | Added #alerts channel |
| `domains/peterbot/wsl_config/CLAUDE.md` | Added Live Data Queries, BUILDING.md reference |
| `domains/peterbot/wsl_config/PETERBOT_SOUL.md` | Added Identity section, output cleanliness, research quality |
| `domains/peterbot/wsl_config/SCHEDULE.md` | Added self-reflect, !quiet flags |
| `config.py` | Added FOOTBALL_DATA_API_KEY |
| `.env` | Added FOOTBALL_DATA_API_KEY |
| `bot.py` | Removed legacy commands (!youtube, !weeklyhealth, !monthlyhealth) |

### Files Deleted (Peter's Incorrect Work)
| File | Reason |
|------|--------|
| `jobs/football_scores.py` | Wrong pattern - used direct APScheduler + Discord posting |

### Files Reverted
| File | Change |
|------|--------|
| `jobs/__init__.py` | Removed football_scores import Peter added |

---

## Testing Completed

| Skill | Test Method | Result |
|-------|-------------|--------|
| youtube-digest | `!skill youtube-digest` | Working |
| weekly-health | `!skill weekly-health` | Working (after data backfill) |
| monthly-health | `!skill monthly-health` | Working |
| news | `!skill news` | Working (improved URL formatting) |
| heartbeat | `!skill heartbeat` | Working (with Edit permissions) |
| football-scores | Manifest verified | Data fetcher ready |
| self-reflect | Added to schedule | Awaiting first run |

---

## Pending (Needs Bot Restart)

1. **Output filters** - All router.py changes need Python reload
2. **Football scores** - Skill ready, needs conversational testing
3. **Self-reflect** - First scheduled run at next 12:00/18:00/23:00

---

## Known Issues

1. **Peter's session caching** - Changes to PETERBOT_SOUL.md/CLAUDE.md don't take effect until Peter re-reads them or session restarts
2. **Memory injection latency** - Training data inserts are queued, may take a few minutes to appear in context

---

## Architecture Diagram (Final State)

```
Discord Message
      ↓
   bot.py
      ↓
┌─────────────────────────────────────────────────────────┐
│                    router.py                             │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ Memory      │  │ Recent       │  │ Output         │ │
│  │ Injection   │  │ Buffer       │  │ Filtering      │ │
│  └─────────────┘  └──────────────┘  └────────────────┘ │
└─────────────────────────────────────────────────────────┘
      ↓
   context.md written to WSL
      ↓
   Claude Code (tmux session: claude-peterbot)
      ↓
   Response extracted & filtered
      ↓
   Discord Channel

Scheduled Jobs:
   SCHEDULE.md → scheduler.py → data_fetchers.py → skill SKILL.md → Claude Code → Discord
```
