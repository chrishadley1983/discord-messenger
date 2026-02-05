# BUILDING.md

## READ THIS BEFORE WRITING ANY CODE

Peter, this document defines how you build things. These patterns exist to maintain system coherence and allow Chris to review/approve changes. Deviating from these patterns creates technical debt and conflicts.

---

## Architecture Overview
```
User Message
     |
     v
+---------+     +--------------+     +-------------+
| Discord |---->|   bot.py     |---->|   router    |
+---------+     +--------------+     +-------------+
                                            |
                      +---------------------+---------------------+
                      v                     v                     v
               +------------+       +--------------+      +--------------+
               | Claude Code |       | Skill Lookup |      | Pre-fetchers |
               |   (tmux)    |<------|  SKILL.md    |<-----|data_fetchers |
               +------------+       +--------------+      +--------------+
                      |
                      v
               +------------+
               |  Response  |---> Discord Channel
               +------------+
```

**Key principle:** Everything flows through Claude Code for natural language generation. No direct Discord posting.

---

## File Locations

| Type | Correct Location | NEVER |
|------|------------------|-------|
| Data fetching functions | `data_fetchers.py` | `jobs/*.py` |
| Skill definitions | `skills/{name}/SKILL.md` | Inline Python |
| Scheduled jobs | `SCHEDULE.md` | Direct APScheduler calls |
| Configuration | `config.py` | Hardcoded in scripts |
| Secrets/API keys | `.env` | Anywhere else |
| Helper utilities | `utils/` (if complex) | Scattered files |

### What Each File Does

| File | Purpose | You Can Modify? |
|------|---------|-----------------|
| `bot.py` | Discord connection, message handling | No |
| `router.py` | Routes messages to Claude Code | No |
| `scheduler.py` | Parses SCHEDULE.md, runs jobs | No |
| `memory.py` | Memory injection/capture | No |
| `config.py` | Environment config | No |
| `data_fetchers.py` | Pre-fetch functions for skills | Yes - add functions |
| `skills/*/SKILL.md` | Skill instructions | Yes - create/edit |
| `SCHEDULE.md` | Scheduled job definitions | No - needs approval |
| `HEARTBEAT.md` | To-do list | Yes |
| `manifest.json` | Auto-generated on load | No - auto-generated |

---

## Creating a New Skill

### Step 1: Create SKILL.md
```
skills/
  {skill-name}/
    SKILL.md
```

Use the template at `skills/_template/SKILL.md`.

### Step 2: Add Pre-fetcher (if needed)

In `data_fetchers.py`, add your async function:
```python
async def get_something_data() -> dict[str, Any]:
    """Fetch data for the something skill."""
    try:
        # API call here
        return {"data": result, "fetched_at": datetime.now().isoformat()}
    except Exception as e:
        return {"error": str(e), "data": None}
```

Register in SKILL_DATA_FETCHERS dict:
```python
SKILL_DATA_FETCHERS = {
    "something": get_something_data,
    # ... other fetchers
}
```

### Step 3: Add to SCHEDULE.md (if scheduled)

**STOP** - This requires Chris's approval.

Add to HEARTBEAT.md instead:
```markdown
- [ ] [SKILL] Add {skill-name} to SCHEDULE.md - proposed: {time} {days}
```

### Step 4: Test
```
!skill {skill-name}
```

---

## Patterns to Follow

### DO
```python
# Async for all I/O
async def get_something_data():
    ...

# UK timezone for all times
from zoneinfo import ZoneInfo
uk_tz = ZoneInfo("Europe/London")
local_time = datetime.now(uk_tz)

# Error handling with fallbacks
try:
    data = await fetch_api()
except Exception as e:
    return {"error": str(e), "data": None}

# Type hints
async def get_weather_data() -> dict[str, Any]:
    ...

# Docstrings
async def get_garmin_data():
    """Fetch today's health metrics from Garmin Connect."""
    ...
```

### DON'T
```python
# Direct Discord posting
await channel.send("Here are the scores...")  # NO!

# Hardcoded secrets
API_KEY = "abc123"  # NO! Use config.py / .env

# Synchronous blocking calls
response = requests.get(url)  # NO! Use async

# Direct APScheduler registration
scheduler.add_job(my_func, 'cron', hour=9)  # NO! Use SCHEDULE.md

# Creating standalone job files
# jobs/my_new_job.py  # NO! Use skills/ + data_fetchers.py
```

---

## Output Routing Rules

**ALL responses go through Claude Code.** This ensures:

1. Natural language formatting
2. Personality consistency
3. Memory capture
4. Conversation context

### Correct Flow
```
Pre-fetcher gets data
        |
        v
SKILL.md instructions + data injected into Claude Code prompt
        |
        v
Claude Code generates natural response
        |
        v
Response posted to Discord via router
```

### Wrong Flow
```
Python script fetches data
        |
        v
Python script formats message
        |
        v
Python script posts directly to Discord  <-- WRONG
```

---

## What Requires Approval

Add these to HEARTBEAT.md for Chris to review:

| Action | Why |
|--------|-----|
| New Python files (outside skills/) | Architecture impact |
| Modify SCHEDULE.md | Affects automated behavior |
| Modify core files (bot.py, scheduler.py, router.py, config.py) | System stability |
| New scheduled jobs | Resource usage, notification frequency |
| New integrations requiring API keys | Security, cost |
| Direct Discord channel posting | Bypasses architecture |

---

## What You CAN Do Without Approval

| Action | Location |
|--------|----------|
| Create new skill SKILL.md | `skills/{name}/SKILL.md` |
| Add pre-fetcher function | `data_fetchers.py` |
| Edit existing skill instructions | `skills/{name}/SKILL.md` |
| Add items to HEARTBEAT.md | `HEARTBEAT.md` |
| Create helper functions in existing files | Within existing structure |

---

## Common Mistakes

### Mistake 1: Creating jobs/*.py files

**Wrong:**
```
jobs/
  football_scores.py  # Standalone script with APScheduler
```

**Right:**
```
skills/football-scores/SKILL.md  # Skill definition
data_fetchers.py                  # Add get_football_scores_data()
SCHEDULE.md                       # Add schedule (with approval)
```

### Mistake 2: Posting directly to Discord

**Wrong:**
```python
channel = bot.get_channel(123456)
await channel.send("Match update: Arsenal 2-1")
```

**Right:**
```python
# In SKILL.md, define the response format
# Claude Code will generate and post via router
```

### Mistake 3: Hardcoding schedules

**Wrong:**
```python
scheduler.add_job(check_scores, 'cron', hour=15, day_of_week='sat')
```

**Right:**
```markdown
# In SCHEDULE.md (after approval)
| Football Scores | football-scores | 15:00 Sat,Sun UK | #peterbot | yes |
```

### Mistake 4: Forgetting error handling

**Wrong:**
```python
async def get_something_data():
    response = await fetch_api()
    return response.json()
```

**Right:**
```python
async def get_something_data():
    try:
        response = await fetch_api()
        return {"data": response.json(), "error": None}
    except Exception as e:
        return {"error": str(e), "data": None}
```

---

## Checklist Before Creating Anything

- [ ] Read this document
- [ ] Check if similar skill/feature already exists
- [ ] Identify correct file locations
- [ ] Plan the data flow (pre-fetcher -> SKILL.md -> Claude Code -> Discord)
- [ ] If scheduled, add to HEARTBEAT.md for approval first
- [ ] If new API/integration, add to HEARTBEAT.md for approval first
- [ ] Test with `!skill {name}` before proposing schedule

---

## Questions?

If unsure about architecture decisions, add to HEARTBEAT.md:
```markdown
- [ ] [QUESTION] Should X use pattern Y or Z? Context: ...
```

Chris will clarify before you build.
