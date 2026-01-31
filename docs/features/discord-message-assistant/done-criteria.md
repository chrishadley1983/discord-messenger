# Done Criteria: discord-message-assistant

**Created:** 2026-01-29
**Author:** Define Done Agent + Chris
**Status:** APPROVED
**Project:** Discord Personal Assistant (new project)
**Location:** `C:\Users\Chris Hadley\Discord-Messenger`

## Feature Summary

A modular Discord bot with AI coaching/assistance via Claude API. Routes messages to domain handlers based on channel, each with its own system prompt, tools, and scheduled tasks. Includes 3 domains (Nutrition, News, API Usage) plus 3 scheduled jobs (AI Morning Briefing, API Balance Monitoring, School Run Traffic Report). Runs as a background Windows process with file logging.

---

## Success Criteria

### Core Framework

#### CF1: Bot Connects to Discord
- **Tag:** AUTO_VERIFY
- **Criterion:** Bot successfully connects to Discord and reports "Logged in as {bot.user}" in logs
- **Evidence:** Log file contains connection success message within 30 seconds of startup
- **Test:** Start bot, parse log file for "Logged in as" within timeout

#### CF2: Domain Registry Routes Messages
- **Tag:** AUTO_VERIFY
- **Criterion:** Messages sent to registered channels are routed to the correct domain handler
- **Evidence:** Mock message to nutrition channel triggers NutritionDomain.handle()
- **Test:** Integration test with mocked Discord client, verify domain.handle() called

#### CF3: Claude Client Handles Tool-Use Loop
- **Tag:** AUTO_VERIFY
- **Criterion:** ClaudeClient executes multi-turn tool calls until final text response
- **Evidence:** Given a message requiring 2 tool calls, both tools execute and final response returned
- **Test:** Integration test with mocked Anthropic API returning tool_use blocks

#### CF4: Scheduler Runs Cron Tasks
- **Tag:** AUTO_VERIFY
- **Criterion:** APScheduler triggers registered tasks at configured times (within 2 minutes tolerance)
- **Evidence:** Scheduled task executes and logs within 2 minutes of scheduled time
- **Test:** Register task for 1 minute in future, verify execution logged

#### CF5: Background Running with File Logging
- **Tag:** AUTO_VERIFY
- **Criterion:** Bot runs via pythonw.exe without visible console, logs to dated file in AppData
- **Evidence:** Log file exists at `%LOCALAPPDATA%\discord-assistant\logs\YYYY-MM-DD.log`
- **Test:** Start via pythonw.exe, verify log file created and contains entries

#### CF6: Windows Startup Task
- **Tag:** AUTO_VERIFY
- **Criterion:** Windows Task Scheduler task exists to start bot on user login
- **Evidence:** `schtasks /query /tn "DiscordAssistant"` returns task details
- **Test:** Query task scheduler, verify task exists with correct trigger

#### CF7: Unregistered Channel Ignored
- **Tag:** AUTO_VERIFY
- **Criterion:** Messages in channels not mapped to a domain are silently ignored (no response, no error)
- **Evidence:** Message to unmapped channel produces no bot response and no error log
- **Test:** Send message to unmapped channel, verify no response and clean logs

---

### Nutrition Domain

#### ND1: log_meal Tool Inserts Record
- **Tag:** AUTO_VERIFY
- **Criterion:** `log_meal` tool inserts meal record to Supabase `nutrition_logs` table with all fields
- **Evidence:** Record exists in DB with matching meal_type, description, calories, protein_g, carbs_g, fat_g
- **Test:** Call tool, query Supabase, verify record

#### ND2: log_water Tool Inserts Record
- **Tag:** AUTO_VERIFY
- **Criterion:** `log_water` tool inserts water record to Supabase with water_ml field
- **Evidence:** Record exists in DB with meal_type='water' and correct water_ml value
- **Test:** Call tool with 500ml, query DB, verify record

#### ND3: get_today_totals Returns Aggregated Data
- **Tag:** AUTO_VERIFY
- **Criterion:** `get_today_totals` returns sum of calories, protein_g, carbs_g, fat_g, water_ml for today
- **Evidence:** Response contains correct totals matching DB aggregation
- **Test:** Insert known test records, call tool, verify totals match expected sums

#### ND4: get_today_meals Returns Meal List
- **Tag:** AUTO_VERIFY
- **Criterion:** `get_today_meals` returns list of meals (excluding water) logged today, ordered by time
- **Evidence:** Response contains array of meal objects with correct fields
- **Test:** Insert test meals, call tool, verify list matches inserted records

#### ND5: get_steps Fetches Garmin Data
- **Tag:** AUTO_VERIFY
- **Criterion:** `get_steps` returns today's step count from Garmin Connect API
- **Evidence:** Response contains `steps` (number), `goal` (number), `percentage` (number)
- **Test:** Integration test with mocked Garmin API response

#### ND6: get_weight Fetches Withings Data
- **Tag:** AUTO_VERIFY
- **Criterion:** `get_weight` returns latest weight from Withings API with auto token refresh
- **Evidence:** Response contains `weight_kg` (number) and `date` (ISO string)
- **Test:** Integration test with mocked Withings API response

#### ND7: Withings Token Auto-Refresh
- **Tag:** AUTO_VERIFY
- **Criterion:** When Withings returns status != 0 (expired token), system refreshes token and retries once
- **Evidence:** Log shows "Refreshing Withings token" followed by successful retry
- **Test:** Mock expired token response, verify refresh called, verify retry succeeds

#### ND8: get_week_summary Returns 7-Day Totals
- **Tag:** AUTO_VERIFY
- **Criterion:** `get_week_summary` returns daily totals for past 7 days via Supabase RPC
- **Evidence:** Response contains array of 7 daily total objects
- **Test:** Call tool, verify response structure and date range

#### ND9: Daily Summary Posts at 9pm UK
- **Tag:** AUTO_VERIFY
- **Criterion:** Scheduled task posts nutrition summary to #food-log channel at 21:00 Europe/London
- **Evidence:** Discord message posted to correct channel within 2 minutes of 21:00 UK time
- **Test:** Mock time to 20:59 UK, advance to 21:00, verify message posted

#### ND10: Daily Summary Format
- **Tag:** AUTO_VERIFY
- **Criterion:** Daily summary contains all metrics with emoji indicators (✅ >=90%, 🟡 70-89%, ❌ <70%)
- **Evidence:** Message contains calories, protein, carbs, fat, water, steps with correct emoji per threshold
- **Test:** Parse posted message, verify all fields present with correct emoji logic

#### ND11: Nutrition Channel ID Configured
- **Tag:** AUTO_VERIFY
- **Criterion:** Nutrition domain is registered to channel ID 1465294449038069912
- **Evidence:** `registry.get_by_channel(1465294449038069912)` returns NutritionDomain
- **Test:** Query registry, verify domain returned

---

### News Domain

#### NW1: get_headlines Fetches RSS Feeds
- **Tag:** AUTO_VERIFY
- **Criterion:** `get_headlines` returns headlines from configured RSS feeds by category (tech, uk, f1, all)
- **Evidence:** Response contains array of headline objects with title, url, source
- **Test:** Call tool with category='tech', verify response contains HN and Ars Technica items

#### NW2: read_article Fetches Content
- **Tag:** AUTO_VERIFY
- **Criterion:** `read_article` fetches article URL and returns extracted text content
- **Evidence:** Response contains article text (not HTML tags)
- **Test:** Call tool with known URL, verify text content returned

#### NW3: Morning Briefing Posts at 7am UK
- **Tag:** AUTO_VERIFY
- **Criterion:** Scheduled task posts news briefing to #news channel at 07:00 Europe/London
- **Evidence:** Discord message posted to correct channel within 2 minutes of 07:00 UK time
- **Test:** Mock time advancement, verify message posted

#### NW4: Morning Briefing Contains Headlines
- **Tag:** AUTO_VERIFY
- **Criterion:** Morning briefing contains top 5 headlines across tech, UK, F1 categories
- **Evidence:** Message contains at least 5 headline items with sources
- **Test:** Parse posted message, count headline items

---

### API Usage Domain

#### AU1: get_anthropic_usage Returns Spend Data
- **Tag:** AUTO_VERIFY
- **Criterion:** `get_anthropic_usage` returns Claude API spend for specified period (default 7 days)
- **Evidence:** Response contains total_cost, breakdown by model, date range
- **Test:** Integration test with mocked Anthropic usage API

#### AU2: get_openai_usage Returns Spend Data
- **Tag:** AUTO_VERIFY
- **Criterion:** `get_openai_usage` returns OpenAI API spend for specified period
- **Evidence:** Response contains total_cost, breakdown by model, date range
- **Test:** Integration test with mocked OpenAI usage API

#### AU3: Weekly Summary Posts
- **Tag:** AUTO_VERIFY
- **Criterion:** Scheduled task posts API usage summary to #api-usage channel weekly
- **Evidence:** Discord message posted containing spend totals for both APIs
- **Test:** Mock weekly trigger, verify message posted with spend data

---

### AI Morning Briefing (Scheduled Job)

#### MB1: Runs at 6:30 AM UTC Daily
- **Tag:** AUTO_VERIFY
- **Criterion:** Job triggers at 06:30 UTC every day
- **Evidence:** Log shows job execution starting within 2 minutes of 06:30 UTC
- **Test:** Mock time to 06:29 UTC, advance, verify execution logged

#### MB2: Posts to #ai-briefings Channel
- **Tag:** AUTO_VERIFY
- **Criterion:** Briefing message posted to Discord channel ID 1465277483866788037
- **Evidence:** Discord API call targets correct channel ID
- **Test:** Verify message send call uses correct channel

#### MB3: Contains 4 Sections
- **Tag:** AUTO_VERIFY
- **Criterion:** Briefing contains: News Headlines, Community Buzz, Moltbot Corner, Video of the Day
- **Evidence:** Message contains section headers for all 4 sections
- **Test:** Parse message, verify all section headers present

#### MB4: News Headlines Section
- **Tag:** AUTO_VERIFY
- **Criterion:** News section contains 3-5 Claude/Anthropic stories + 3-5 broader AI stories, each with link
- **Evidence:** Section contains 6-10 items, each with `<https://...>` URL
- **Test:** Parse section, count items, verify URLs present

#### MB5: Community Buzz Uses xAI Grok
- **Tag:** AUTO_VERIFY
- **Criterion:** Community buzz section fetches X/Reddit data via xAI Grok API
- **Evidence:** API call made to Grok endpoint with correct auth header
- **Test:** Integration test verifying Grok API called

#### MB6: Every Item Has Link
- **Tag:** AUTO_VERIFY
- **Criterion:** Every story/mention in briefing includes a clickable link
- **Evidence:** Regex `<https?://[^>]+>` matches for every bullet item
- **Test:** Parse all items, verify each has URL pattern

#### MB7: Discord Formatting
- **Tag:** AUTO_VERIFY
- **Criterion:** Message uses Discord formatting: `>` blockquotes, `**bold**`, `<url>` wrapped links
- **Evidence:** Message contains blockquote markers and properly wrapped URLs
- **Test:** Verify message syntax matches Discord markdown

---

### API Balance Monitoring (Scheduled Job)

#### BM1: Runs Hourly at Top of Hour
- **Tag:** AUTO_VERIFY
- **Criterion:** Job triggers at minute 0 of every hour UTC
- **Evidence:** Log shows execution at HH:00 (within 2 minutes)
- **Test:** Mock time advancement to hour boundary, verify execution

#### BM2: Posts to #peter-chat Channel
- **Tag:** AUTO_VERIFY
- **Criterion:** Balance summary posted to Discord channel ID 1415741789758816369
- **Evidence:** Discord API call targets correct channel ID
- **Test:** Verify message send call uses correct channel

#### BM3: Queries Claude Balance from Supabase
- **Tag:** AUTO_VERIFY
- **Criterion:** Job queries `claude_api_usage` table for latest available_balance
- **Evidence:** Supabase query executed, balance value extracted
- **Test:** Integration test with mocked Supabase response

#### BM4: Queries Moonshot Kimi via REST
- **Tag:** AUTO_VERIFY
- **Criterion:** Job calls `https://api.moonshot.ai/v1/users/me/balance` with auth header
- **Evidence:** HTTP request made to correct endpoint with Authorization header
- **Test:** Integration test verifying API call made

#### BM5: Combined Message Format
- **Tag:** AUTO_VERIFY
- **Criterion:** Message shows both balances: "💳 Claude: $X.XX" and "🌙 Kimi: $X.XX available"
- **Evidence:** Message contains both emoji-prefixed balance lines
- **Test:** Parse message, verify both balances present

#### BM6: Low Balance Alert
- **Tag:** AUTO_VERIFY
- **Criterion:** If either balance < $5.00, emoji changes to ⚠️ and message includes alert
- **Evidence:** When balance < 5, message contains ⚠️ instead of normal emoji
- **Test:** Mock low balance, verify alert emoji in message

#### BM7: Logs to Balance Files
- **Tag:** AUTO_VERIFY
- **Criterion:** Both balances logged to respective files with timestamp
- **Evidence:** Files exist at configured paths with timestamped entries
- **Test:** Run job, verify log files contain new entries

---

### School Run Traffic Report (Scheduled Job)

#### SR1: Runs 8:15 AM UK Weekdays Only
- **Tag:** AUTO_VERIFY
- **Criterion:** Job triggers at 08:15 Europe/London on Monday-Friday only
- **Evidence:** Log shows execution on weekdays, no execution on Saturday/Sunday
- **Test:** Mock time to weekend 08:15, verify no execution; mock weekday, verify execution

#### SR2: Sends via Twilio WhatsApp
- **Tag:** AUTO_VERIFY
- **Criterion:** Report sent via Twilio WhatsApp API to both recipients
- **Evidence:** Twilio API calls made to +447856182831 (Abby) and +447855620978 (Chris)
- **Test:** Integration test verifying Twilio API called with correct numbers

#### SR3: Real Traffic from Google Maps API
- **Tag:** AUTO_VERIFY
- **Criterion:** Traffic data fetched from Google Maps Directions API (not scraped/hallucinated)
- **Evidence:** API call to maps.googleapis.com/maps/api/directions with origin/destination
- **Test:** Verify API request made with correct parameters

#### SR4: Traffic Data Contains Required Fields
- **Tag:** AUTO_VERIFY
- **Criterion:** Traffic response includes: duration_in_minutes, route_name, traffic_condition
- **Evidence:** Parsed response contains all three fields with valid values
- **Test:** Verify response parsing extracts all fields

#### SR5: Real Weather from Open-Meteo
- **Tag:** AUTO_VERIFY
- **Criterion:** Weather fetched from Open-Meteo API for Tonbridge coordinates (51.1833, 0.2833)
- **Evidence:** API call to api.open-meteo.com with correct lat/long
- **Test:** Verify API request parameters

#### SR6: Weather Data Contains Required Fields
- **Tag:** AUTO_VERIFY
- **Criterion:** Weather includes: low_temp, high_temp, precipitation_probability, condition
- **Evidence:** Parsed response contains all fields with numeric values
- **Test:** Verify response parsing

#### SR7: Max Uniform Rules Applied
- **Tag:** AUTO_VERIFY
- **Criterion:** Max's uniform: PE kit on Tuesday & Thursday, school uniform otherwise
- **Evidence:** Tuesday/Thursday messages say "PE kit needed", other days say "School uniform ✅"
- **Test:** Run for each weekday, verify correct uniform text

#### SR8: Emmie Uniform Rules Applied
- **Tag:** AUTO_VERIFY
- **Criterion:** Emmie's uniform: PE kit Wed/Fri, Gymnastics kit Thu, school uniform otherwise
- **Evidence:** Correct kit text for each day of week
- **Test:** Run for each weekday, verify correct uniform text

#### SR9: Leave Time Calculation
- **Tag:** AUTO_VERIFY
- **Criterion:** Leave time = current time + ETA + 2 minutes, formatted as "Leave by H:MM to arrive 8:38"
- **Evidence:** If ETA is 4 mins at 8:15, leave time shows 8:34 (8:38 - 4)
- **Test:** Mock ETA values, verify calculated leave time

#### SR10: WhatsApp Formatting
- **Tag:** AUTO_VERIFY
- **Criterion:** Message uses WhatsApp markdown (*bold* not **bold**), no Discord-style headers
- **Evidence:** Message contains `*text*` for bold, no `**` or `#` markdown
- **Test:** Regex verify WhatsApp-compatible formatting

---

### Error Handling

#### EH1: Supabase Unavailable Response
- **Tag:** AUTO_VERIFY
- **Criterion:** When Supabase connection fails, bot responds "Database unavailable, try again shortly"
- **Evidence:** Error caught, user-friendly message returned (not stack trace)
- **Test:** Mock Supabase timeout, verify response message

#### EH2: Garmin API Failure Graceful
- **Tag:** AUTO_VERIFY
- **Criterion:** When Garmin API fails, nutrition data still returns with steps marked unavailable
- **Evidence:** Response contains nutrition totals + `steps: { error: "...", steps: null }`
- **Test:** Mock Garmin failure, verify partial response

#### EH3: Claude API Failure Response
- **Tag:** AUTO_VERIFY
- **Criterion:** When Claude API fails, bot responds "AI unavailable, try again shortly"
- **Evidence:** Error caught, user-friendly message returned
- **Test:** Mock Anthropic API error, verify response

#### EH4: Unknown Tool Returns Error
- **Tag:** AUTO_VERIFY
- **Criterion:** When Claude requests unknown tool, error returned in tool_result for graceful recovery
- **Evidence:** Tool result contains `{ error: "Unknown tool: xyz" }`
- **Test:** Mock unknown tool request, verify error in result

#### EH5: Twilio Failure Logged
- **Tag:** AUTO_VERIFY
- **Criterion:** When WhatsApp send fails, error logged but job doesn't crash
- **Evidence:** Log contains Twilio error, job completes (doesn't throw)
- **Test:** Mock Twilio failure, verify error logged, job continues

#### EH6: Google Maps API Failure Fallback
- **Tag:** AUTO_VERIFY
- **Criterion:** When Google Maps API fails, report states "Traffic data unavailable" instead of crashing
- **Evidence:** Message contains fallback text, job completes
- **Test:** Mock API failure, verify fallback message

---

### Performance

#### PF1: Message Response Time
- **Tag:** AUTO_VERIFY
- **Criterion:** Bot responds to messages within 15 seconds (excluding Claude API latency edge cases)
- **Evidence:** Time from message received to response sent < 15000ms
- **Test:** Send test message, measure response time

#### PF2: Startup Time
- **Tag:** AUTO_VERIFY
- **Criterion:** Bot is ready (connected, domains registered) within 30 seconds of launch
- **Evidence:** "Logged in" message appears in log within 30 seconds
- **Test:** Start bot, measure time to ready

#### PF3: Scheduled Task Tolerance
- **Tag:** AUTO_VERIFY
- **Criterion:** Scheduled tasks execute within 2 minutes of configured time
- **Evidence:** Actual execution time is within 120 seconds of scheduled time
- **Test:** Log scheduled vs actual execution times

---

### Integration Tests

#### IT1: Happy Path Message Flow
- **Tag:** AUTO_VERIFY
- **Criterion:** Test covers: message received → domain routed → Claude called → tool executed → response sent
- **Evidence:** Integration test exists and passes with mocked Discord/Claude
- **Test:** `pytest tests/integration/test_message_flow.py`

#### IT2: Tool Call Round-Trip
- **Tag:** AUTO_VERIFY
- **Criterion:** Test covers multi-turn tool use: message → tool_use response → tool execution → final response
- **Evidence:** Integration test with 2+ tool calls passes
- **Test:** `pytest tests/integration/test_tool_calls.py`

#### IT3: Error Scenario Coverage
- **Tag:** AUTO_VERIFY
- **Criterion:** Tests exist for: Supabase failure, Garmin failure, Withings token refresh, Claude failure
- **Evidence:** 4+ error scenario tests exist and pass
- **Test:** `pytest tests/integration/test_error_scenarios.py`

#### IT4: Scheduled Task Firing
- **Tag:** AUTO_VERIFY
- **Criterion:** Test covers scheduled task registration and execution with mocked time
- **Evidence:** Integration test verifies task fires at correct time
- **Test:** `pytest tests/integration/test_schedules.py`

#### IT5: Withings Token Refresh Flow
- **Tag:** AUTO_VERIFY
- **Criterion:** Test covers: expired token → refresh request → retry with new token → success
- **Evidence:** Integration test mocks full refresh flow
- **Test:** `pytest tests/integration/test_withings_refresh.py`

---

## Out of Scope

- Mobile app (Discord bot only)
- Web dashboard
- Multi-user support (personal use only)
- Database migrations (nutrition_logs table already exists)
- Conversation history/context (each message is stateless)
- Voice channel integration
- Slash commands (message-based only)
- Rate limiting (personal use, low volume)

## Dependencies

- Discord bot token and channel access
- Anthropic API key (Claude Haiku 4.5)
- Supabase project with `nutrition_logs` table and `get_daily_totals` function
- Garmin Connect credentials
- Withings OAuth credentials (client ID, secret, tokens)
- xAI Grok API key
- Moonshot Kimi API key
- Google Maps Directions API key
- Open-Meteo API (no key required)
- Twilio account with WhatsApp Business API

## Environment Variables Required

```
# Discord
DISCORD_TOKEN=

# Claude API
ANTHROPIC_API_KEY=

# Supabase
SUPABASE_URL=
SUPABASE_KEY=

# Garmin
GARMIN_EMAIL=
GARMIN_PASSWORD=

# Withings
WITHINGS_CLIENT_ID=
WITHINGS_CLIENT_SECRET=
WITHINGS_ACCESS_TOKEN=
WITHINGS_REFRESH_TOKEN=

# OpenAI (for API usage tracking)
OPENAI_API_KEY=

# xAI Grok (for morning briefing)
GROK_API_KEY=

# Moonshot Kimi (for balance monitoring)
MOONSHOT_API_KEY=

# Google Maps
GOOGLE_MAPS_API_KEY=

# Twilio WhatsApp
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_FROM=
```

## Iteration Budget

- **Max iterations:** 8 (larger scope than typical feature)
- **Escalation:** If not converged after 8 iterations, pause for human review

---

## Verification Summary

| Category | AUTO_VERIFY | HUMAN_VERIFY | Total |
|----------|-------------|--------------|-------|
| Core Framework | 7 | 0 | 7 |
| Nutrition Domain | 11 | 0 | 11 |
| News Domain | 4 | 0 | 4 |
| API Usage Domain | 3 | 0 | 3 |
| AI Morning Briefing | 7 | 0 | 7 |
| API Balance Monitoring | 7 | 0 | 7 |
| School Run Report | 10 | 0 | 10 |
| Error Handling | 6 | 0 | 6 |
| Performance | 3 | 0 | 3 |
| Integration Tests | 5 | 0 | 5 |
| **Total** | **63** | **0** | **63** |

All criteria are machine-verifiable. No human judgment required for verification.
