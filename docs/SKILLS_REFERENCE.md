# Peterbot Skills Reference

Complete reference for all Peter bot skills. Each skill is defined by a `SKILL.md` file in `domains/peterbot/wsl_config/skills/<skill-name>/SKILL.md`.

**Last updated:** 2026-03-27

---

## Summary

| Category | Skills | Scheduled | Conversational |
|----------|--------|-----------|----------------|
| [Hadley Bricks (LEGO Business)](#hadley-bricks-lego-business) | 22 | 6 | 21 |
| [Health & Nutrition](#health--nutrition) | 11 | 8 | 11 |
| [Family & Kids](#family--kids) | 5 | 5 | 5 |
| [Sports & Entertainment](#sports--entertainment) | 9 | 8 | 7 |
| [News & Briefings](#news--briefings) | 8 | 8 | 6 |
| [System & Monitoring](#system--monitoring) | 12 | 10 | 7 |
| [Instagram & Content](#instagram--content) | 5 | 3 | 3 |
| [Education & Learning](#education--learning) | 7 | 7 | 7 |
| [Planning & Productivity](#planning--productivity) | 6 | 1 | 6 |
| [Core Utilities](#core-utilities) | 7 | 0 | 7 |
| [Miscellaneous](#miscellaneous) | 10 | 5 | 7 |
| **Total** | **102** | **61** | **87** |

**Note:** Some skills appear only in SCHEDULE.md (e.g. `hb-orders` at 09:05) but their SKILL.md marks them as both scheduled and conversational. The counts above reflect the SKILL.md definitions. Several additional skills exist as directories (`brickstop-traffic`, `shopping-list-pdf`, `purchase`) that serve niche or legacy purposes.

---

## Skill Architecture

Each skill is defined by a `SKILL.md` file with YAML frontmatter:

```yaml
---
name: skill-name
description: Brief description
trigger:
  - "keyword1"
  - "keyword2"
scheduled: true
conversational: true
channel: "#peterbot"
---
```

**Key concepts:**

- **Conversational** -- Triggered by natural language in Discord or WhatsApp matching the trigger phrases
- **Scheduled** -- Runs on a cron schedule defined in `SCHEDULE.md`
- **Pre-fetched data** -- Data fetchers in `data_fetchers.py` inject data into the skill context before execution
- **NO_REPLY** -- Skills can return `NO_REPLY` to suppress output when there is nothing to report (e.g. no cricket on that day)
- **Channel suffixes** -- `+WhatsApp:chris` (also send to Chris on WhatsApp), `+WhatsApp:group` (also send to family group), `!quiet` (exempt from quiet hours 23:00-06:00)

**Schedule notation:**

| Format | Example | Meaning |
|--------|---------|---------|
| `HH:MM UK` | `08:00 UK` | Daily at 08:00 |
| `Day HH:MM UK` | `Mon 07:30 UK` | Weekly on Monday |
| `Day-Day,Day HH:MM UK` | `Mon-Wed,Fri 08:10 UK` | Specific days |
| `hourly+N UK` | `hourly+3 UK` | Every hour at :03 |
| `half-hourly+N UK` | `half-hourly+1 UK` | Every 30 min at :01/:31 |
| `1st HH:MM UK` | `1st 09:15 UK` | First of month |
| Comma-separated | `08:00,20:00 UK` | Multiple times |

---

## Hadley Bricks (LEGO Business)

22 skills for managing the Hadley Bricks LEGO resale business across Amazon, eBay, BrickLink, and Brick Owl.

| Skill | Purpose | Conv | Sched | Schedule | Channel | Data Sources |
|-------|---------|------|-------|----------|---------|-------------|
| `hb-dashboard` | Daily business KPI overview (P&L, inventory, orders, activity) | YES | YES | 08:00 daily | #peterbot | HB API: P&L, inventory summary, orders, daily activity |
| `hb-add-purchase` | Record LEGO purchase with ASIN lookup and optimal pricing | YES | NO | -- | -- | HB API: batch-import, ASIN lookup, competitive pricing |
| `hb-add-inventory` | Add inventory without purchase (gifts, received items, samples) | YES | NO | -- | -- | HB API: inventory create |
| `hb-eval-purchase` | Evaluate LEGO set resale viability with buy/pass recommendation | YES | NO | -- | -- | HB API: set info, market pricing, fee calculation |
| `hb-set-lookup` | LEGO set info, retired status, Brickset data, market pricing | YES | NO | -- | -- | HB API: Brickset data, Amazon/eBay pricing, stock check |
| `hb-stock-check` | Current stock count for a specific set by condition and location | YES | NO | -- | -- | HB API: inventory search |
| `hb-inventory-status` | Total inventory valuation by condition and platform listing status | YES | NO | -- | -- | HB API: inventory summary, condition breakdown |
| `hb-inventory-aging` | Slow-moving stock analysis grouped by age buckets (30/60/90+ days) | YES | NO | -- | -- | HB API: inventory aging |
| `hb-orders` | Unfulfilled orders needing dispatch, by platform and age | YES | YES | 09:05 daily | #peterbot | HB API: unfulfilled orders |
| `hb-pick-list` | Amazon and eBay picking lists for order fulfillment | YES | YES | 09:05 daily | #peterbot | HB API: picking lists by platform |
| `hb-full-sync-print` | Full platform sync + pick list PDF generation + Discord delivery | YES | YES | 09:35 daily | #peterbot | HB API: sync endpoints, PDF generation |
| `hb-daily-activity` | Listings added, items sold, and revenue for the day | YES | YES | -- | #peterbot | HB API: daily listings, sales |
| `hb-pnl` | Profit & loss by platform and period (today/week/month/year) | YES | NO | -- | -- | HB API: P&L with period presets |
| `hb-platform-performance` | eBay vs Amazon vs BrickLink vs Brick Owl comparison metrics | YES | NO | -- | -- | HB API: per-platform sales, margins, fees, sell-through |
| `hb-purchase-analysis` | ROI analysis by purchase source (Vinted, FB, retail, trade) | YES | NO | -- | -- | HB API: purchases grouped by source |
| `hb-arbitrage` | Profitable LEGO buying opportunities from Vinted scanner | YES | YES | -- | #peterbot | HB API: Vinted scanner opportunities |
| `hb-email-purchases` | Auto-import purchases from Vinted/eBay confirmation emails | YES | YES | -- | #ai-briefings | Gmail API, HB API: batch-import |
| `hb-schedule-pickup` | Schedule a LEGO collection pickup (date, location, seller) | YES | NO | -- | -- | HB API: pickup create |
| `hb-upcoming-pickups` | View scheduled collection pickups with route planning | YES | NO | -- | -- | HB API: pickup list |
| `hb-minifig-removals` | Review and approve cross-platform minifig removal queue | YES | NO | -- | #peter-chat | HB API: `/hb/minifigs/sync/removals` |
| `hb-tasks` | Today's automated workflow tasks (ship, list, reprice, photograph) | YES | NO | -- | -- | HB API: task list |
| `hb-task-complete` | Mark a Hadley Bricks workflow task as complete | YES | NO | -- | -- | HB API: task update |

**Triggers (conversational):**

| Skill | Trigger Phrases |
|-------|-----------------|
| `hb-dashboard` | "business summary", "how's the business", "business health", "bricks dashboard", "hadley bricks" |
| `hb-add-purchase` | "log purchase", "bought", "add purchase", "record purchase", "just bought" |
| `hb-add-inventory` | "add inventory", "add stock", "add to inventory", "received", "got given" |
| `hb-eval-purchase` | "should I buy", "evaluate purchase", "worth it", "good deal", "is this a good buy" |
| `hb-set-lookup` | "look up", "set info", "price check", "what's the price of", "tell me about set" |
| `hb-stock-check` | "how many", "stock of", "do I have", "in stock", "got any", "check stock" |
| `hb-inventory-status` | "inventory status", "stock value", "inventory value", "what's in stock" |
| `hb-inventory-aging` | "slow stock", "aging inventory", "stale items", "old stock", "what's not selling" |
| `hb-orders` | "pending orders", "orders today", "unfulfilled orders", "what orders" |
| `hb-pick-list` | "picking list", "pick list", "what needs shipping", "what needs picking" |
| `hb-full-sync-print` | "full sync", "sync and print", "morning workflow", "print pick lists" |
| `hb-daily-activity` | "daily activity", "what did I list today", "what sold today" |
| `hb-pnl` | "profit and loss", "p&l", "pnl", "how much profit", "profit this month" |
| `hb-platform-performance` | "platform performance", "best platform", "amazon vs ebay", "which platform" |
| `hb-purchase-analysis` | "purchase roi", "best sources", "where should I buy", "sourcing analysis" |
| `hb-arbitrage` | "arbitrage deals", "buying opportunities", "vinted deals", "what should I buy" |
| `hb-email-purchases` | "import purchases from email", "scan purchase emails", "check for new purchases" |
| `hb-schedule-pickup` | "schedule pickup", "book collection", "arrange pickup" |
| `hb-upcoming-pickups` | "upcoming pickups", "collections this week", "scheduled pickups" |
| `hb-minifig-removals` | "minifig removals", "pending removals", "approve removals", "minifig sold" |
| `hb-tasks` | "tasks today", "what needs doing", "bricks tasks", "workflow tasks" |
| `hb-task-complete` | "complete task", "done with", "finished task", "mark complete", "task done" |

---

## Health & Nutrition

11 skills for health tracking, nutrition logging, meal planning, and hydration monitoring. Most data flows through the Hadley API nutrition endpoints and Garmin health data.

| Skill | Purpose | Conv | Sched | Schedule | Channel | Data Sources |
|-------|---------|------|-------|----------|---------|-------------|
| `nutrition-summary` | End-of-day macros, calories, hydration wrap-up vs targets | YES | YES | 21:00 daily | #food-log | Hadley API: `/nutrition/today`, nutrition goals |
| `hydration` | Hourly water intake and step progress check-in with motivation | YES | YES | Hourly 07:02-21:02 | #food-log +WhatsApp:chris | Hadley API: `/nutrition/today` (water_ml, steps) |
| `health-digest` | Morning health summary (sleep, weight, steps, HR, vs yesterday) | YES | YES | 07:55 daily | #food-log | Garmin data via Hadley API |
| `weekly-health` | 7-day health trends with grades and insights | YES | YES | Sunday 09:10 | #food-log | Garmin data, nutrition history |
| `monthly-health` | Monthly health report with long-term trends | YES | YES | 1st 09:15 | #food-log | Garmin data, nutrition history |
| `meal-rating` | Evening prompt to rate dinner meals for feedback loop | YES | YES | 20:30 daily | #food-log | Hadley API: meal plan, meal history |
| `cooking-reminder` | Proactive prep reminders (defrost, marinate, slow cooker) | YES | YES | 07:30, 20:45 daily | #food-log | Hadley API: meal plan, recipe prep steps |
| `daily-recipes` | 5 recipe recommendations matching nutrition targets | YES | YES | 06:30 daily | #food-log | Hadley API: `/nutrition/goals`, recipe search |
| `price-scanner` | Weekly Sainsbury's protein/staple price scan and deal report | YES | YES | Mon 06:00 | #food-log | Hadley API: `/grocery/price-scan` (Sainsbury's scraper) |
| `meal-plan` | View, import, and manage weekly meal plans + shopping lists | YES | NO | -- | -- | Hadley API: `/meal-plan/*`, Google Sheets, Gousto |
| `meal-plan-generator` | Generate balanced weekly plan from templates, preferences, calendar | YES | NO | -- | -- | Hadley API: meal template, preferences, Gousto, Family Fuel DB |

**Triggers (conversational):**

| Skill | Trigger Phrases |
|-------|-----------------|
| `nutrition-summary` | "nutrition summary", "how did i eat today", "macros", "daily summary" |
| `hydration` | "water", "hydration", "how much water", "steps" |
| `health-digest` | "health digest", "morning digest", "how did i sleep", "health summary" |
| `weekly-health` | "weekly summary", "weekly health", "how was my week" |
| `monthly-health` | "monthly summary", "monthly health", "how was my month" |
| `meal-rating` | "rate dinner", "rate that meal", "how was dinner", "that was delicious" |
| `cooking-reminder` | "cooking reminders", "any prep needed", "what needs defrosting" |
| `daily-recipes` | "recipe ideas", "what should I cook", "recipe recommendations" |
| `price-scanner` | "check prices", "what's on offer", "sainsburys deals", "what's cheap this week" |
| `meal-plan` | "meal plan", "what's for dinner", "what's for tea", "import meal plan", "gousto recipes" |
| `meal-plan-generator` | "plan meals", "generate meal plan", "what should we eat this week", "plan dinners" |

---

## Family & Kids

5 skills covering school logistics, kids activities, and family communication. All post to both Discord and WhatsApp family group.

| Skill | Purpose | Conv | Sched | Schedule | Channel | Data Sources |
|-------|---------|------|-------|----------|---------|-------------|
| `kids-daily` | Daily briefing: today/tomorrow activities, kit needed, school notices, spellings | YES | YES | 07:25 daily | #peterbot +WhatsApp:group | Supabase: `evening_clubs`, Google Calendar, school data |
| `kids-weekly` | Weekly kids summary: next week plan (Sun) or last week review (on demand) | YES | YES | Sunday 18:10 | #peterbot +WhatsApp:group | Supabase: `evening_clubs`, Google Calendar |
| `school-run` | Morning school commute traffic with weather and uniform info | YES | YES | Mon-Wed,Fri 08:10; Thu 07:45 | #traffic-reports +WhatsApp:group | Hadley API: Google Maps traffic, weather |
| `school-pickup` | Afternoon pickup traffic with after-school clubs info | YES | YES | Mon,Tue,Thu,Fri 14:55; Wed 16:50 | #traffic-reports +WhatsApp:group | Hadley API: Google Maps traffic, clubs |
| `school-weekly-spellings` | Weekly spelling words for Max and Emmie | YES | YES | Mon 07:30 | #peter-chat +WhatsApp:group | Supabase: spellings DB |

**Triggers (conversational):**

| Skill | Trigger Phrases |
|-------|-----------------|
| `kids-daily` | "kids today", "what are the kids doing", "kids schedule", "kids tomorrow" |
| `kids-weekly` | "kids next week", "kids this week", "kids last week", "weekly kids" |
| `school-run` | "school run", "traffic", "school traffic" |
| `school-pickup` | "school pickup", "pickup", "clubs today" |
| `school-weekly-spellings` | "spellings this week", "spelling words", "what are the spellings" |

---

## Sports & Entertainment

9 skills covering Premier League, Spurs, cricket, ticket ballots, and YouTube content.

| Skill | Purpose | Conv | Sched | Schedule | Channel | Data Sources |
|-------|---------|------|-------|----------|---------|-------------|
| `cricket-scores` | Morning cricket roundup across all major competitions | YES | YES | 08:30 daily | #peterbot +WhatsApp:chris | Football-Data.org API, web search |
| `football-scores` | Live/recent Premier League scores (on demand only) | YES | NO | -- | -- | Football-Data.org API |
| `pl-results` | Morning football results: PL, Champions League, Dover Athletic | YES | YES | 06:05 daily | #peterbot +WhatsApp:chris | Football-Data.org API, web search |
| `ballot-reminders` | Ticket ballot alerts for England Cricket/Football, Oval Invincibles | YES | YES | 09:00 daily | #peterbot +WhatsApp:chris | Gmail: ballot notification emails |
| `spurs-matchday` | Morning heads-up when Spurs have a match today | YES | YES | 08:00 match days | #peterbot +WhatsApp:chris | Football-Data.org API |
| `spurs-match` | On-demand Spurs match info and live score | YES | YES | -- | #peterbot | Football-Data.org API |
| `spurs-live` | Auto-post live Spurs score updates during matches | NO | YES | 10m interval | #peterbot +WhatsApp:chris!quiet | Football-Data.org API |
| `saturday-sport-preview` | Weekend sports preview for the coming week | YES | YES | Sat 08:00 | #peterbot +WhatsApp:chris | Football-Data.org, cricket APIs, F1 schedule, TV listings |
| `youtube-digest` | Daily YouTube video recommendations across interest areas | YES | YES | 09:05 daily | #youtube | Web search, Supabase dedup |

**Triggers (conversational):**

| Skill | Trigger Phrases |
|-------|-----------------|
| `cricket-scores` | "cricket scores", "cricket results", "how did England do", "county cricket" |
| `football-scores` | "football scores", "premier league", "PL scores", "what's the score", "footy" |
| `pl-results` | "PL results", "premier league results", "football results yesterday", "dover results" |
| `ballot-reminders` | "ballot", "ticket ballot", "any ballots open" |
| `spurs-matchday` | "are spurs playing today", "spurs today", "is there a spurs game" |
| `spurs-match` | "spurs score", "tottenham score", "how are spurs doing" |
| `spurs-live` | _(no conversational triggers -- scheduled only)_ |
| `saturday-sport-preview` | "sport this week", "what sport is on", "sport preview", "weekend sport" |
| `youtube-digest` | "youtube", "videos", "anything good on youtube" |

---

## News & Briefings

8 skills for morning information delivery covering AI news, general news, email, calendar, and knowledge base activity.

| Skill | Purpose | Conv | Sched | Schedule | Channel | Data Sources |
|-------|---------|------|-------|----------|---------|-------------|
| `morning-briefing` | AI and Claude news morning briefing | YES | YES | 07:01 daily | #ai-briefings | Web search (X/Twitter, Reddit, tech news) |
| `news` | Personalised news based on preferences and memory context | YES | YES | 07:02 daily | #news | Web search, Second Brain preferences |
| `morning-laughs` | 3 dad jokes and an inspirational quote | YES | YES | 06:30 daily | #peterbot | Generated by Claude |
| `email-summary` | Inbox status: unread count, priority emails, last 24h | YES | YES | 08:02 daily | #peterbot | Hadley API: `/gmail/unread` |
| `schedule-today` | Today's calendar events and agenda | YES | YES | 08:04 daily | #peterbot | Hadley API: `/calendar/today` |
| `schedule-week` | Weekly calendar overview | YES | YES | Sunday 18:00 | #peterbot | Hadley API: `/calendar/week` |
| `knowledge-digest` | Weekly Second Brain activity: saves, connections, fading items | YES | YES | -- | #peterbot | Second Brain digest module |
| `morning-quality-report` | Daily parser quality, regressions, and feedback summary | NO | YES | 06:45 daily | #peter-heartbeat | Parser regression stats, capture store |

**Triggers (conversational):**

| Skill | Trigger Phrases |
|-------|-----------------|
| `morning-briefing` | "ai news", "claude news", "briefing", "ai briefing", "morning briefing" |
| `news` | "news", "headlines", "what's happening", "what's going on" |
| `morning-laughs` | "tell me a joke", "dad joke", "morning laughs" |
| `email-summary` | "emails", "inbox", "any emails", "check email", "email summary" |
| `schedule-today` | "what's on today", "my schedule", "today's calendar", "any meetings today" |
| `schedule-week` | "this week", "week ahead", "upcoming schedule", "what's on this week" |
| `knowledge-digest` | "knowledge digest", "brain digest", "second brain summary" |
| `morning-quality-report` | _(no conversational triggers -- scheduled only)_ |

---

## System & Monitoring

12 skills for system health, API costs, security, and infrastructure monitoring.

| Skill | Purpose | Conv | Sched | Schedule | Channel | Data Sources |
|-------|---------|------|-------|----------|---------|-------------|
| `heartbeat` | Half-hourly health check + Peter queue task processing | NO | YES | Half-hourly :01/:31 | #peter-heartbeat!quiet | Session health, job history, ptasks |
| `balance-monitor` | Hourly API credit balance check with low-balance alerts | YES | YES | Hourly :03 | #api-costs | Anthropic, Moonshot, other API balances |
| `api-usage` | Weekly API usage and cost summary | YES | YES | -- | #api-usage | API usage logs |
| `system-health` | Daily ops report covering all scheduled jobs across both systems | YES | YES | 06:50 daily | #alerts | Hadley API: `/jobs/health` (DM + HB) |
| `security-monitor` | Proactive security monitoring: Supabase, Google, Vercel | YES | YES | 5x daily (06,10,14,18,22) | #alerts | Gmail (security emails), Supabase, Vercel |
| `whatsapp-keepalive` | WhatsApp Evolution API connection health check | NO | YES | 08:00, 20:00 | #peter-heartbeat!quiet | Evolution API connection state |
| `self-reflect` | Review memories and activity to identify proactive tasks | NO | YES | 12:00, 18:00, 23:00 | #alerts!quiet | Recent memories, Second Brain, ptasks |
| `ring-status` | Ring doorbell battery and recent visitor activity | YES | NO | -- | -- | Hadley API: `/ring/status` |
| `ev-charging` | EV battery level, charging status, and readiness | YES | NO | -- | -- | Hadley API: `/ev/combined`, `/kia/status` |
| `subscription-monitor` | Weekly sub health: new subs, price changes, missed payments | YES | YES | Sunday 09:02 | #alerts +WhatsApp:chris | Financial data MCP: recurring transactions |
| `healthera-prescriptions` | Prescription monitoring, ordering, and collection tracking | YES | YES | 09:10 daily | #peterbot | Gmail (Healthera emails), Playwright browser |
| `property-valuation` | Monthly home value estimate using HM Land Registry HPI | YES | YES | 1st 10:15 | #peterbot | HM Land Registry UK HPI data |

**Triggers (conversational):**

| Skill | Trigger Phrases |
|-------|-----------------|
| `heartbeat` | _(no conversational triggers -- scheduled only)_ |
| `balance-monitor` | "balance", "credits", "api balance" |
| `api-usage` | "api usage", "api costs", "how much have i spent" |
| `system-health` | "system health", "job status", "what failed", "ops report" |
| `security-monitor` | "security check", "any security issues", "security alerts", "check security" |
| `whatsapp-keepalive` | _(no conversational triggers -- scheduled only)_ |
| `self-reflect` | _(no conversational triggers -- scheduled only)_ |
| `ring-status` | "ring doorbell", "is anyone at the door", "doorbell battery" |
| `ev-charging` | "car charging", "is the car charging", "battery level", "charge status" |
| `subscription-monitor` | "subscription check", "sub monitor", "subscription health" |
| `healthera-prescriptions` | "prescription", "healthera", "repeat prescription", "order my meds", "sertraline" |
| `property-valuation` | "how much is the house worth", "property value", "house value", "house price" |

---

## Instagram & Content

5 skills for Hadley Bricks Instagram content pipeline: concept generation, image processing, and batch production.

| Skill | Purpose | Conv | Sched | Schedule | Channel | Data Sources |
|-------|---------|------|-------|----------|---------|-------------|
| `daily-instagram-prep` | Source 3 candidate images, optimize for Instagram, post to Discord | NO | YES | 21:05 daily | #peterbot | Unsplash/Pixabay, Instagram photo optimizer |
| `instagram-concepts` | Generate 5 post concepts across content pillars | YES | YES | -- | #peterbot | HB inventory, Instagram analytics, content pillars |
| `instagram-processing` | Process images and write captions for approved concepts | YES | YES | -- | #peterbot | User-provided images, Instagram format optimization |
| `weekly-instagram-batch` | Generate 7 post drafts per week from backlog + inventory | YES | NO | -- | -- | Instagram backlog table, HB inventory |
| `morning-briefing` | _(Also covers AI content trends -- see News & Briefings)_ | -- | -- | -- | -- | -- |

**Note:** The Instagram pipeline flow is: `daily-instagram-prep` (evening) sources images, Chris picks one, then it gets posted the next day. Alternatively, `instagram-concepts` (generate ideas) then `instagram-processing` (create final content) for a two-step workflow.

**Triggers (conversational):**

| Skill | Trigger Phrases |
|-------|-----------------|
| `daily-instagram-prep` | _(scheduled only -- but responds to "instagram prep", "daily instagram")_ |
| `instagram-concepts` | "instagram concepts", "post ideas" |
| `instagram-processing` | "instagram processing", "process instagram", "write captions" |
| `weekly-instagram-batch` | _(triggered via Claude Code skill, not Discord)_ |

---

## Education & Learning

7 skills for managing the children's education: spelling tests, 11+ exam prep, tutor integration, pocket money, and GitHub activity tracking.

| Skill | Purpose | Conv | Sched | Schedule | Channel | Data Sources |
|-------|---------|------|-------|----------|---------|-------------|
| `spelling-test-generator` | Process Max's spelling photo, add to DB, deploy test page | YES | YES | Fri 19:00 | #peterbot +WhatsApp:chris | Image OCR, Hadley API: `/spellings/add`, surge.sh deploy |
| `practice-allocate` | Weekly 11+ Mate practice paper allocation for Emmie and Max | YES | YES | Tue 21:00 | #peterbot | Supabase: `allocate-practice` Edge Function |
| `tutor-email-parser` | Parse tutor emails for topic and homework, update 11+ Mate | YES | YES | Tue 19:00 | #peterbot | Gmail: tutor emails, 11+ Mate API |
| `paper-builder` | Generate missing 11+ practice papers for this week's topic | YES | YES | Tue 19:30 | #peterbot | 11+ Mate: paper counts, topic data, template system |
| `pocket-money-weekly` | Sunday pocket money grid calculation with approval flow | YES | YES | Sunday 09:32 | #peterbot | IHD Dashboard API: `/api/kids/pocket-money/calculate` |
| `github-activity` | Daily GitHub commit and PR summary across all repos | YES | YES | 08:08 daily | #peterbot | GitHub API |
| `github-weekly` | Weekly GitHub activity recap | YES | YES | Sunday 18:05 | #peterbot | GitHub API |

**Education pipeline (Tuesday flow):**
1. `tutor-email-parser` at 19:00 -- parses tutor email, identifies topic
2. `paper-builder` at 19:30 -- generates practice papers for the topic
3. `practice-allocate` at 21:00 -- allocates papers across the week

**Triggers (conversational):**

| Skill | Trigger Phrases |
|-------|-----------------|
| `spelling-test-generator` | "max spellings", "spelling test", "generate spelling test", "spelling photo" |
| `practice-allocate` | "allocate practice", "generate practice week", "11+ mate allocate" |
| `tutor-email-parser` | _(primarily scheduled -- parses tutor email automatically)_ |
| `paper-builder` | "build papers", "generate papers", "make practice papers" |
| `pocket-money-weekly` | "pocket money", "pocket money update", "kids pocket money" |
| `github-activity` | "github activity", "github summary", "what did I commit", "dev activity" |
| `github-weekly` | "weekly dev recap", "weekly github", "week's commits" |

---

## Planning & Productivity

6 skills for task management, trip planning, meal plan configuration, and recipe discovery.

| Skill | Purpose | Conv | Sched | Schedule | Channel | Data Sources |
|-------|---------|------|-------|----------|---------|-------------|
| `notion-todos` | Notion task sync from "Claude Managed To Dos" database | YES | YES | 08:06 daily | #peterbot | Hadley API: `/notion/todos` |
| `notion-ideas` | Browse and add to the "Ideas Backlog" database | YES | NO | -- | -- | Hadley API: `/notion/ideas` |
| `trip-prep` | Consolidated trip preparation: calendar + directions + EV status | YES | NO | -- | -- | Hadley API: calendar, directions, EV status |
| `meal-plan-setup` | Manage weekly meal plan templates, food preferences, staples | YES | NO | -- | -- | Hadley API: meal templates, preferences |
| `recipe-discovery` | Discover 3 new recipes weekly based on ratings and preferences | YES | YES | Sunday 10:00 | #food-log | Family Fuel DB: top recipes, cuisine preferences |
| `paper-builder` | _(See Education & Learning above)_ | -- | -- | -- | -- | -- |

**Triggers (conversational):**

| Skill | Trigger Phrases |
|-------|-----------------|
| `notion-todos` | "my todos", "task list", "what's on my plate", "pending tasks" |
| `notion-ideas` | "ideas backlog", "my ideas", "idea list", "show ideas" |
| `trip-prep` | "trip prep", "am I ready for [place]", "trip to [place]" |
| `meal-plan-setup` | "set up meal template", "food preferences", "disliked ingredients", "shopping staples" |
| `recipe-discovery` | "find new recipes", "recipe ideas", "suggest recipes", "new dinner ideas" |

---

## Core Utilities

7 general-purpose skills for browser automation, navigation, file management, email, reminders, calendar, and weather.

| Skill | Purpose | Conv | Sched | Schedule | Channel | Data Sources |
|-------|---------|------|-------|----------|---------|-------------|
| `chrome-cdp` | Browser automation via Chrome DevTools Protocol (navigate, click, scrape, screenshot) | YES | NO | -- | -- | Chrome CDP on port 9222 |
| `directions` | Route planning with travel time via Google Maps | YES | NO | -- | -- | Hadley API: `/directions` (Google Maps) |
| `drive-search` | Google Drive read/write: search, create, share, move, copy, rename | YES | NO | -- | -- | Hadley API: `/drive/*` |
| `email-search` | Gmail search by sender, subject, or content | YES | NO | -- | -- | Hadley API: `/gmail/search` |
| `remind` | Set, list, update, and cancel reminders | YES | NO | -- | #peterbot | Hadley API: `/reminders` (Supabase storage) |
| `find-free-time` | Calendar free slot finder for scheduling | YES | NO | -- | -- | Hadley API: `/calendar/free` |
| `weather` / `weather-forecast` | Current conditions and multi-day forecast for Tonbridge | YES | NO | -- | -- | Hadley API: `/weather/current`, `/weather/forecast` |

**Triggers (conversational):**

| Skill | Trigger Phrases |
|-------|-----------------|
| `chrome-cdp` | "check this page", "open chrome", "browse to", "screenshot this", "scrape this page", "track my parcel" |
| `directions` | "directions to [place]", "how do I get to [place]", "how long to [place]" |
| `drive-search` | "find document", "search drive", "save to drive", "create a doc", "recent files" |
| `email-search` | "find email from [person]", "email about [topic]", "search emails" |
| `remind` | "remind me", "set a reminder", "list reminders", "cancel reminder", "/remind" |
| `find-free-time` | "when am I free", "find time for", "free slots", "available times" |
| `weather` | "weather", "is it raining", "temperature", "do I need an umbrella" |
| `weather-forecast` | "forecast", "weather this week", "weather tomorrow", "will it rain on Saturday" |

---

## Miscellaneous

10 skills covering Amazon order tracking, daily thoughts capture, traffic, parser optimization, Japan travel, grocery shopping, Vinted tracking, shopping lists, and product purchasing.

| Skill | Purpose | Conv | Sched | Schedule | Channel | Data Sources |
|-------|---------|------|-------|----------|---------|-------------|
| `amazon-purchases` | Sync Amazon purchase history from Gmail confirmation emails | YES | YES | 09:30 daily | #peterbot | Gmail: Amazon order emails, Second Brain |
| `daily-thoughts` | End-of-day email digest of thoughts captured during the day | NO | YES | 21:45 daily | #peterbot!quiet | Buffer file, Hadley API: `/gmail/send` |
| `traffic-check` | Real-time traffic conditions for the school run | YES | NO | -- | -- | Hadley API: `/traffic/school` |
| `parser-improve` | Nightly parser optimization cycle (review, plan, implement, validate) | NO | YES | 02:00 daily | #peter-heartbeat!quiet | Parser captures, fixtures, feedback |
| `osaka-mint-check` | Monitor Osaka Mint Bureau cherry blossom reservation opening | NO | YES | -- | #peterbot +WhatsApp:chris | Web search (Osaka Mint website) |
| `grocery-shop` | Add shopping list to Sainsbury's trolley + book delivery slot | YES | NO | -- | -- | Hadley API: meal plan ingredients, Chrome CDP (Sainsbury's) |
| `vinted-collections` | Track Vinted parcels ready to collect from pickup points | YES | NO | -- | -- | Gmail: Vinted collection emails |
| `shopping-list-pdf` | Generate printable A4 shopping list PDF with categories | YES | NO | -- | -- | Hadley API: PDF generator, Google Drive |
| `purchase` | Find products and provide direct purchase/add-to-cart links | YES | NO | -- | -- | Gmail (past orders), Amazon/eBay search |
| `brickstop-traffic` | One-time traffic update for Brickstop Cafe trip (legacy) | NO | NO | -- | -- | Hadley API: `/directions` |

**Triggers (conversational):**

| Skill | Trigger Phrases |
|-------|-----------------|
| `amazon-purchases` | "what have I bought on amazon", "amazon purchases", "amazon orders" |
| `daily-thoughts` | _(scheduled only -- buffer populated by "put that in the email")_ |
| `traffic-check` | "traffic", "how's the traffic", "should I leave now" |
| `parser-improve` | _(no conversational triggers -- nightly automated cycle)_ |
| `osaka-mint-check` | "osaka mint", "cherry blossom registration" |
| `grocery-shop` | "do the shopping", "add shopping list to sainsburys", "book a delivery", "do the sainsburys" |
| `vinted-collections` | "vinted collections", "ready to collect", "check vinted", "any parcels to collect" |
| `shopping-list-pdf` | "shopping list", "grocery list", "printable list", "print shopping list" |
| `purchase` | "buy", "purchase", "order from amazon", "buy packaging", "order supplies" |
| `brickstop-traffic` | _(legacy one-time skill -- no active triggers)_ |

---

## Daily Schedule Timeline

Complete view of all scheduled skills in chronological order for a typical weekday.

| Time | Skill | Channel |
|------|-------|---------|
| 02:00 | `parser-improve` | #peter-heartbeat!quiet |
| 06:05 | `pl-results` | #peterbot +WhatsApp:chris |
| 06:30 | `morning-laughs` | #peterbot |
| 06:30 | `daily-recipes` | #food-log |
| 06:45 | `morning-quality-report` | #peter-heartbeat |
| 06:50 | `system-health` | #alerts |
| 07:01 | `morning-briefing` | #ai-briefings |
| 07:02 | `news` | #news |
| 07:02 | `hydration` _(first of 15)_ | #food-log +WhatsApp:chris |
| 07:25 | `kids-daily` | #peterbot +WhatsApp:group |
| 07:30 | `cooking-reminder` _(morning)_ | #food-log |
| 07:55 | `health-digest` | #food-log |
| 08:00 | `spurs-matchday` _(match days only)_ | #peterbot +WhatsApp:chris |
| 08:00 | `whatsapp-keepalive` | #peter-heartbeat!quiet |
| 08:02 | `email-summary` | #peterbot |
| 08:04 | `schedule-today` | #peterbot |
| 08:06 | `notion-todos` | #peterbot |
| 08:08 | `github-activity` | #peterbot |
| 08:10 | `school-run` _(Mon-Wed,Fri)_ | #traffic-reports +WhatsApp:group |
| 08:30 | `cricket-scores` | #peterbot +WhatsApp:chris |
| 09:00 | `ballot-reminders` | #peterbot +WhatsApp:chris |
| 09:05 | `youtube-digest` | #youtube |
| 09:10 | `healthera-prescriptions` | #peterbot |
| 09:30 | `amazon-purchases` | #peterbot |
| 09:35 | `hb-full-sync-print` | #peterbot |
| 12:00 | `self-reflect` | #alerts!quiet |
| 14:55 | `school-pickup` _(Mon,Tue,Thu,Fri)_ | #traffic-reports +WhatsApp:group |
| 18:00 | `self-reflect` | #alerts!quiet |
| 20:00 | `whatsapp-keepalive` | #peter-heartbeat!quiet |
| 20:30 | `meal-rating` | #food-log |
| 20:45 | `cooking-reminder` _(evening)_ | #food-log |
| 21:00 | `nutrition-summary` | #food-log |
| 21:02 | `hydration` _(last of 15)_ | #food-log +WhatsApp:chris |
| 21:05 | `daily-instagram-prep` | #peterbot |
| 21:45 | `daily-thoughts` | #peterbot!quiet |
| 23:00 | `self-reflect` | #alerts!quiet |

**Recurring intervals:**

| Interval | Skill | Channel |
|----------|-------|---------|
| Every 30 min (:01/:31) | `heartbeat` | #peter-heartbeat!quiet |
| Every hour (:03) | `balance-monitor` | #api-costs |
| Every 10 min | `spurs-live` _(match days only)_ | #peterbot +WhatsApp:chris!quiet |
| 5x daily (06,10,14,18,22) | `security-monitor` | #alerts |

**Day-specific schedules:**

| Day | Time | Skill | Channel |
|-----|------|-------|---------|
| Monday | 06:00 | `price-scanner` | #food-log |
| Monday | 07:30 | `school-weekly-spellings` | #peter-chat +WhatsApp:group |
| Tuesday | 19:00 | `tutor-email-parser` | #peterbot |
| Tuesday | 19:30 | `paper-builder` | #peterbot |
| Tuesday | 21:00 | `practice-allocate` | #peterbot |
| Thursday | 07:45 | `school-run` _(early start)_ | #traffic-reports +WhatsApp:group |
| Wednesday | 16:50 | `school-pickup` _(late pickup)_ | #traffic-reports +WhatsApp:group |
| Friday | 19:00 | `spelling-test-generator` | #peterbot +WhatsApp:chris |
| Saturday | 08:00 | `saturday-sport-preview` | #peterbot +WhatsApp:chris |
| Sunday | 09:02 | `subscription-monitor` | #alerts +WhatsApp:chris |
| Sunday | 09:10 | `weekly-health` | #food-log |
| Sunday | 09:32 | `pocket-money-weekly` | #peterbot |
| Sunday | 10:00 | `recipe-discovery` | #food-log |
| Sunday | 18:00 | `schedule-week` | #peterbot |
| Sunday | 18:05 | `github-weekly` | #peterbot |
| Sunday | 18:10 | `kids-weekly` | #peterbot +WhatsApp:group |
| 1st of month | 09:15 | `monthly-health` | #food-log |
| 1st of month | 10:15 | `property-valuation` | #peterbot |

---

## Discord Channel Map

Which skills post to which Discord channels.

| Channel | Skills |
|---------|--------|
| `#peterbot` | hb-dashboard, hb-orders, hb-pick-list, hb-full-sync-print, hb-daily-activity, kids-daily, kids-weekly, morning-laughs, email-summary, schedule-today, schedule-week, notion-todos, knowledge-digest, amazon-purchases, daily-instagram-prep, instagram-concepts, instagram-processing, github-activity, github-weekly, spelling-test-generator, practice-allocate, paper-builder, pocket-money-weekly, healthera-prescriptions, property-valuation, daily-thoughts, remind, hb-dashboard |
| `#food-log` | nutrition-summary, hydration, health-digest, weekly-health, monthly-health, meal-rating, cooking-reminder, daily-recipes, price-scanner, recipe-discovery |
| `#traffic-reports` | school-run, school-pickup |
| `#ai-briefings` | morning-briefing, hb-email-purchases |
| `#news` | news |
| `#youtube` | youtube-digest |
| `#alerts` | system-health, security-monitor, self-reflect, subscription-monitor |
| `#api-costs` | balance-monitor |
| `#api-usage` | api-usage |
| `#peter-heartbeat` | heartbeat, morning-quality-report, whatsapp-keepalive |
| `#peter-chat` | school-weekly-spellings, hb-minifig-removals |

---

## File Locations

| File | Purpose |
|------|---------|
| `domains/peterbot/wsl_config/skills/<name>/SKILL.md` | Skill definition and instructions |
| `domains/peterbot/wsl_config/skills/manifest.json` | Auto-generated skill index with triggers |
| `domains/peterbot/wsl_config/SCHEDULE.md` | Cron/interval job schedule |
| `domains/peterbot/wsl_config/data_fetchers.py` | Pre-fetch data functions for skills |
| `domains/peterbot/wsl_config/skills/_template/SKILL.md` | Template for creating new skills |
