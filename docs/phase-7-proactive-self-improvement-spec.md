# Phase 7: Proactive Infrastructure + Self-Improvement

## Overview

Phase 7 establishes Peterbot's proactive capabilities — the ability to act without being asked and to improve its own capabilities within governance boundaries.

**Three sub-phases:**
- **7a**: Scheduler infrastructure + SCHEDULE.md
- **7b**: Migrate all existing scheduled jobs
- **7c**: Self-improvement governance

> **Note:** USER.md was considered but removed. If Peter lacks core user context, the fix is improving peterbot-mem retrieval, not adding a workaround file.

---

## Configuration Decisions

| Setting | Value |
|---------|-------|
| Heartbeat interval | 30 minutes |
| Quiet hours | 11pm - 6am |
| Output channel | #peterbot |
| Schedule format | SCHEDULE.md (Peter can edit) |

---

## 7a: Scheduler Infrastructure

### Architecture

```
┌─────────────────────────────────────────────────────┐
│  Scheduler (APScheduler)                            │
│  - Reads SCHEDULE.md on startup                     │
│  - Hot-reloads on file change (optional)            │
│  - Cron jobs for fixed times                        │
│  - Interval jobs for periodic checks                │
└─────────────────────┬───────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────┐
│  Job Execution                                      │
│  1. Load relevant skill from skills/                │
│  2. Call Claude Code with skill + context           │
│  3. Post to configured channel (or NO_REPLY)        │
└─────────────────────────────────────────────────────┘
```

### SCHEDULE.md Format

```markdown
# Peterbot Schedule

Peter can edit this file to manage scheduled jobs.
Changes take effect on next scheduler reload.

## Fixed Time Jobs (Cron)

| Job | Skill | Schedule | Channel | Enabled |
|-----|-------|----------|---------|---------|
| Morning Briefing | morning-briefing | 07:00 UK | #ai-briefings | yes |
| Morning Health Digest | health-digest | 08:00 UK | #food-log | yes |
| School Run (Mon-Wed,Fri) | school-run | 08:10 UK | #traffic-reports | yes |
| School Run (Thu) | school-run | 07:45 UK | #traffic-reports | yes |
| School Pickup (Mon,Tue,Thu,Fri) | school-pickup | 14:55 UK | #traffic-reports | yes |
| School Pickup (Wed) | school-pickup | 16:50 UK | #traffic-reports | yes |
| Daily Nutrition Summary | nutrition-summary | 21:00 UK | #food-log | yes |
| News Briefing | news | 07:00 UK | #news | yes |
| Weekly Health Summary | weekly-health | Sun 09:00 UK | #food-log | yes |
| Monthly Health Summary | monthly-health | 1st 09:00 UK | #food-log | yes |
| Weekly API Usage | api-usage | Mon 09:00 UK | #api-usage | yes |

## Interval Jobs

| Job | Skill | Interval | Channel | Enabled |
|-----|-------|----------|---------|---------|
| Heartbeat | heartbeat | 30m | #peterbot | yes |
| Balance Monitor | balance-monitor | 60m | #api-balances | yes |
| Hydration Check-in | hydration | 2h (9am-9pm) | #food-log | yes |

## Quiet Hours

No jobs run between 23:00 and 06:00 UK.
```

### Scheduler Implementation

```python
# scheduler.py (discord-messenger)

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

class PeterbotScheduler:
    def __init__(self, bot):
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.schedule_path = "domains/peterbot/wsl_config/SCHEDULE.md"
    
    def load_schedule(self):
        """Parse SCHEDULE.md and register jobs"""
        # Parse markdown tables
        # Register cron jobs for fixed times
        # Register interval jobs for periodic checks
        # Respect quiet hours
        pass
    
    async def execute_job(self, skill_name: str, channel_id: int):
        """Run a scheduled job via Claude Code"""
        # 1. Load skill from skills/{skill_name}/SKILL.md
        # 2. Call Claude Code with skill instructions
        # 3. Post response to channel (unless NO_REPLY)
        pass
    
    def start(self):
        self.load_schedule()
        self.scheduler.start()
```

### Implementation Tasks

| Task | Description |
|------|-------------|
| Create scheduler.py | APScheduler integration with SCHEDULE.md parsing |
| SCHEDULE.md parser | Extract jobs from markdown tables |
| Quiet hours enforcement | Skip jobs during 23:00-06:00 |
| Job executor | Route to Claude Code with skill context |
| NO_REPLY detection | Suppress Discord message if response contains NO_REPLY |
| Hot reload (optional) | Watch SCHEDULE.md for changes |

---

## 7b: Migrate Existing Scheduled Jobs

### Jobs to Migrate

11 jobs currently running in discord-messenger need skills + SCHEDULE.md entries:

| # | Job | Current Schedule | Channel | Skill to Create |
|---|-----|------------------|---------|-----------------|
| 1 | Balance Monitor | Every hour :00 UTC | #api-balances | `balance-monitor` |
| 2 | Hydration Check-in | 9,11,13,15,17,19,21 UK | #food-log | `hydration` |
| 3 | AI Morning Briefing | 6:30am UTC | #ai-briefings | `morning-briefing` |
| 4 | Morning Health Digest | 8:00am UK | #food-log | `health-digest` |
| 5 | School Run (Morning) | 8:10am Mon-Wed,Fri / 7:45am Thu | #traffic-reports | `school-run` |
| 6 | School Pickup (Afternoon) | 2:55pm Mon,Tue,Thu,Fri / 4:50pm Wed | #traffic-reports | `school-pickup` |
| 7 | Weekly Health Summary | Sunday 9:00am UK | #food-log | `weekly-health` |
| 8 | Monthly Health Summary | 1st of month 9:00am UK | #food-log | `monthly-health` |
| 9 | Daily Nutrition Summary | 9:00pm UK | #food-log | `nutrition-summary` |
| 10 | Morning News Briefing | 7:00am UK | #news | `news` (exists) |
| 11 | Weekly API Usage | Monday 9:00am UK | #api-usage | `api-usage` |

### Skill Template

Each job becomes a skill in `skills/{skill-name}/SKILL.md`:

```markdown
---
name: hydration
description: Check hydration and step progress, post motivational message
triggers: scheduled
channel: food-log
---

# Hydration Check-in

## Purpose
Post water intake and step progress with contextual motivation.

## Data Sources
- Water intake: Supabase hydration table
- Steps: Garmin API

## Output Format
💧 Hydration Check-in

Water: {actual}ml / 3,500ml ({percent}%)
Steps: {actual} / 15,000 ({percent}%)

{contextual motivation based on time of day and progress}

## Rules
- Use emoji status: ✅ >80%, ⚠️ 50-80%, ❌ <50%
- Morning: encouraging start
- Midday: progress check
- Evening: final push or celebration
```

### Migration Process

For each job:
1. Create skill in `skills/{name}/SKILL.md`
2. Extract any hardcoded logic into skill instructions
3. Add entry to SCHEDULE.md
4. Test via manual trigger (`!{skillname}` command)
5. Disable old job in current scheduler
6. Verify scheduled execution works

### Data Access

Skills need access to various APIs. Current approach (API calls in Python) vs future (MCP servers in Phase 8):

| Data | Phase 7 (Skills) | Phase 8 (MCP) |
|------|------------------|---------------|
| Supabase (nutrition, hydration) | Direct API call | MCP server |
| Garmin (steps, sleep, HR) | Existing API wrapper | MCP server |
| Withings (weight) | Existing API wrapper | MCP server |
| Traffic | Web search | Web search |
| News | Web search + RSS | MCP server |
| API balances | Direct API calls | MCP server |

For Phase 7, skills can instruct Claude Code to use existing Python functions or web search. Phase 8 adds structured MCP tool access.

### Implementation Tasks

| Task | Description |
|------|-------------|
| Create 11 skills | One SKILL.md per job |
| Add manual triggers | `!skillname` commands for testing |
| Populate SCHEDULE.md | All jobs with correct schedules |
| Migration testing | Each job runs correctly via new system |
| Decommission old scheduler | Remove legacy job code |
| WhatsApp routing | School run/pickup also post to WhatsApp |

---

## 7c: Self-Improvement Capability

### Concept

Peter can improve his own capabilities within defined boundaries. This is NOT autonomous agent chaos — it's governed self-improvement.

### Governance Tiers

| Tier | What | Governance | Examples |
|------|------|------------|----------|
| **Free** | Create/modify skills in `skills/`, update SCHEDULE.md, update HEARTBEAT.md | Just do it, notify Chris after | New skill, add/modify scheduled job, tweak heartbeat checks |
| **Propose** | CLAUDE.md, SOUL.md changes | Show diff, wait for approval | "I'd like to update my SOUL.md to be less chatty - here's the change" |
| **Never** | Core routing, auth, database schema | "This needs a proper phase spec" | Code changes, new API endpoints |

### Workspace Structure

```
peterbot-mem/
├── skills/                    ← Peter can write here freely
│   ├── hydration/
│   │   └── SKILL.md
│   ├── morning-briefing/
│   │   └── SKILL.md
│   ├── news/
│   │   └── SKILL.md
│   └── _template/
│       └── SKILL.md           ← Template for new skills
├── CLAUDE.md                  ← Peter can propose changes
├── PETERBOT_SOUL.md           ← Peter can propose changes
├── SCHEDULE.md                ← Peter can edit freely
└── HEARTBEAT.md               ← Peter can edit freely
```

### Skills System

Skills are markdown files that teach Peter how to do things. Following the AgentSkills spec (same as Clawdbot/Moltbot).

#### Skill Template

```markdown
---
name: skill-name
description: What this skill does
requirements:
  - Any CLI tools or APIs needed
---

# Skill Name

## Purpose
What this skill accomplishes.

## Usage
When to use this skill.

## Steps
1. First step
2. Second step
3. etc.

## Examples
Example invocations and expected outputs.
```

#### Example: Weather Skill

```markdown
---
name: weather
description: Get current weather and forecast
requirements:
  - web_search tool
---

# Weather

## Purpose
Fetch current weather conditions and forecast for a location.

## Usage
When user asks about weather, or for contextual info in briefings/hydration.

## Steps
1. Use web_search to query "[location] weather"
2. Extract current conditions and forecast
3. Format naturally (not robotic)

## Examples
User: "What's the weather like?"
→ Search "Tonbridge weather"
→ "Currently 8°C and cloudy. Expecting rain this afternoon, clearing by evening."
```

### CLAUDE.md Additions

Add to CLAUDE.md:

```markdown
## Self-Improvement

### You CAN freely:
- Create new skills in `skills/` folder
- Modify existing skills
- Update SCHEDULE.md (add/remove/modify scheduled jobs)
- Update HEARTBEAT.md with new checks
- After making changes, briefly mention what you did

### You MUST propose (show diff, get approval):
- Changes to CLAUDE.md
- Changes to PETERBOT_SOUL.md
- Format: "I'd like to change X because Y. Here's the diff: ..."

### You CANNOT:
- Modify core system code (*.py, *.ts files outside skills/)
- Change database schema
- Add new API endpoints
- Bypass the proposal process for protected files

### Skill Creation
When you identify a repeated task or capability gap:
1. Create a new skill in `skills/[skill-name]/SKILL.md`
2. Follow the template in `skills/_template/SKILL.md`
3. Optionally add to SCHEDULE.md if it should run automatically
4. Let Chris know: "I've created a new skill for X"

### Schedule Management
You can manage your own schedule:
- Add new scheduled jobs
- Modify timing of existing jobs
- Enable/disable jobs
- Changes take effect on scheduler reload
```

### Implementation Tasks

| Task | Description |
|------|-------------|
| Create skills/ directory structure | With _template |
| Add skill discovery to CC | Read skills on session start |
| Update CLAUDE.md | Self-improvement instructions |
| Proposal workflow | How Peter proposes changes |
| Git integration (optional) | Auto-commit skill changes |

---

---

## Success Criteria

Phase 7 is complete when:

**7a - Infrastructure:**
1. ✅ Scheduler running (APScheduler reads SCHEDULE.md)
2. ✅ Cron jobs execute at specified times
3. ✅ Interval jobs execute at specified intervals
4. ✅ Quiet hours enforced (23:00-06:00)
5. ✅ NO_REPLY suppression working

**7b - Migration:**
6. ✅ All 11 existing jobs have skills
7. ✅ All jobs running via new scheduler
8. ✅ Old scheduler decommissioned
9. ✅ Manual triggers work (`!skillname`)

**7c - Self-Improvement:**
10. ✅ Skills folder structure in place
11. ✅ Peter can create a new skill unprompted
12. ✅ Peter can modify SCHEDULE.md
13. ✅ Governance enforced (propose for CLAUDE.md/SOUL.md)

---

## Phase 8 Preview

Phase 8 adds MCP server integrations — structured tool access to external services:

| MCP Server | Capabilities |
|------------|--------------|
| eBay | Order monitoring, message alerts, listing stats |
| Google Calendar | Event awareness, reminders, scheduling |
| Garmin | Steps, sleep, HR, activities |
| Gmail | Email monitoring, alerts |
| Hadley Bricks API | Inventory, sales, orders |

Once MCP servers are connected, Peter can build skills that use them and add monitoring to SCHEDULE.md.

---

## Files to Create

| File | Location | Purpose |
|------|----------|---------|
| scheduler.py | discord-messenger/domains/peterbot/ | APScheduler integration |
| SCHEDULE.md | discord-messenger/domains/peterbot/wsl_config/ | Job schedule (Peter-editable) |
| HEARTBEAT.md | discord-messenger/domains/peterbot/wsl_config/ | Heartbeat checks |
| skills/_template/SKILL.md | discord-messenger/domains/peterbot/wsl_config/skills/ | Skill template |
| skills/hydration/SKILL.md | ... | Hydration check-in |
| skills/morning-briefing/SKILL.md | ... | AI morning briefing |
| skills/health-digest/SKILL.md | ... | Morning health digest |
| skills/school-run/SKILL.md | ... | School run traffic |
| skills/school-pickup/SKILL.md | ... | School pickup traffic |
| skills/weekly-health/SKILL.md | ... | Weekly health summary |
| skills/monthly-health/SKILL.md | ... | Monthly health summary |
| skills/nutrition-summary/SKILL.md | ... | Daily nutrition summary |
| skills/balance-monitor/SKILL.md | ... | API balance monitor |
| skills/api-usage/SKILL.md | ... | Weekly API usage |

## CLAUDE.md Updates

Add sections:
- Self-Improvement (governance tiers)
- Skills (creation instructions)
- Schedule Management (how to modify SCHEDULE.md)
