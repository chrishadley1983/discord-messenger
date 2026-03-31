# Hadley API Reference

FastAPI application running on **port 8100**. Serves as Peter's gateway to external services, Google APIs, home automation, and internal systems.

```
uvicorn hadley_api.main:app --port 8100
```

NSSM service name: `HadleyAPI`

---

## Module Overview

| Module | Prefix | File | Endpoints | Purpose |
|--------|--------|------|-----------|---------|
| Core | `/` | `main.py` | ~180 | Gmail, Calendar, Drive, Sheets, Docs, Tasks, Contacts, Nutrition, Meal Plan, Recipes, Weather, Location, Shopping, Utilities, Brain, Schedule, Reminders |
| Peterbot Tasks | `/ptasks` | `task_routes.py` | 20 | Supabase-backed task management (personal_todo, peter_queue, idea, research) |
| Brain Graph | `/brain/graph` | `brain_routes.py` | 5 | Second Brain mind map visualization and search |
| Vinted | `/vinted` | `vinted_routes.py` | 1 | Parcel collection tracking from Gmail |
| Spotify | `/spotify` | `spotify_routes.py` | 17 | Full playback control, playlists, recommendations |
| Claude | `/claude` | `claude_routes.py` | 1 | Claude CLI extraction (uses OAuth subscription, no API key) |
| Vault | `/vault` | `vault_routes.py` | 4 | Encrypted payment card storage (Fernet AES) |
| WhatsApp | `/whatsapp` | `whatsapp_webhook.py` | 5 | Evolution API messaging (send, voice, webhook) |
| Voice | `/voice` | `voice_routes.py` | 5 | STT (Moonshine), TTS (Kokoro), round-trip conversation |
| Spellings | `/spellings` | `spelling_routes.py` | 3 | School spelling test management |
| Japan | `/japan` | `japan_routes.py` | 16 | Trip planning, day plans, digest, SIM, photobook, expenses, trains |
| Browser | `/browser` | `browser_routes.py` | 10 | Chrome CDP automation with domain allowlist and spending limits |
| Finance | `/finance` | `finance_routes.py` | 13 | Personal finance + Hadley Bricks P&L (fallback for MCP) |
| Schedule Manager | `/schedule` | `schedule_manager.py` + `main.py` | 14 | SCHEDULE.md management, job CRUD, pauses, pending actions |
| HB Proxy | `/hb` | `main.py` | 1 (catch-all) | Proxy to Hadley Bricks Next.js app (localhost:3000) |
| Peter Routes | varies | `peter_routes/*.py` | auto-discovered | Peter-created endpoint files |

---

## System and Health

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/` | -- | Root health check. Returns `{status, service, timestamp}` |
| GET | `/health` | -- | Simple health check. Returns `{status: "ok"}` |
| GET | `/time` | -- | Current UK date/time from Windows host (WSL clocks can drift) |
| POST | `/services/restart/{service_name}` | path: service_name | Restart NSSM service. Allowed: `DiscordBot`, `HadleyAPI`, `PeterDashboard` |
| GET | `/channels/status` | -- | Status of all 3 channel tmux sessions (peter/whatsapp/jobs) + HTTP health |
| POST | `/channels/restart/{session_name}` | path: session_name | Kill and relaunch a channel tmux session |
| POST | `/channels/restart-all` | -- | Restart all channel sessions |
| GET | `/model/status` | -- | Current model provider status |
| PUT | `/model/switch` | body: `{provider, reason}` | Switch provider (claude or kimi) |
| PUT | `/model/auto-switch` | -- | Toggle auto-recovery |
| POST | `/response/capture` | body: `{text, user_message?, channel_name?, channel_id?, message_id?}` | Capture response to Second Brain (fire-and-forget from channel reply tool) |

**Example -- `/time`:**
```json
{
  "date": "2026-03-27",
  "time": "14:30",
  "day": "Friday",
  "datetime": "2026-03-27T14:30:00+00:00",
  "timezone": "Europe/London"
}
```

---

## Gmail (20 endpoints)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/gmail/unread` | `limit` (max 20) | Unread emails with id, from, subject, date, snippet |
| GET | `/gmail/search` | `q` (required), `limit` (max 500), `account` (personal/hadley-bricks) | Search with full Gmail query syntax. Paginates for large limits |
| GET | `/gmail/get` | `id` (required), `account`, `html` (bool) | Full email content. Extracts plain text from HTML. Optional raw HTML |
| GET | `/gmail/thread` | `id` (required) | Full email thread/conversation with all messages |
| GET | `/gmail/labels` | `account` | List all Gmail labels |
| GET | `/gmail/starred` | `limit` (max 20) | Starred emails |
| GET | `/gmail/attachments` | `message_id` (required), `attachment_id` (optional) | List or download attachments (base64) |
| GET | `/gmail/attachment/text` | `message_id`, `attachment_id` | Extract text from PDF/text attachments (uses pypdf) |
| POST | `/gmail/send` | `to`, `subject`, `body`, `attachments[]` | Send email with optional file attachments |
| POST | `/gmail/draft` | `to`, `subject`, `body`, `attachments[]` | Create draft with optional file attachments |
| POST | `/gmail/reply` | `message_id`, `body`, `attachments[]` | Reply to email (maintains thread) |
| POST | `/gmail/forward` | `message_id`, `to`, `comment?` | Forward email with optional comment |
| POST | `/gmail/archive` | `message_id` | Archive (remove INBOX label) |
| POST | `/gmail/trash` | `message_id` | Move to trash |
| POST | `/gmail/mark-read` | `message_id`, `read` (bool) | Mark as read/unread |
| GET | `/gmail/vacation` | -- | Get vacation responder settings |
| POST | `/gmail/vacation` | `enabled`, `subject?`, `message?` | Set vacation responder |
| GET | `/gmail/filters` | -- | List email filters |
| GET | `/gmail/signature` | -- | Get primary email signature |

**Example -- `/gmail/search`:**
```
GET /gmail/search?q=from:amazon.co.uk subject:dispatch&limit=5
```
```json
{
  "query": "from:amazon.co.uk subject:dispatch",
  "count": 3,
  "emails": [
    {"id": "19abc...", "from": "Amazon <ship@amazon.co.uk>", "subject": "Your order has been dispatched", "date": "Thu, 27 Mar 2026 10:00:00 +0000", "snippet": "Your order #123..."}
  ],
  "fetched_at": "2026-03-27T14:30:00+00:00"
}
```

---

## Calendar (16 endpoints)

Queries across 3 calendars: Chris (primary), Abby, and Family.

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/calendar/today` | -- | Today's events across all calendars, sorted by time |
| GET | `/calendar/week` | -- | Next 7 days, grouped by day |
| GET | `/calendar/range` | `start_date`, `end_date`, `limit` (max 5000) | Events in date range (paginated) |
| GET | `/calendar/next` | `limit` (max 10) | Next N upcoming events |
| GET | `/calendar/search` | `q`, `limit` | Search events +/-1 year |
| GET | `/calendar/event` | `id` | Specific event details |
| GET | `/calendar/free` | `date?`, `duration` (mins, default 60) | Free time slots (09:00-17:30) |
| GET | `/calendar/conflicts` | `start_date?`, `end_date?` | Find overlapping events |
| GET | `/calendar/calendars` | -- | List all calendars with access roles |
| GET | `/calendar/busy` | `email`, `date?` | Check if someone is busy (freebusy API) |
| GET | `/calendar/meal-context` | `week_start?` | Analyse week for meal planning overrides (busy evenings, eating out, guests) |
| POST | `/calendar/create` | `summary`, `start`, `end?`, `location?`, `description?`, `attachments[]` | Create event (timed or all-day). Supports Drive file attachments |
| POST | `/calendar/quickadd` | `text` | Natural language event creation |
| POST | `/calendar/recurring` | `summary`, `start_time`, `days`, `duration_mins?`, `start_date?`, `end_date?`, `location?`, `color_id?`, `transparency?`, `exclude_dates?` | Create recurring event with color, free/busy, exclusion support |
| POST | `/calendar/invite` | `event_id`, `email` | Add attendee to event |
| PUT | `/calendar/event` | `id`, `summary?`, `start?`, `end?`, `location?`, `description?`, `attachments[]` | Update event fields |
| DELETE | `/calendar/event` | `id` | Delete event |

**Example -- `/calendar/meal-context`:**
```json
{
  "week_start": "2026-03-23",
  "overrides": {
    "2026-03-25": {"type_override": null, "max_prep_override": 20, "portions_override": null, "reasons": ["Swimming until 18:00 - quick meal night"]}
  },
  "summary": "Tue: quick meal (Swimming until 18:00 - quick meal night)"
}
```

---

## Google Drive (16 endpoints)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/drive/search` | `q`, `limit` | Search files by name or content |
| GET | `/drive/recent` | `limit` | Recently accessed files |
| GET | `/drive/starred` | `limit` | Starred files |
| GET | `/drive/shared` | `limit` | Files shared with me |
| GET | `/drive/download` | `file_id` | Get download/view links |
| GET | `/drive/export` | `file_id`, `format` (pdf/docx/xlsx/pptx/txt) | Export Google Doc/Sheet/Slides |
| GET | `/drive/permissions` | `file_id` | List who has access |
| GET | `/drive/storage` | -- | Storage quota (usage, limit, available) |
| POST | `/drive/create` | `title`, `type` (document/spreadsheet/presentation), `folder_id?`, body: `{content?, folder_name?}` | Create Google Doc/Sheet/Slides with optional content |
| POST | `/drive/upload` | `file_path`, `folder_id?`, `title?` | Upload local file |
| POST | `/drive/folder` | `name`, `parent_id?` | Create folder |
| POST | `/drive/copy` | `file_id`, `name?` | Copy file |
| POST | `/drive/rename` | `file_id`, `name` | Rename file |
| POST | `/drive/move` | `file_id`, `folder_id` | Move file to folder |
| POST | `/drive/share` | `file_id`, `email`, `role` (reader/commenter/writer) | Share file |
| POST | `/drive/trash` | `file_id` | Trash file |

---

## Google Sheets (5 endpoints)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/sheets/read` | `spreadsheet_id`, `range` | Read data from range |
| GET | `/sheets/info` | `spreadsheet_id` | Spreadsheet metadata (sheet names, row/column counts) |
| POST | `/sheets/write` | `spreadsheet_id`, `range`, `values` (JSON array) | Write data to range |
| POST | `/sheets/append` | `spreadsheet_id`, `range`, `values` (JSON array) | Append rows |
| POST | `/sheets/clear` | `spreadsheet_id`, `range` | Clear range |

---

## Google Docs (2 endpoints)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/docs/read` | `document_id` | Read document text (max 10k chars) |
| POST | `/docs/append` | `document_id`, `text` | Append text to end of document |

---

## Google Tasks (3 endpoints)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/tasks/list` | `tasklist` (default: @default) | List incomplete tasks (max 20) |
| POST | `/tasks/create` | `title`, `notes?`, `due?`, `tasklist` | Create task |
| POST | `/tasks/complete` | `task_id`, `tasklist` | Mark task complete |

---

## Contacts (1 endpoint)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/contacts/search` | `q` | Search Google Contacts by name, email, phone |

---

## Notion (2 endpoints)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/notion/todos` | -- | Get Notion todos |
| GET | `/notion/ideas` | -- | Get Notion ideas |

---

## Weather and Location (14 endpoints)

### Weather (Open-Meteo, free)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/weather/current` | -- | Current weather for Tonbridge (temp, feels_like, humidity, wind, condition) |
| GET | `/weather/forecast` | `days` (max 14) | Daily forecast (high/low, precipitation, condition) |

### Traffic and Directions (Google Maps)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/traffic/school` | -- | Live traffic to school with delay assessment |
| GET | `/directions` | `destination`, `origin?`, `mode` (driving/walking/bicycling/transit) | Directions to destination |
| GET | `/directions/matrix` | `destinations` (comma-separated), `origin?` | Travel times to multiple destinations |

### Places (Google Places API)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/places/search` | `query`, `location?` | Search for places (uses Places API New) |
| GET | `/places/details` | `place_id` | Detailed place info (hours, phone, reviews) |
| GET | `/places/nearby` | `location?`, `type`, `radius` | Find places by type near location |
| GET | `/places/autocomplete` | `input`, `location?` | Place name suggestions |

### Geocoding and Maps

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/geocode` | `address?`, `latlng?` | Address to coordinates or reverse |
| GET | `/timezone` | `location` | Timezone info for location |
| GET | `/elevation` | `location` | Elevation in meters/feet |
| GET | `/distance` | `origin`, `destination` | Straight-line distance (Haversine) |
| GET | `/location/{person}` | path: person (chris/abby) | Real-time family location + distance from home |
| GET | `/maps/static` | `location`, `zoom?`, `size?` | Static map image URL |
| GET | `/maps/streetview` | `location`, `heading?`, `size?` | Street View image URL |

---

## Home Automation (4 endpoints)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/ev/status` | -- | EV charging status from Ohme (rate, mode, energy) |
| GET | `/ev/combined` | -- | Combined Kia Connect + Ohme status (actual battery % + charge rate) |
| GET | `/ring/status` | -- | Ring doorbell status, battery, recent events |
| GET | `/kia/status` | -- | Kia vehicle status (battery %, range, charging, location, locked) |

**Example -- `/ev/combined`:**
```json
{
  "battery_level": 72,
  "battery_source": "kia_connect",
  "range_km": 280,
  "charging": false,
  "plugged_in": true,
  "charge_rate_kw": 0,
  "charge_mode": "smart_charge",
  "energy_added_wh": 1500,
  "charger_available": true,
  "fetched_at": "2026-03-27T14:30:00+00:00"
}
```

---

## Nutrition (18 endpoints)

Supabase-backed nutrition tracking with Withings integration for weight/steps.

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| POST | `/nutrition/log-meal` | body: meal data | Log a meal |
| POST | `/nutrition/log-water` | body: water data | Log water intake |
| DELETE | `/nutrition/meal` | query params | Delete a meal entry |
| GET | `/nutrition/water/entries` | query params | Get water entries |
| DELETE | `/nutrition/water` | query params | Delete a water entry |
| POST | `/nutrition/water/reset` | query params | Reset water for a day |
| GET | `/nutrition/today` | -- | Today's nutrition summary |
| GET | `/nutrition/today/meals` | -- | Today's logged meals |
| GET | `/nutrition/date` | query params | Nutrition for a specific date |
| GET | `/nutrition/date/meals` | query params | Meals for a specific date |
| GET | `/nutrition/week` | -- | Weekly nutrition summary |
| GET | `/nutrition/goals` | -- | Nutrition goals |
| PATCH | `/nutrition/goals` | body: goal updates | Update nutrition goals |
| GET | `/nutrition/steps` | -- | Step count (Withings) |
| GET | `/nutrition/weight` | -- | Current weight (Withings) |
| GET | `/nutrition/weight/history` | -- | Weight history (Withings) |
| GET | `/nutrition/favourites` | -- | Favourite meals list |
| GET | `/nutrition/favourite` | query params | Get a specific favourite |
| POST | `/nutrition/favourite` | body: favourite data | Save a favourite meal |
| DELETE | `/nutrition/favourite` | query params | Remove a favourite |
| GET | `/withings/status` | -- | Withings API connection status |

---

## Meal Planning (28 endpoints)

Full meal planning pipeline: create plans, import from Sheets/CSV/Gousto, generate shopping lists, export to PDF/HTML, push to grocery trolley.

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/meal-plan/current` | -- | Current active meal plan |
| GET | `/meal-plan/meals` | -- | Meals in current plan |
| GET | `/meal-plan/reminders` | -- | Meal plan reminders |
| GET | `/meal-plan/week` | -- | Week view of meal plan |
| GET | `/meal-plan/{plan_id}` | path: plan_id | Specific plan details |
| POST | `/meal-plan` | body: plan data | Create new meal plan |
| DELETE | `/meal-plan/{plan_id}` | path: plan_id | Delete meal plan |
| PUT | `/meal-plan/{plan_id}/ingredients` | path: plan_id, body | Update plan ingredients |
| POST | `/meal-plan/import/sheets` | body: import config | Import from Google Sheets |
| POST | `/meal-plan/import/csv` | body: CSV data | Import from CSV |
| POST | `/meal-plan/import/gousto` | body: Gousto data | Import from Gousto |
| **Templates** | | | |
| GET | `/meal-plan/templates` | -- | List templates |
| GET | `/meal-plan/templates/default` | -- | Default template |
| GET | `/meal-plan/templates/{name}` | path: name | Get template |
| PUT | `/meal-plan/templates/{name}` | path: name, body | Update template |
| DELETE | `/meal-plan/templates/{name}` | path: name | Delete template |
| **Preferences** | | | |
| GET | `/meal-plan/preferences` | -- | Meal preferences |
| PUT | `/meal-plan/preferences` | body: preferences | Update preferences |
| **History** | | | |
| POST | `/meal-plan/history` | body: history entry | Log meal to history |
| GET | `/meal-plan/history` | -- | Meal history |
| PATCH | `/meal-plan/history/{meal_id}/rating` | path: meal_id, body | Rate a meal |
| **Staples** | | | |
| POST | `/meal-plan/staples` | body: staple data | Add staple item |
| GET | `/meal-plan/staples` | -- | List staples |
| GET | `/meal-plan/staples/due` | -- | Staples due for purchase |
| PUT | `/meal-plan/staples/{name}` | path: name, body | Update staple |
| DELETE | `/meal-plan/staples/{name}` | path: name | Delete staple |
| POST | `/meal-plan/staples/mark-added` | body: items | Mark staples as added |
| **Shopping List** | | | |
| GET | `/meal-plan/shopping-list` | -- | Get shopping list from plan |
| POST | `/meal-plan/shopping-list/generate` | body: config | Generate shopping list |
| POST | `/meal-plan/shopping-list/html` | body: list data | Generate HTML shopping list |
| POST | `/meal-plan/shopping-list/to-trolley` | body: trolley config | Push list to grocery trolley |
| **Export** | | | |
| POST | `/meal-plan/view/html` | body: view config | Generate HTML view of plan |
| POST | `/meal-plan/export-pdf` | body: export config | Export plan as PDF |

---

## Recipes (10 endpoints)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| POST | `/recipes/extract` | body: `{url}` | Extract recipe from URL via Chrome CDP (JSON-LD parsing) |
| GET | `/recipes/search` | query params | Search recipes |
| GET | `/recipes/discover` | -- | Discover new recipes |
| GET | `/recipes/batch-friendly` | -- | Recipes suitable for batch cooking |
| POST | `/recipes` | body: recipe data | Create recipe |
| GET | `/recipes/{recipe_id}` | path: recipe_id | Get recipe details |
| PATCH | `/recipes/{recipe_id}/usage` | path: recipe_id | Log recipe usage |
| PATCH | `/recipes/{recipe_id}/rating` | path: recipe_id, body | Rate recipe |
| DELETE | `/recipes/{recipe_id}` | path: recipe_id | Delete recipe |
| POST | `/recipes/{recipe_id}/card` | path: recipe_id | Generate recipe card |
| POST | `/recipes/cards/batch` | body: recipe_ids | Batch generate recipe cards |

---

## Grocery Shopping (9 endpoints)

Chrome CDP-based grocery store automation.

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/grocery/price-cache` | -- | Cached product prices |
| POST | `/grocery/price-scan` | body: scan config | Scan prices for products |
| GET | `/grocery/{store}/prices` | path: store | Store-specific prices |
| GET | `/grocery/{store}/login-check` | path: store | Check store login status |
| GET | `/grocery/{store}/search` | path: store, query params | Search store products |
| GET | `/grocery/{store}/slots` | path: store | Available delivery slots |
| POST | `/grocery/{store}/slots/book` | path: store, body | Book delivery slot |
| GET | `/grocery/{store}/trolley` | path: store | Current trolley contents |
| POST | `/grocery/{store}/trolley/add-list` | path: store, body | Add shopping list to trolley |
| POST | `/grocery/{store}/trolley/resolve` | path: store, body | Resolve items in trolley |

---

## Shopping List (1 endpoint)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| POST | `/shopping-list/generate` | body: list data | Generate printable PDF shopping list |

---

## Reminders (5 endpoints)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/reminders` | `user_id` | List reminders for user |
| GET | `/reminders/active-nags` | -- | Reminders in active nag mode |
| POST | `/reminders` | body: `{task, run_at, user_id, channel_id, reminder_type?, interval_minutes?, nag_until?, delivery?}` | Create reminder |
| POST | `/reminders/{reminder_id}/acknowledge` | path: reminder_id | Acknowledge a nagging reminder |
| PATCH | `/reminders/{reminder_id}` | path: reminder_id, body | Update reminder |
| DELETE | `/reminders/{reminder_id}` | path: reminder_id | Delete reminder |

---

## Second Brain (4 endpoints)

Direct REST access to the knowledge base (MCP is the primary path).

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/brain/search` | query params | Semantic search across knowledge items |
| POST | `/brain/save` | body: item data | Save item to Second Brain |
| GET | `/brain/stats` | -- | Knowledge base statistics |
| DELETE | `/brain/item/{item_id}` | path: item_id | Delete knowledge item |

---

## Peterbot Tasks `/ptasks` (20 endpoints)

Supabase-backed task management across 4 list types: `personal_todo`, `peter_queue`, `idea`, `research`.

**Status values:** inbox, scheduled, queued, heartbeat_scheduled, in_heartbeat, in_progress, review, findings_ready, done, cancelled, parked

**Priority values:** critical, high, medium, low, someday

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/ptasks` | filters (status, priority, list_type, etc.) | List tasks with filters |
| GET | `/ptasks/counts` | -- | Task counts by list and status |
| GET | `/ptasks/list/{list_type}` | path: list_type | Tasks for a specific list |
| GET | `/ptasks/{task_id}` | path: task_id | Get task details |
| POST | `/ptasks` | body: TaskCreate | Create task |
| PUT | `/ptasks/{task_id}` | path: task_id, body: TaskUpdate | Update task |
| DELETE | `/ptasks/{task_id}` | path: task_id | Delete task |
| POST | `/ptasks/{task_id}/status` | body: `{status, actor}` | Change task status (validates transitions) |
| POST | `/ptasks/{task_id}/heartbeat` | body: HeartbeatSchedule | Schedule task for heartbeat |
| GET | `/ptasks/heartbeat/plan` | -- | Current heartbeat plan |
| **Comments** | | | |
| POST | `/ptasks/{task_id}/comments` | body: `{content, author?, is_system_message?}` | Add comment |
| GET | `/ptasks/{task_id}/comments` | -- | List comments |
| **History** | | | |
| GET | `/ptasks/{task_id}/history` | -- | Task change history |
| **Categories** | | | |
| GET | `/ptasks/categories` | -- | List all categories |
| POST | `/ptasks/categories` | body: `{name, slug?, color?, icon?}` | Create category |
| PUT | `/ptasks/categories/{category_id}` | body: `{name?, color?, icon?}` | Update category |
| DELETE | `/ptasks/categories/{category_id}` | -- | Delete category |
| PUT | `/ptasks/{task_id}/categories` | body: `{category_slugs}` | Set task categories |
| **Reorder** | | | |
| POST | `/ptasks/{task_id}/reorder` | body: reorder data | Reorder single task |
| POST | `/ptasks/bulk/reorder` | body: bulk reorder data | Bulk reorder tasks |

---

## Brain Graph `/brain/graph` (5 endpoints)

Mind map visualization from Second Brain data.

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/brain/graph` | -- | Full graph data (topics, edges, stats). Cached 10 min |
| GET | `/brain/graph/topic/{topic}` | `limit` (max 100) | Knowledge items for a specific topic |
| GET | `/brain/graph/search` | query params | Semantic search with topic highlighting |
| GET | `/brain/graph/activity` | -- | Activity patterns |
| POST | `/brain/graph/refresh` | -- | Clear cache |

---

## Spotify `/spotify` (17 endpoints)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/spotify/now-playing` | -- | Current playback state with mood data |
| POST | `/spotify/play` | body: `{query, type, device?}` | Search and play (track/album/artist/playlist) |
| POST | `/spotify/play-uri` | body: `{uri, device?}` | Play by Spotify URI |
| POST | `/spotify/queue` | body: `{query}` | Add to queue |
| POST | `/spotify/pause` | -- | Pause playback |
| POST | `/spotify/resume` | -- | Resume playback |
| POST | `/spotify/skip` | -- | Skip to next |
| POST | `/spotify/previous` | -- | Previous track |
| POST | `/spotify/volume` | body: `{level}` | Set volume (0-100) |
| POST | `/spotify/seek` | body: `{position_ms}` | Seek to position |
| POST | `/spotify/shuffle` | body: `{state}` | Toggle shuffle |
| POST | `/spotify/repeat` | body: `{state}` (off/track/context) | Set repeat mode |
| GET | `/spotify/devices` | -- | List available devices |
| POST | `/spotify/transfer` | body: `{device}` | Transfer playback to device |
| GET | `/spotify/playlists` | -- | List playlists |
| POST | `/spotify/play-playlist` | body: playlist data | Play a playlist |
| GET | `/spotify/recommend` | -- | Get recommendations based on current playback |
| POST | `/spotify/play-similar` | -- | Play similar tracks |

**Example -- `/spotify/play`:**
```json
POST /spotify/play
{"query": "Parachutes Coldplay", "type": "album"}
```

---

## WhatsApp `/whatsapp` (5 endpoints)

Evolution API integration for WhatsApp messaging.

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| POST | `/whatsapp/send` | body: message data | Send WhatsApp message |
| POST | `/whatsapp/send-voice` | body: voice data | Send voice message |
| GET | `/whatsapp/status` | -- | WhatsApp connection status |
| POST | `/whatsapp/webhook` | body: webhook payload | Receive incoming messages (debounced per sender, 3s) |
| POST | `/whatsapp/webhook/{event_type}` | body: webhook payload | Receive typed webhook events |

---

## Voice `/voice` (5 endpoints)

Local STT (Moonshine ONNX) and TTS (Kokoro ONNX) pipeline.

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| POST | `/voice/listen` | audio body (wav/ogg/webm/mp3/m4a/flac) | Transcribe audio to text |
| POST | `/voice/speak` | body: `{text, voice?, speed?}` | Synthesise text to audio. Default voice: `bm_daniel` |
| POST | `/voice/converse` | body: `{sender_name?, sender_number?}` + audio body | Full round-trip: STT -> Peter -> TTS |
| GET | `/voice/audio/{filename}` | path: filename | Serve generated audio file (5 min TTL) |
| GET | `/voice/voices` | -- | List available TTS voices |

---

## Spellings `/spellings` (3 endpoints)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| POST | `/spellings/add` | body: `{child_name, year_group, academic_year?, week_number, phoneme?, words[]}` | Add/update spelling words for a week |
| GET | `/spellings/current-week` | -- | Get current week's spellings |
| POST | `/spellings/sentences` | body: `{sentences: {word: sentence}}` | Add practice sentences for words |

---

## Japan `/japan` (16 endpoints)

Japan 2026 trip planning: day plans, daily digest emails, SIM tracking, photobook, expenses, train status.

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/japan/day-plans` | -- | All day plans |
| GET | `/japan/day-plans/{date}` | path: date (YYYY-MM-DD) | Single day plan |
| PUT | `/japan/day-plans/{date}` | body: `{city?, stay_name?, plan_data?, notes?}` | Update day plan |
| POST | `/japan/digest/send` | body: digest config | Generate and send daily digest email |
| GET | `/japan/trains` | `city` (default: all) | Live train status for Japanese cities |
| GET | `/japan/trains/status` | -- | Train status summary |
| GET | `/japan/sim` | -- | SIM card status |
| POST | `/japan/sim` | body: SIM data | Update SIM data |
| POST | `/japan/sim/time` | body: time data | Log SIM time usage |
| POST | `/japan/photobook/upload` | body: photo data | Upload photo to photobook |
| POST | `/japan/photobook/highlight` | body: highlight data | Mark photo as highlight |
| POST | `/japan/photobook/diary` | body: diary entry | Add diary entry |
| GET | `/japan/photobook/coverage/{day_number}` | path: day_number | Photo coverage for a day |
| POST | `/japan/expenses` | body: expense data | Log expense |
| GET | `/japan/expenses/today` | -- | Today's expenses |
| POST | `/japan/alerts/send` | body: alert data | Send alert |
| POST | `/japan/alerts/test` | body: test config | Test alert delivery |

---

## Browser `/browser` (10 endpoints)

Chrome CDP automation with domain allowlist and spending limits. Protected by API key.

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/browser/domains` | -- | List allowed domains |
| GET | `/browser/limits` | -- | Current spending limits |
| POST | `/browser/limits/check` | body: purchase check | Check if purchase is within limits |
| POST | `/browser/session/start` | body: `{domain, user_id, channel_id}` | Start browser session |
| GET | `/browser/session/{session_id}` | path: session_id | Get session status |
| POST | `/browser/session/end` | body: `{session_id, save_state?}` | End session |
| GET | `/browser/screenshot` | query: session_id | Take screenshot |
| POST | `/browser/action` | body: `{session_id, action, params, purchase_id?}` | Execute action (navigate/click/type/press/scroll/wait) |
| GET | `/browser/text` | query: session_id | Extract page text |
| GET | `/browser/fetch` | query params | Fetch URL content |

---

## Finance `/finance` (13 endpoints)

HTTP fallback for the financial-data MCP server. All responses are pre-formatted markdown.

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/finance/net-worth` | -- | Current net worth across all accounts |
| GET | `/finance/budget` | `year?`, `month?` | Budget status by category |
| GET | `/finance/spending` | `period`, `category_name?` | Spending breakdown |
| GET | `/finance/savings-rate` | `year?`, `month?` | Savings rate calculation |
| GET | `/finance/fire` | `scenario_name?` | FIRE progress |
| GET | `/finance/recurring` | `min_occurrences`, `months` | Recurring transactions (subscriptions) |
| GET | `/finance/search` | `query`, `period`, `limit` | Search transactions |
| GET | `/finance/transactions` | `category_name`, `period`, `limit` | Transactions by category |
| GET | `/finance/business/pnl` | `start_month?`, `end_month?` | Hadley Bricks P&L statement |
| GET | `/finance/business/revenue` | `platform?`, `period` | Revenue by platform (eBay, Amazon, BrickLink, Brick Owl) |
| GET | `/finance/compare` | `period_a`, `period_b` | Compare spending between two periods |
| GET | `/finance/health` | -- | Comprehensive financial overview |

---

## Schedule Management (14 endpoints)

SCHEDULE.md management with atomic read/write, job CRUD, pause system, and pending action confirmations.

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/schedule` | -- | Read SCHEDULE.md content |
| PUT | `/schedule` | body: new content | Write SCHEDULE.md + trigger reload |
| POST | `/schedule/reload` | -- | Trigger schedule reload (file-based trigger, polled every 10s) |
| POST | `/schedule/run/{skill_name}` | path: skill_name | Manually run a scheduled skill |
| **Job CRUD** | | | |
| GET | `/schedule/jobs` | -- | List all jobs (parsed from SCHEDULE.md) |
| PATCH | `/schedule/jobs/{skill}` | body: field updates | Update job field (name, schedule, channel, enabled) |
| POST | `/schedule/jobs` | body: job definition | Add new job to schedule |
| DELETE | `/schedule/jobs/{skill}` | path: skill | Remove job from schedule |
| **Pauses** | | | |
| GET | `/schedule/pauses` | -- | List active pauses |
| POST | `/schedule/pauses` | body: pause config | Pause a skill |
| DELETE | `/schedule/pauses/{pause_id}` | path: pause_id | Remove a pause |
| GET | `/schedule/pauses/check/{skill}` | path: skill | Check if skill is paused |
| **Pending Actions** | | | |
| POST | `/schedule/pending-actions` | body: action data | Create pending action (requires Chris confirmation) |
| GET | `/schedule/pending-actions` | -- | List pending actions |
| POST | `/schedule/pending-actions/{action_id}/confirm` | path: action_id | Confirm pending action |
| POST | `/schedule/pending-actions/{action_id}/cancel` | path: action_id | Cancel pending action |

---

## Vault `/vault` (4 endpoints)

Encrypted payment card storage. Fernet AES-128-CBC + HMAC-SHA256. Data never leaves localhost.

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| POST | `/vault/cards` | body: `{label, card_number, expiry, cvc, name_on_card?, is_default?}` | Save new card (encrypts + writes to disk) |
| GET | `/vault/cards` | -- | List cards (last-4 digits only) |
| GET | `/vault/cards/default` | -- | Full default card details (for browser automation) |
| DELETE | `/vault/cards/{card_id}` | path: card_id | Remove a card |

---

## Claude `/claude` (1 endpoint)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| POST | `/claude/extract` | body: `{prompt, max_tokens?, model?}` | Run Claude extraction via local CLI (`claude -p`). Uses OAuth subscription |

---

## Vinted `/vinted` (1 endpoint)

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/vinted/collections` | -- | Parcel collection tracking from Gmail (parses InPost/Royal Mail/Evri/DPD emails) |

---

## HB Proxy `/hb` (catch-all)

Proxies all requests to the Hadley Bricks Next.js app on `localhost:3000/api/*`. Auto-injects the `x-api-key` header from `HADLEY_BRICKS_API_KEY` env var.

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| ANY | `/hb/{path}` | pass-through | `GET/POST/PUT/PATCH/DELETE /hb/inventory/summary` -> `localhost:3000/api/inventory/summary` |

---

## Utilities (25+ endpoints)

### Conversion and Encoding

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/currency` | `amount`, `from_currency`, `to_currency` | Currency conversion (exchangerate-api) |
| GET | `/units` | `value`, `from_unit`, `to_unit` | Unit conversion (km/miles, kg/lb, C/F, L/gal, etc.) |
| GET | `/calculate` | `expression` | Safe math expression evaluator (supports sqrt, sin, cos, etc.) |
| GET | `/color` | `value` | Color format conversion (hex/rgb/name) |
| GET | `/encode` | `text`, `action` (encode/decode), `format` (base64/url) | Encode/decode text |
| GET | `/translate` | `text`, `target`, `source?` | Google Translate |

### Generators

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/qrcode` | `data`, `size?` | QR code image URL |
| GET | `/shorten` | `url` | URL shortener (TinyURL) |
| GET | `/uuid` | `count?` | Generate UUID(s) |
| GET | `/random` | `min?`, `max?`, `count?` | Random number(s) |
| GET | `/password` | `length?`, `include_symbols?` | Secure password generator |

### Date and Time

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/countdown` | `date` (YYYY-MM-DD or event name) | Days until a date |
| GET | `/age` | date param | Calculate age |
| GET | `/holidays` | query params | UK bank holidays |
| GET | `/sunrise` | query params | Sunrise/sunset times |
| GET | `/moon` | -- | Moon phase |

### Reference and Lookup

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/wikipedia` | query | Wikipedia summary |
| GET | `/dictionary` | query | Word definition |
| GET | `/synonyms` | query | Synonyms/thesaurus |
| GET | `/quote` | -- | Random quote |
| GET | `/fact` | -- | Random fact |
| GET | `/youtube/search` | `q`, `limit?` | Search YouTube videos |

### Network

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/ip` | -- | Public IP information |
| GET | `/dns` | query | DNS lookup |
| GET | `/whois` | query | WHOIS lookup |
| GET | `/ping` | query | Ping a host |

---

## Monitoring and Operations

| Method | Path | Parameters | Purpose |
|--------|------|------------|---------|
| GET | `/jobs/health` | `hours` (default 24) | Unified job health across DM (SQLite) and HB (Supabase) |
| GET | `/gcp/usage` | `hours` (default 24) | GCP API usage and estimated cost |
| GET | `/gcp/monthly` | -- | GCP month-to-date spend with projection |
| POST | `/deploy/surge` | body: deploy config | Deploy HTML to surge.sh |
| POST | `/investment/retrain` | -- | ML pipeline (build, features, train, score) |

---

## Authentication

The API runs on `localhost:8100` with no authentication for most endpoints (designed for local use by Peter and internal services).

Exceptions:
- **HB Proxy** (`/hb/*`): Auto-injects `x-api-key` header
- **Browser** (`/browser/*`): Requires API key authentication
- **Google APIs**: Uses OAuth credentials stored in `google_token.json` (auto-refreshes)

---

## Environment Variables

Key env vars loaded from `.env`:

| Variable | Used By |
|----------|---------|
| `SUPABASE_URL`, `SUPABASE_KEY` | Tasks, Brain, Spellings, Japan, Nutrition |
| `GOOGLE_MAPS_API_KEY` | Maps, Places, Directions, Geocoding, Translate |
| `OHME_EMAIL`, `OHME_PASSWORD` | EV charging |
| `KIA_EMAIL`, `KIA_PASSWORD`, `KIA_PIN` | Kia vehicle |
| `HADLEY_BRICKS_API_KEY` | HB Proxy |
| `VAULT_ENCRYPTION_KEY` | Vault |
| `WEATHER_LAT`, `WEATHER_LON`, `WEATHER_LOCATION_NAME` | Weather |
| `HOME_ADDRESS`, `SCHOOL_ADDRESS` | Traffic, Directions |
| `WHATSAPP_USE_CHANNEL` | WhatsApp routing (0=bot.py, 1=channel) |
| `DISCORD_WEBHOOK_ALERTS` | Job failure alerting |

---

## Error Handling

All endpoints follow a consistent pattern:
- **503**: Service not configured (missing credentials/API keys)
- **400**: Bad request (invalid parameters)
- **404**: Resource not found
- **500**: Internal error (detail in response body)
- **504**: Timeout (service restart)

Every successful response includes a `fetched_at` timestamp in `Europe/London` timezone.
