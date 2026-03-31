# Scheduled Jobs Reference

## Overview

Peter runs 50+ scheduled jobs via APScheduler, defined in `domains/peterbot/wsl_config/SCHEDULE.md`. Jobs execute skills through Claude Code (Opus 4.6, 50 max turns) with pre-fetched data. The scheduler is initialised in `bot.py` via `PeterbotScheduler` and can be toggled with `USE_PETERBOT_SCHEDULER`.

**Key files:**

| File | Purpose |
|------|---------|
| `domains/peterbot/wsl_config/SCHEDULE.md` | Job definitions (markdown tables) |
| `domains/peterbot/scheduler.py` | Schedule parser, APScheduler registration, job execution |
| `domains/peterbot/data_fetchers.py` | Pre-fetch functions (~60 fetchers, 3700+ lines) |
| `domains/peterbot/config.py` | `SECOND_BRAIN_SAVE_SKILLS` list, timeouts |
| `domains/peterbot/wsl_config/skills/*/SKILL.md` | Skill instructions for each job |
| `peter_dashboard/job_history.db` | SQLite execution history |

---

## Schedule Format

SCHEDULE.md uses two markdown table sections: **Fixed Time Jobs (Cron)** and **Interval Jobs**.

| Column | Description |
|--------|-------------|
| Job | Human-readable name |
| Skill | Skill folder name (maps to `skills/<name>/SKILL.md`) |
| Schedule / Interval | Timing expression (see syntax below) |
| Channel | Discord channel + optional modifiers |
| Enabled | `yes` / `no` |

### Schedule Syntax

| Format | Example | Meaning |
|--------|---------|---------|
| `HH:MM UK` | `07:00 UK` | Daily at 7am UK time |
| `HH:MM,HH:MM UK` | `09:00,11:00 UK` | Multiple times daily |
| `Day HH:MM UK` | `Sunday 09:00 UK` | Specific day of week |
| `Day-Day,Day HH:MM UK` | `Mon-Wed,Fri 08:10 UK` | Multiple days with ranges |
| `1st HH:MM UK` | `1st 09:00 UK` | First of month |
| `hourly UK` | `hourly UK` | Every hour at :00 |
| `hourly+N UK` | `hourly+3 UK` | Every hour at :03 past |
| `half-hourly UK` | `half-hourly UK` | Every 30 min at :00/:30 |
| `half-hourly+N UK` | `half-hourly+1 UK` | Every 30 min at :01/:31 |
| `Nm` | `10m` | Interval (minutes) |
| `Nh` | `2h` | Interval (hours) |

### Channel Modifiers

Modifiers are appended to the channel name in the SCHEDULE.md table:

| Modifier | Example | Meaning |
|----------|---------|---------|
| `+WhatsApp:chris` | `#peterbot+WhatsApp:chris` | Also send to Chris's WhatsApp |
| `+WhatsApp:group` | `#peterbot+WhatsApp:group` | Also send to family WhatsApp group |
| `+WhatsApp:abby` | `#peterbot+WhatsApp:abby` | Also send to Abby's WhatsApp |
| `!quiet` | `#alerts!quiet` | Exempt from quiet hours (23:00-06:00) |

Modifiers can be combined: `#peterbot+WhatsApp:chris!quiet`

---

## Complete Daily Timeline (Weekday)

Times are UK local. Jobs marked with a day name only run on that day.

### 02:00 - 06:00 (Quiet Hours Exempt)

| Time | Skill | Channel | Notes |
|------|-------|---------|-------|
| 02:00 | `parser-improve` | #peter-heartbeat!quiet | Self-improving parser cycle |

### 06:00 - 08:00 (Morning Sequence)

| Time | Skill | Channel | Notes |
|------|-------|---------|-------|
| 06:00 | `security-monitor` | #alerts | 1st of 5 daily security checks |
| 06:00 | `price-scanner` | #food-log | **Mon only** |
| 06:05 | `pl-results` | #peterbot+WhatsApp:chris | Premier League results overnight |
| 06:30 | `morning-laughs` | #peterbot | Daily joke/fun content |
| 06:45 | `morning-quality-report` | #peter-heartbeat | Parser quality metrics review |
| 06:50 | `system-health` | #alerts | Cross-system health check (DM + HB) |
| 07:01 | `morning-briefing` | #ai-briefings | AI/tech morning briefing |
| 07:02 | `news` | #news | General news digest |
| 07:02 | `hydration` | #food-log+WhatsApp:chris | 1st of 15 daily hydration checks |
| 07:25 | `kids-daily` | #peterbot+WhatsApp:group | Kids daily briefing (school, weather) |
| 07:30 | `cooking-reminder` | #food-log | Morning cooking reminder |
| 07:30 | `school-weekly-spellings` | #peter-chat+WhatsApp:group | **Mon only** |
| 07:45 | `school-run` | #traffic-reports+WhatsApp:group | **Thu only** (early start) |
| 07:55 | `health-digest` | #food-log | Garmin + Withings + nutrition digest |

### 08:00 - 10:00 (Morning Operational)

| Time | Skill | Channel | Notes |
|------|-------|---------|-------|
| 08:00 | `whatsapp-keepalive` | #peter-heartbeat!quiet | WhatsApp connection health check |
| 08:00 | `spurs-matchday` | #peterbot+WhatsApp:chris | Match days only (conditional) |
| 08:00 | `saturday-sport-preview` | #peterbot+WhatsApp:chris | **Sat only** |
| 08:02 | `email-summary` | #peterbot | Gmail inbox summary |
| 08:02 | `hydration` | #food-log+WhatsApp:chris | |
| 08:04 | `schedule-today` | #peterbot | Today's calendar and jobs |
| 08:06 | `notion-todos` | #peterbot | Pending Notion tasks |
| 08:08 | `github-activity` | #peterbot | Daily GitHub activity summary |
| 08:10 | `school-run` | #traffic-reports+WhatsApp:group | **Mon-Wed, Fri** |
| 08:30 | `cricket-scores` | #peterbot+WhatsApp:chris | Cricket match updates |
| 09:00 | `ballot-reminders` | #peterbot+WhatsApp:chris | Ticket ballot deadline alerts |
| 09:02 | `hydration` | #food-log+WhatsApp:chris | |
| 09:02 | `subscription-monitor` | #alerts+WhatsApp:chris | **Sun only** |
| 09:05 | `youtube-digest` | #youtube | YouTube subscription digest |
| 09:10 | `healthera-prescriptions` | #peterbot | Prescription status check |
| 09:10 | `weekly-health` | #food-log | **Sun only** |
| 09:15 | `monthly-health` | #food-log | **1st of month only** |
| 09:30 | `amazon-purchases` | #peterbot | Amazon order tracking |
| 09:32 | `pocket-money-weekly` | #peterbot | **Sun only** |
| 09:35 | `hb-full-sync-print` | #peterbot | Hadley Bricks sync + pick list print |

### 10:00 - 14:00 (Midday)

| Time | Skill | Channel | Notes |
|------|-------|---------|-------|
| 10:00 | `security-monitor` | #alerts | 2nd security check |
| 10:00 | `recipe-discovery` | #food-log | **Sun only** |
| 10:00 | `claude-history` | #peterbot | **1st of month only** (no skill, direct) |
| 10:02 | `hydration` | #food-log+WhatsApp:chris | |
| 10:15 | `property-valuation` | #peterbot | **1st of month only** |
| 11:02 | `hydration` | #food-log+WhatsApp:chris | |
| 12:00 | `self-reflect` | #alerts!quiet | Memory and performance reflection |
| 12:02 | `hydration` | #food-log+WhatsApp:chris | |
| 13:02 | `hydration` | #food-log+WhatsApp:chris | |

### 14:00 - 18:00 (Afternoon)

| Time | Skill | Channel | Notes |
|------|-------|---------|-------|
| 14:00 | `security-monitor` | #alerts | 3rd security check |
| 14:02 | `hydration` | #food-log+WhatsApp:chris | |
| 14:55 | `school-pickup` | #traffic-reports+WhatsApp:group | **Mon, Tue, Thu, Fri** |
| 15:02 | `hydration` | #food-log+WhatsApp:chris | |
| 16:02 | `hydration` | #food-log+WhatsApp:chris | |
| 16:50 | `school-pickup` | #traffic-reports+WhatsApp:group | **Wed only** (early finish) |
| 17:02 | `hydration` | #food-log+WhatsApp:chris | |

### 18:00 - 23:00 (Evening)

| Time | Skill | Channel | Notes |
|------|-------|---------|-------|
| 18:00 | `self-reflect` | #alerts!quiet | 2nd daily reflection |
| 18:00 | `security-monitor` | #alerts | 4th security check |
| 18:00 | `schedule-week` | #peterbot | **Sun only** |
| 18:02 | `hydration` | #food-log+WhatsApp:chris | |
| 18:05 | `github-weekly` | #peterbot | **Sun only** |
| 18:10 | `kids-weekly` | #peterbot+WhatsApp:group | **Sun only** |
| 19:00 | `tutor-email-parser` | #peterbot | **Tue only** — 11+ tutor emails |
| 19:00 | `spelling-test-generator` | #peterbot+WhatsApp:chris | **Fri only** |
| 19:02 | `hydration` | #food-log+WhatsApp:chris | |
| 19:30 | `paper-builder` | #peterbot | **Tue only** — 11+ practice papers |
| 20:00 | `whatsapp-keepalive` | #peter-heartbeat!quiet | 2nd WhatsApp health check |
| 20:02 | `hydration` | #food-log+WhatsApp:chris | |
| 20:30 | `meal-rating` | #food-log | Rate today's meals |
| 20:45 | `cooking-reminder` | #food-log | Evening cooking reminder |
| 21:00 | `nutrition-summary` | #food-log | End-of-day nutrition totals |
| 21:00 | `practice-allocate` | #peterbot | **Tue only** — allocate 11+ practice |
| 21:02 | `hydration` | #food-log+WhatsApp:chris | Final hydration check |
| 21:05 | `daily-instagram-prep` | #peterbot | Instagram content prep for Hadley Bricks |
| 21:45 | `daily-thoughts` | #peterbot!quiet | Daily reflection/journal prompt |
| 22:00 | `security-monitor` | #alerts | 5th (final) security check |
| 23:00 | `self-reflect` | #alerts!quiet | 3rd daily reflection (quiet hours exempt) |

---

## Recurring Interval Jobs

| Job | Skill | Interval | Channel | Notes |
|-----|-------|----------|---------|-------|
| Heartbeat | `heartbeat` | Every 30 min (+1 offset = :01/:31) | #peter-heartbeat!quiet | System health + Peter queue pickup |
| Balance Monitor | `balance-monitor` | Every hour (+3 offset = :03) | #api-costs | Claude, Moonshot, Grok API + GCP billing |
| Spurs Live | `spurs-live` | Every 10 min | #peterbot+WhatsApp:chris!quiet | Live match updates (conditional on match day) |

---

## Hydration Schedule (Detailed)

The hydration skill runs 15 times daily with pre-fetched water intake and step data:

```
07:02, 08:02, 09:02, 10:02, 11:02, 12:02, 13:02,
14:02, 15:02, 16:02, 17:02, 18:02, 19:02, 20:02, 21:02
```

All post to `#food-log+WhatsApp:chris`. Each check reports current water intake vs target and step count.

---

## Quiet Hours

**23:00 - 06:00 UK** -- no jobs execute unless the channel has the `!quiet` modifier.

Exempt jobs (run during quiet hours):
- `heartbeat` (#peter-heartbeat!quiet) -- every 30 min
- `parser-improve` (#peter-heartbeat!quiet) -- 02:00
- `whatsapp-keepalive` (#peter-heartbeat!quiet) -- 08:00, 20:00
- `self-reflect` (#alerts!quiet) -- 12:00, 18:00, 23:00
- `daily-thoughts` (#peterbot!quiet) -- 21:45
- `spurs-live` (#peterbot+WhatsApp:chris!quiet) -- every 10 min

---

## Data Fetchers

Pre-fetch functions in `data_fetchers.py` run **before** skill execution to provide structured data. Skills without a fetcher rely on web search or API calls during execution.

### Registered Fetchers (SKILL_DATA_FETCHERS)

#### Health & Nutrition
| Skill | Fetcher | Data Sources |
|-------|---------|--------------|
| `nutrition-summary` | `get_nutrition_data()` | Hadley API nutrition endpoints, daily targets |
| `hydration` | `get_hydration_data()` | Hadley API water intake + Garmin steps |
| `health-digest` | `get_health_digest_data()` | Garmin, Withings, nutrition; syncs to Supabase |
| `weekly-health` | `get_weekly_health_data()` | Supabase `garmin_daily_summary` (7 days) |
| `monthly-health` | `get_monthly_health_data()` | Supabase `garmin_daily_summary` (30 days) |
| `meal-rating` | `get_meal_rating_data()` | Today's logged meals for rating |
| `cooking-reminder` | `get_cooking_reminder_data()` | Meal plan + pantry data |
| `price-scanner` | `get_price_scanner_data()` | Grocery price tracking |
| `recipe-discovery` | `get_recipe_discovery_data()` | Recipe search + nutrition gaps |

#### Productivity & Communication
| Skill | Fetcher | Data Sources |
|-------|---------|--------------|
| `email-summary` | `get_email_summary_data()` | Gmail API (unread, important) |
| `schedule-today` | `get_schedule_today_data()` | Google Calendar + SCHEDULE.md |
| `schedule-week` | `get_schedule_week_data()` | Google Calendar (week view) |
| `notion-todos` | `get_notion_todos_data()` | Notion API (incomplete tasks) |
| `morning-briefing` | `get_morning_briefing_data()` | Reddit, tech news aggregation |

#### Sport
| Skill | Fetcher | Data Sources |
|-------|---------|--------------|
| `pl-results` | `get_pl_results_data()` | Football API (Premier League) |
| `spurs-matchday` | `get_spurs_matchday_data()` | Fixture data + team news |
| `spurs-live` | `get_spurs_live_data()` | Live match data (scores, events) |
| `cricket-scores` | `get_cricket_scores_data()` | Cricket API |
| `saturday-sport-preview` | `get_saturday_sport_preview_data()` | Multi-sport fixtures |
| `ballot-reminders` | `get_ballot_reminders_data()` | Ticket ballot deadlines |

#### Kids & School
| Skill | Fetcher | Data Sources |
|-------|---------|--------------|
| `school-run` | `get_school_run_data()` | Google Maps, Weather API, Calendar |
| `school-pickup` | `get_school_pickup_data()` | Google Maps, Weather API |
| `school-weekly-spellings` | `get_school_data()` | Supabase spellings + school events |
| `tutor-email-parser` | `get_tutor_email_data()` | Gmail (tutor emails) |
| `paper-builder` | `get_paper_builder_data()` | 11+ practice paper data |
| `practice-allocate` | `get_practice_allocate_data()` | 11+ practice allocation |
| `pocket-money-weekly` | `get_pocket_money_weekly_data()` | Chore completion data |

#### Hadley Bricks (Business)
| Skill | Fetcher | Data Sources |
|-------|---------|--------------|
| `hb-full-sync-print` | `get_hb_full_sync_and_print_data()` | Full inventory sync + pick list |
| `hb-dashboard` | `get_hb_dashboard_data()` | Business dashboard summary |
| `hb-orders` | `get_hb_orders_data()` | Order status across platforms |
| `hb-pick-list` | `get_hb_pick_list_data()` | Outstanding pick list |
| `hb-daily-activity` | `get_hb_daily_activity_data()` | Daily sales/dispatch activity |
| `hb-arbitrage` | `get_hb_arbitrage_data()` | Arbitrage opportunity scanner |
| `hb-pnl` | `get_hb_pnl_data()` | Profit and loss report |
| `daily-instagram-prep` | `get_instagram_prep_data()` | Instagram content + images via APIs |

#### System & Monitoring
| Skill | Fetcher | Data Sources |
|-------|---------|--------------|
| `balance-monitor` | `get_balance_data()` | Claude, Moonshot, Grok APIs + GCP billing |
| `system-health` | `get_system_health_data()` | Job health across DM + HB systems |
| `heartbeat` | `get_heartbeat_data()` | System status + Peter queue tasks |
| `self-reflect` | `get_self_reflect_data()` | Memories, brain saves, job history |
| `morning-quality-report` | `get_morning_quality_data()` | Parser quality metrics |
| `parser-improve` | `run_parser_improvement_cycle()` | Parser improvement pipeline |
| `subscription-monitor` | `get_subscription_monitor_data()` | Active subscription costs |
| `whatsapp-health` | `get_whatsapp_health_data()` | WhatsApp connection status |
| `youtube-digest` | `get_youtube_data()` | YouTube API + Supabase dedup |
| `github-activity` | `get_github_daily_data()` | GitHub commits/PRs (daily) |
| `github-weekly` | `get_github_weekly_data()` | GitHub commits/PRs (weekly) |
| `amazon-purchases` | `get_amazon_purchases_data()` | Amazon order tracking |

### Fetcher Skip Signal

Fetchers can return `{"__skip__": True, "reason": "..."}` to prevent Claude invocation entirely. This is used when a fetcher determines there is nothing to report (e.g., no live match, no new data).

---

## Job Execution Flow

```
APScheduler trigger
    |
    v
1. _execute_job() — overlap check
    |  If another job is running: queue (max 10) or drop
    |
    v
2. Quiet hours check (skip if 23:00-06:00 and no !quiet)
    |
    v
3. Pause check (data/schedule_pauses.json, cached 60s)
    |
    v
4. Pre-fetch data via SKILL_DATA_FETCHERS
    |  Runs async fetcher function if registered for this skill
    |  Check for __skip__ signal (fetcher says don't invoke Claude)
    |  Extract file attachments if present in fetcher response
    |
    v
5. Load SKILL.md from skills/<name>/SKILL.md
    |
    v
6. Build context (current time + skill instructions + pre-fetched data)
    |
    v
7. Invoke Claude Code
    |  JOBS_USE_CHANNEL=1 -> persistent jobs-channel session (HTTP :8103)
    |  JOBS_USE_CHANNEL=0 -> independent CLI process via router_v2
    |  Timeout: 1200 seconds (20 minutes)
    |
    v
8. Validate response
    |  NO_REPLY check -> suppress output, record success
    |  Garbage response detection -> suppress, record failure
    |  Reasoning leak detection -> post fallback warning
    |
    v
9. Post to Discord channel
    |  Attach files if fetcher provided them
    |
    v
10. Post to WhatsApp (if +WhatsApp modifier present)
    |
    v
11. Auto-save to Second Brain (if skill in SECOND_BRAIN_SAVE_SKILLS)
    |
    v
12. Record to job_history.db (execution_id, success, output/error, duration)
    |  On failure: post alert to Discord #alerts webhook
```

### Overlap Prevention

Only one job executes at a time. If a job triggers while another is running:
- Queued up to `MAX_QUEUED_JOBS` (10)
- Processed FIFO after current job completes
- Dropped if queue is full

### NO_REPLY Suppression

Skills can return `NO_REPLY` to suppress Discord output. This counts as a successful execution. Used by conditional skills like `spurs-matchday` (no match today) or `system-health` (all systems green).

### Second Brain Auto-Save

These skills have their output automatically saved to Second Brain after execution:

- `daily-recipes`
- `health-digest`
- `nutrition-summary`
- `weekly-health`
- `morning-briefing`
- `news`
- `youtube-digest`
- `knowledge-digest`

---

## Discord Channel Map

| Channel | Channel ID | Skills |
|---------|-----------|--------|
| **#peterbot** | (env var) | morning-laughs, kids-daily, email-summary, schedule-today, notion-todos, github-activity, cricket-scores, ballot-reminders, healthera-prescriptions, amazon-purchases, hb-full-sync-print, daily-instagram-prep, spurs-matchday, saturday-sport-preview, pl-results, claude-history, property-valuation, pocket-money-weekly, tutor-email-parser, paper-builder, practice-allocate, spelling-test-generator, daily-thoughts, schedule-week, github-weekly, kids-weekly, spurs-live |
| **#food-log** | 1465294449038069912 | hydration, health-digest, nutrition-summary, cooking-reminder, meal-rating, weekly-health, monthly-health, recipe-discovery, price-scanner |
| **#ai-briefings** | 1465277483866788037 | morning-briefing |
| **#news** | 1465277483866788037 | news |
| **#youtube** | 1465277483866788037 | youtube-digest |
| **#alerts** | 1466019126194606286 | system-health, security-monitor, subscription-monitor, self-reflect |
| **#api-costs** | 1465761699582972142 | balance-monitor |
| **#peter-heartbeat** | 1467553740570755105 | heartbeat, morning-quality-report, parser-improve, whatsapp-keepalive |
| **#traffic-reports** | 1466522078462083325 | school-run, school-pickup |
| **#peter-chat** | (separate) | school-weekly-spellings |

---

## Infrastructure Jobs (bot.py, NOT in SCHEDULE.md)

These background jobs are registered directly in `bot.py` using APScheduler, wrapped with `_tracked_job()` for execution tracking and failure alerting. They do not produce Discord messages.

| Job ID | Schedule | Purpose |
|--------|----------|---------|
| `school_daily_sync` | Daily 07:03 UK | Gmail school email parser + Arbor scraper/monitor |
| `school_weekly_sync` | Sat 06:00 UK | Term dates poller + newsletter scraper + calendar sync |
| `energy_daily_sync` | Daily | Energy usage sync |
| `energy_weekly_digest` | Weekly | Energy digest |
| `energy_monthly_billing` | Monthly | Energy billing |
| `whatsapp_web_scrape` | Periodic | WhatsApp web scraping |
| `whatsapp_export_scan` | Periodic | WhatsApp export scanning |
| `incremental_seed` | Periodic | Second Brain incremental seeding |
| `reprocess_pending` | Periodic | Reprocess pending captures |
| `daily_health_check` | Daily | System health check |
| `weekly_health_digest` | Weekly | Aggregated weekly health digest |

---

## Management

### Reload Schedule

After editing SCHEDULE.md, the schedule must be reloaded:

```bash
# Via API
curl -s -X POST http://localhost:8100/schedule/reload

# Via Discord
!reload-schedule
```

The scheduler also watches for a trigger file (`data/schedule_reload.trigger`) every 10 seconds, used by the API to initiate reloads.

### Manual Run

Run any skill on demand:

```bash
# Via API
curl -s -X POST "http://localhost:8100/schedule/run/tutor-email-parser?channel=#peterbot"

# Via Discord
!skill tutor-email-parser
```

Manual runs always bypass quiet hours.

### Schedule Management API

```bash
# List all jobs
GET /schedule/jobs

# Update a job (schedule, channel, or enabled state)
PATCH /schedule/jobs/{skill}
Body: {"schedule": "07:30 UK"} or {"enabled": "no"} or {"channel": "#peterbot+WhatsApp:group"}

# Add a new job
POST /schedule/jobs
Body: {"name": "My Job", "skill": "my-skill", "schedule": "09:00 UK", "channel": "#peterbot"}

# Remove a job
DELETE /schedule/jobs/{skill}

# Read full SCHEDULE.md
GET /schedule

# Write full SCHEDULE.md (triggers reload)
PUT /schedule
Body: {"content": "<full SCHEDULE.md content>", "reason": "Added workout reminder"}
```

### Pause System

Pause jobs without editing SCHEDULE.md. Pauses are stored in `data/schedule_pauses.json` and cached for 60 seconds.

```bash
# Pause specific skills
curl -s -X POST http://localhost:8100/schedule/pauses \
  -H "Content-Type: application/json" \
  -d '{"skills":["hydration","nutrition-summary","cooking-reminder"],"reason":"Holiday","resume_at":"2026-04-03T06:00","paused_by":"chris"}'

# Pause everything
curl -s -X POST http://localhost:8100/schedule/pauses \
  -H "Content-Type: application/json" \
  -d '{"skills":["*"],"reason":"System maintenance","resume_at":"2026-03-28T12:00","paused_by":"chris"}'

# View active pauses
GET /schedule/pauses

# Check if a specific skill is paused
GET /schedule/pauses/check/{skill}

# Resume early (delete pause)
DELETE /schedule/pauses/{id}
```

Pauses auto-expire at their `resume_at` time. The `_is_skill_paused()` method checks pauses before every job execution.

### Job History & Monitoring

```bash
# Health endpoint (aggregates DM SQLite + HB Supabase)
GET /jobs/health?hours=24

# Dashboard: http://localhost:5000 (Peter Dashboard)
```

- **Database**: `peter_dashboard/job_history.db` (SQLite)
- **Recording**: `record_job_start()` and `record_job_complete()` from `peter_dashboard/api/jobs.py`
- **Failure alerting**: `record_job_complete` posts to Discord #alerts webhook on any job failure
- **Health tracker**: `jobs/claude_code_health.py` tracks success rates, durations, garbage responses

### News Deduplication

The `news` skill maintains a 7-day history log at `data/news_history.jsonl`. Previous articles are injected into the skill context to prevent repetition.

---

## Adding a New Scheduled Job

1. **Create the skill**: Copy `skills/_template/SKILL.md` to `skills/<name>/SKILL.md` and fill in instructions
2. **Add a data fetcher** (optional): Write an async function in `data_fetchers.py` and register it in `SKILL_DATA_FETCHERS`
3. **Add to SCHEDULE.md**: Add a row to the Fixed Time or Interval table
4. **Reload**: `POST /schedule/reload` or `!reload-schedule`
5. **Test**: `POST /schedule/run/<skill>?channel=#peterbot` or `!skill <name>`

See `domains/peterbot/wsl_config/BUILDING.md` for the full skill creation guide.
