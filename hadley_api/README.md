# Hadley API

Local API proxy for Peter's real-time queries. Full CRUD access to Google services.

> **Alternative access**: The Second Brain (`/brain/*` endpoints) is also available via MCP server for Claude Desktop and Claude Code. See `mcp_servers/second_brain_mcp.py` and `.mcp.json`.

## Setup

```bash
cd hadley_api
pip install -r requirements.txt
```

## Run

```bash
# From Discord-Messenger directory
uvicorn hadley_api.main:app --port 8100 --reload
```

## Endpoints

### Gmail
**Read:**
- `GET /gmail/unread` - Get unread emails
- `GET /gmail/search?q=from:sarah` - Search emails
- `GET /gmail/get?id=<message_id>` - Get specific email
- `GET /gmail/thread?id=<thread_id>` - Get email thread
- `GET /gmail/labels` - List labels
- `GET /gmail/starred` - Get starred emails
- `GET /gmail/attachments?message_id=<id>` - List attachments
- `GET /gmail/attachment/text?message_id=<id>&attachment_id=<id>` - Get attachment text

**Write:**
- `POST /gmail/send?to=<email>&subject=<text>&body=<text>&attachments=<path>` - Send email (repeat `attachments` for multiple files)
- `POST /gmail/draft?to=<email>&subject=<text>&body=<text>&attachments=<path>` - Create draft (repeat `attachments` for multiple files)
- `POST /gmail/reply?message_id=<id>&body=<text>&attachments=<path>` - Reply to email (repeat `attachments` for multiple files)
- `POST /gmail/forward?message_id=<id>&to=<email>` - Forward email
- `POST /gmail/archive?message_id=<id>` - Archive email
- `POST /gmail/trash?message_id=<id>` - Move to trash
- `POST /gmail/mark-read?message_id=<id>` - Mark as read

**Settings:**
- `GET /gmail/vacation` - Get vacation responder
- `POST /gmail/vacation` - Set vacation responder
- `GET /gmail/filters` - List filters
- `GET /gmail/signature` - Get signature

### Calendar
**Read:**
- `GET /calendar/today?date=YYYY-MM-DD` - Events for a day (defaults to today)
- `GET /calendar/week?start_date=YYYY-MM-DD&days=7` - Events for date range
- `GET /calendar/range?start=YYYY-MM-DD&end=YYYY-MM-DD` - Events in range
- `GET /calendar/free?date=YYYY-MM-DD&duration=60` - Find free time slots
- `GET /calendar/search?q=meeting` - Search events
- `GET /calendar/event?id=<event_id>` - Get specific event
- `GET /calendar/next?limit=5` - Get next N events
- `GET /calendar/conflicts?start=<datetime>&end=<datetime>` - Check for conflicts
- `GET /calendar/calendars` - List all calendars
- `GET /calendar/busy?email=<email>&date=YYYY-MM-DD` - Check if someone is busy
- `GET /calendar/colors` - Get available event/calendar colors

**Write:**
- `POST /calendar/create` - Create event with full options:
  - `summary` (required), `start`, `end`, `location`, `description`, `attachments` (Google Drive URLs, repeat for multiple)
  - `color` - 1=lavender, 2=sage, 3=grape, 4=flamingo, 5=banana, 6=tangerine, 7=peacock, 8=graphite, 9=blueberry, 10=basil, 11=tomato
  - `visibility` - default, public, private, confidential
  - `transparency` - opaque (busy) or transparent (free)
  - `guests_can_modify`, `guests_can_invite`, `guests_can_see_guests` (booleans)
  - `reminders` - minutes comma-separated (e.g., "10,60" for 10min and 1hr)
- `POST /calendar/quickadd?text=Meeting tomorrow at 3pm` - Quick add event
- `POST /calendar/recurring?summary=<title>&start=<date>&rrule=<rule>` - Create recurring event
- `POST /calendar/invite?event_id=<id>&email=<email>` - Add attendee
- `PUT /calendar/event` - Update event with full options:
  - `id` (required), `summary`, `start`, `end`, `location`, `description`, `attachments` (Google Drive URLs, appended to existing)
  - `color`, `visibility`, `transparency`, `status` (confirmed/tentative/cancelled)
  - `reminders`
- `DELETE /calendar/event?id=<event_id>` - Delete event

### Drive
**Read:**
- `GET /drive/search?q=budget` - Search files
- `GET /drive/recent?limit=10` - Recent files
- `GET /drive/starred` - Starred files
- `GET /drive/shared` - Shared with me
- `GET /drive/download?file_id=<id>` - Download file
- `GET /drive/export?file_id=<id>&mime_type=<type>` - Export Google doc
- `GET /drive/permissions?file_id=<id>` - Get file permissions
- `GET /drive/storage` - Storage quota

**Write:**
- `POST /drive/create?title=<name>&type=<document|spreadsheet|presentation>` - Create file (optional JSON body: `{"content": "<text>", "folder_name": "<name>"}` to populate content and auto-find/create folder)
- `POST /drive/upload?file_path=<local_path>&title=<name>&folder_id=<id>` - Upload local file to Drive (returns file_id, link for use as calendar attachments)
- `POST /drive/folder?name=<name>` - Create folder
- `POST /drive/copy?file_id=<id>&name=<new_name>` - Copy file
- `POST /drive/rename?file_id=<id>&name=<new_name>` - Rename file
- `POST /drive/move?file_id=<id>&folder_id=<id>` - Move file
- `POST /drive/share?file_id=<id>&email=<email>&role=<role>` - Share file
- `POST /drive/trash?file_id=<id>` - Move to trash

### Sheets
**Read:**
- `GET /sheets/read?spreadsheet_id=<id>&range=<A1:B10>` - Read cells
- `GET /sheets/info?spreadsheet_id=<id>` - Get spreadsheet info

**Write:**
- `POST /sheets/write?spreadsheet_id=<id>&range=<A1>` - Write cells (body: values array)
- `POST /sheets/append?spreadsheet_id=<id>&range=<A1>` - Append rows
- `POST /sheets/clear?spreadsheet_id=<id>&range=<A1:B10>` - Clear cells
- `POST /sheets/create?title=<name>` - Create spreadsheet
- `POST /sheets/delete-rows?spreadsheet_id=<id>&sheet_id=<id>&start=<row>&end=<row>` - Delete rows
- `POST /sheets/insert-rows?spreadsheet_id=<id>&sheet_id=<id>&start=<row>&count=<n>` - Insert rows
- `PATCH /sheets/update?spreadsheet_id=<id>&range=<A1>` - Update cells

### Docs
**Read:**
- `GET /docs/read?document_id=<id>` - Read document

**Write:**
- `POST /docs/create?title=<name>` - Create document
- `POST /docs/append?document_id=<id>&text=<content>` - Append text
- `POST /docs/insert?document_id=<id>&text=<content>&index=<n>` - Insert at position
- `POST /docs/replace?document_id=<id>&find=<old>&replace=<new>` - Find and replace
- `POST /docs/delete?document_id=<id>&start=<n>&end=<n>` - Delete range

### Tasks
**Read:**
- `GET /tasks/lists` - List task lists
- `GET /tasks/list?tasklist_id=<id>` - Get tasks in list
- `GET /tasks/{task_id}?tasklist_id=<id>` - Get specific task

**Write:**
- `POST /tasks/create?tasklist_id=<id>&title=<title>` - Create task
- `POST /tasks/complete?tasklist_id=<id>&task_id=<id>` - Complete task
- `PATCH /tasks/{task_id}?tasklist_id=<id>` - Update task
- `DELETE /tasks/{task_id}?tasklist_id=<id>` - Delete task

### Contacts
**Read:**
- `GET /contacts/search?q=<name>` - Search contacts
- `GET /contacts/list?limit=100` - List contacts
- `GET /contacts/{resource_name}` - Get specific contact

**Write:**
- `POST /contacts` - Create contact (body: {givenName, familyName, email, phone})
- `PATCH /contacts/{resource_name}` - Update contact
- `DELETE /contacts/{resource_name}` - Delete contact

### Peterbot Tasks (ptasks)
Unified task management system with 4 list types: personal_todo, peter_queue, idea, research.

**Read:**
- `GET /ptasks` - List tasks (filters: list_type, status, priority, search)
- `GET /ptasks/list/{list_type}` - Get all tasks for a list type
- `GET /ptasks/{task_id}` - Get specific task with comments/attachments
- `GET /ptasks/counts` - Get task counts per list type (excludes done/cancelled)
- `GET /ptasks/categories` - Get task categories
- `GET /ptasks/{task_id}/comments` - Get task comments
- `GET /ptasks/heartbeat/plan` - Get heartbeat plan (scheduled tasks by date)

**Write:**
- `POST /ptasks` - Create task (body: {list_type, title, priority, ...})
- `PUT /ptasks/{task_id}` - Update task (title, description, priority, scheduled_date, due_date, estimated_effort)
- `DELETE /ptasks/{task_id}` - Delete task
- `POST /ptasks/{task_id}/status` - Change status (body: {status, actor})
- `POST /ptasks/{task_id}/heartbeat` - Schedule for heartbeat (body: {schedule_date?})
- `POST /ptasks/{task_id}/comments` - Add comment
- `PUT /ptasks/{task_id}/categories` - Update categories (body: [slugs])
- `POST /ptasks/{task_id}/reorder` - Reorder task
- `POST /ptasks/bulk/reorder` - Bulk reorder tasks

**Categories (Tags):**
- `POST /ptasks/categories` - Create category (body: {name, color?, icon?})
- `PUT /ptasks/categories/{id}` - Update category (body: {name?, color?, icon?})
- `DELETE /ptasks/categories/{id}` - Delete category (removes from all tasks)

**Task Lists:**
- `personal_todo` - Chris's personal tasks (statuses: inbox, scheduled, in_progress, done)
- `peter_queue` - Peter's work queue (statuses: queued, heartbeat_scheduled, in_heartbeat, in_progress, review, done)
- `idea` - Ideas dump (statuses: inbox, scheduled, review, done)
- `research` - Research queue (statuses: queued, in_progress, findings_ready, done)

**Priorities:** critical, high, medium, low, someday

### Notion
**Read:**
- `GET /notion/todos` - Get todos
- `GET /notion/ideas` - Get ideas

**Write:**
- `POST /notion/todos` - Create todo (body: {title})
- `PATCH /notion/todos/{todo_id}` - Update todo
- `DELETE /notion/todos/{todo_id}` - Delete todo
- `POST /notion/todos/{todo_id}/complete` - Mark complete
- `POST /notion/ideas` - Create idea
- `PATCH /notion/ideas/{idea_id}` - Update idea
- `DELETE /notion/ideas/{idea_id}` - Delete idea

### Reminders
**Read:**
- `GET /reminders?user_id=<id>` — List pending (unfired) reminders, sorted by run_at
- `GET /reminders/active-nags` — List active nag reminders (fired, not acknowledged). Optional `?delivery=whatsapp:abby` filter.

**Write:**
- `POST /reminders` — Create reminder (body: `{task, run_at, user_id, channel_id, reminder_type?, interval_minutes?, nag_until?, delivery?}`)
  - `run_at` must be ISO 8601 and in the future
  - `reminder_type`: `"one_off"` (default) or `"nag"` (repeats until acknowledged)
  - `interval_minutes`: Nag repeat interval (e.g. 120 = every 2 hours)
  - `nag_until`: Stop time in 24h format (e.g. `"21:00"`)
  - `delivery`: `"discord"` (default), `"whatsapp:chris"`, `"whatsapp:abby"`, `"whatsapp:group"`
- `POST /reminders/{id}/acknowledge` — Acknowledge a nag reminder (stops further nags)
- `PATCH /reminders/{id}` — Update reminder (body: `{task?, run_at?, last_nagged_at?, fired_at?}`)
- `DELETE /reminders/{id}` — Cancel/delete a reminder

**Nag reminders:** The scheduler polls every 60s for due nags, sends WhatsApp messages, and auto-acknowledges past `nag_until` time. Users can reply "done" on WhatsApp to acknowledge.

### Weather
- `GET /weather/current` - Current weather
- `GET /weather/forecast?days=5` - Weather forecast

### Traffic & Directions
- `GET /traffic/school` - School run traffic info
- `GET /directions?origin=<addr>&destination=<addr>` - Get directions
- `GET /distance?origins=<addr>&destinations=<addr>` - Distance matrix

### Places
- `GET /places/search?q=<query>&location=<lat,lng>` - Search places
- `GET /places/details?place_id=<id>` - Place details
- `GET /places/nearby?location=<lat,lng>&type=<type>` - Nearby places
- `GET /places/autocomplete?input=<text>` - Autocomplete

### EV & Home
- `GET /ev/status` - EV charging status
- `GET /ev/combined` - Combined EV info
- `GET /ring/status` - Ring doorbell status
- `GET /kia/status` - Kia vehicle status

### Utilities
- `GET /fetch-url?url=<url>` - Fetch and parse URL content
- `GET /translate?text=<text>&target=<lang>` - Translate text
- `GET /youtube/search?q=<query>` - Search YouTube
- `GET /geocode?address=<addr>` - Geocode address
- `GET /timezone?location=<lat,lng>` - Get timezone
- `GET /currency?from=<code>&to=<code>&amount=<n>` - Currency conversion
- `GET /calculate?expression=<expr>` - Calculate expression
- `GET /wikipedia?q=<query>` - Wikipedia summary
- `GET /dictionary?word=<word>` - Word definition
- `GET /holidays?country=<code>&year=<year>` - Public holidays
- `GET /sunrise?lat=<lat>&lng=<lng>` - Sunrise/sunset times
- `GET /moon` - Moon phase

### Meal Plan
Weekly meal plan management with Google Sheets import, Gousto email integration, and shopping list generation.

**Read:**
- `GET /meal-plan/current` - Get current week's plan (items + ingredients)
- `GET /meal-plan/week?date=YYYY-MM-DD` - Get plan for week containing date
- `GET /meal-plan/{plan_id}` - Get plan by ID
- `GET /meal-plan/shopping-list?plan_id=<id>` - Get ingredients as shopping list categories (defaults to current week)

**Create:**
- `POST /meal-plan` - Create/update a meal plan with items (body: `{week_start, source, notes?, items: [{date, meal_slot ("dinner"/"lunch"/"breakfast"), adults_meal, kids_meal?, source_tag, recipe_url?, cook_time_mins?, servings?, notes?}]}`). Maps string meal_slot to integer automatically. Powers reminders, "what's for dinner?", and meal ratings.

**Import:**
- `POST /meal-plan/import/sheets?spreadsheet_id=<id>` - Import from Google Sheet (default: Chris's meal plan sheet)
  - Auto-discovers meal plan and ingredients tabs
  - Parses DD/MM dates, detects Gousto/homemade source tags
- `POST /meal-plan/import/csv` - Import from CSV (body: `{csv_data: "Date,Day,Adults,Kids\n...", ingredients_csv: "Category,Item,Qty\n..."}`)
- `POST /meal-plan/import/gousto` - Search Gmail for Gousto order emails, extract recipes, match to meal plan, and scrape+save to Family Fuel DB. Returns `saved_to_family_fuel` (recipe IDs) and `save_errors`.

**Write:**
- `PUT /meal-plan/{plan_id}/ingredients` - Replace ingredients (body: `{ingredients: [{category, item, quantity?, for_recipe?}]}`)
- `POST /meal-plan/shopping-list/generate?plan_id=<id>&title=<title>` - Generate PDF from plan ingredients
- `DELETE /meal-plan/{plan_id}` - Delete a plan (cascades to items and ingredients)

**Templates:**
- `GET /meal-plan/templates` - List all weekly templates
- `GET /meal-plan/templates/default` - Get the default template
- `GET /meal-plan/templates/{name}` - Get a template by name
- `PUT /meal-plan/templates/{name}` - Create/update template (body: `{days: {monday: {portions, max_prep_mins, type, notes}, ...}, is_default: bool}`)
- `DELETE /meal-plan/templates/{name}` - Delete a template

**Preferences:**
- `GET /meal-plan/preferences?profile=default` - Get food preferences
- `PUT /meal-plan/preferences?profile=default` - Update preferences (body: `{dietary?, variety_rules?, cuisine_preferences?, disliked_ingredients?, gousto_nights_per_week?, batch_cook_per_week?, budget_per_week_pence?}`)

**Meal History:**
- `POST /meal-plan/history` - Log a meal (body: `{date, meal_name, recipe_source?, protein_type?, rating?, would_make_again?, notes?}`)
- `GET /meal-plan/history?days=14` - Get recent meal history
- `PATCH /meal-plan/history/{meal_id}/rating` - Rate a meal (body: `{rating, would_make_again?, notes?}`)

**Recipes (Family Fuel):**
- `POST /recipes/extract` — Extract structured recipe data from a URL via Chrome CDP (port 9222)
  - Body: `{url: "https://cooking.nytimes.com/...", auto_save?: false}`
  - Uses Chris's logged-in Chrome session — works with paywalled sites (NYT Cooking, etc.)
  - Extracts Schema.org JSON-LD: name, ingredients with quantities/units, instructions, macros, dietary flags
  - Set `auto_save: true` to save directly to Family Fuel
- `GET /recipes/search?q=<name>&cuisine=<type>&meal_type=<type>&tags=<csv>&limit=20` — Search recipes by name, cuisine, meal type, or tags
- `POST /recipes` — Create a recipe with ingredients + instructions in one call
  - Body: `{recipeName, description?, servings?, prepTimeMinutes?, cookTimeMinutes?, cuisineType?, mealType?: ["dinner"], caloriesPerServing?, proteinPerServing?, carbsPerServing?, fatPerServing?, isVegetarian?, isDairyFree?, containsMeat?, containsSeafood?, freezable?, tags?: ["quick"], recipeSource?, sourceUrl?, ingredients: [{ingredientName, quantity?, unit?, category?, sortOrder?}], instructions: [{stepNumber, instruction, timerMinutes?}]}`
- `GET /recipes/{id}` — Get full recipe with ingredients and instructions
- `PATCH /recipes/{id}/usage` — Increment usage count and set last used date
- `PATCH /recipes/{id}/rating` — Update family rating (body: `{rating}`, 1-10 scale)
- `DELETE /recipes/{id}` — Soft-delete (archive) a recipe

**Surge.sh Deploy:**
- `POST /deploy/surge` — Deploy HTML to a public URL via surge.sh
  - Body: `{html: "<full HTML>", domain: "my-site.surge.sh", filename?: "index.html"}`
  - Returns: `{deployed: true, url: "https://my-site.surge.sh", domain: "my-site.surge.sh"}`

**Shopping Staples:**
- `GET /meal-plan/staples` - List all staples (active_only=true by default)
- `GET /meal-plan/staples/due` - Get staples due to be added (checks frequency vs last_added_date)
- `PUT /meal-plan/staples/{name}` - Add/update staple (body: `{category, quantity?, frequency?, notes?}`)
  - Frequency values: `weekly`, `biweekly`, `monthly`
- `DELETE /meal-plan/staples/{name}` - Remove a staple
- `POST /meal-plan/staples/mark-added` - Mark staples as added (body: `{names: ["milk", "bread"]}`)

**Interactive Shopping List:**
- `POST /meal-plan/shopping-list/html` - Generate interactive HTML shopping list page
  - Body: `{categories: {"Dairy & Eggs": [{item, quantity?, for_recipe?}]}, staples?: [{name, category, quantity?}], gousto_items?: ["item1"], title?, week_start?}`
  - Returns raw HTML — deploy to surge.sh for shareable URL
  - Features: checkbox items with localStorage, grouped by aisle, progress bar, recipe attribution, Gousto exclusion section

**Interactive Meal Plan:**
- `POST /meal-plan/view/html` - Generate interactive HTML meal plan page (shareable weekly view)
  - Body: `{plan: {items: [...], week_start: "..."}, title?}`
  - Returns raw HTML — deploy to surge.sh for shareable URL

### Shopping List
- `POST /shopping-list/generate` - Generate printable shopping list PDF (body: `{categories: {"Dairy": ["Milk"]}, title: "Weekly Shop", output_dir: "..."}`)
  - Defaults to `G:\My Drive\AI Work\Shopping Lists` with timestamped filename
  - Optional `output_dir` to override save location
  - Returns `{status, filename, path}`

### Grocery Shopping (Chrome CDP)
Automates Sainsbury's (and later Ocado) via Chrome DevTools Protocol on port 9222. Requires Chrome running with `--remote-debugging-port=9222` and Chris logged in to the store.

- `GET /grocery/{store}/login-check` — Check if logged in to the store
- `GET /grocery/{store}/search?q=<query>&limit=10` — Search for products
- `GET /grocery/{store}/slots?date=<YYYY-MM-DD>&prefer=<saver|standard>` — Get available delivery slots
  - Returns slots with `booking_key`, `date`, `start`, `end`, `price`, `type` (saver/standard/green)
  - Sorted by preference if `prefer` specified; saver slots are £1-2, standard £4-6.50
- `POST /grocery/{store}/slots/book` — Book a delivery slot (2hr hold)
  - Body: `{booking_key: "<key from slots response>"}`
- `GET /grocery/{store}/trolley` — View current trolley contents (items, prices, subtotal)
- `POST /grocery/{store}/trolley/add-list` — Add shopping list items to trolley
  - Body: `{items: [{name: "chicken breast", quantity?: "500g", category?: "meat"}]}`
  - Auto-adds high-confidence matches (score >= 0.7), returns ambiguous/not-found items for manual resolution

Supported stores: `sainsburys` (Ocado planned).

### Nutrition
- `POST /nutrition/log-meal` - Log meal
- `POST /nutrition/log-water` - Log water
- `DELETE /nutrition/meal?meal_id=<uuid>` - Delete meal/food entry
- `GET /nutrition/water/entries` - Today's water entries with IDs
- `DELETE /nutrition/water?entry_id=<uuid>` - Delete single water entry
- `POST /nutrition/water/reset` - Bulk delete today's water entries
- `GET /nutrition/today` - Today's totals and progress
- `GET /nutrition/today/meals` - Today's meal list
- `GET /nutrition/date?date=YYYY-MM-DD` - Totals for any date
- `GET /nutrition/date/meals?date=YYYY-MM-DD` - Meals for any date
- `GET /nutrition/week` - Weekly summary
- `GET /nutrition/goals` - Nutrition goals
- `PATCH /nutrition/goals` - Update goals
- `GET /nutrition/steps` - Today's steps (Garmin)
- `GET /nutrition/weight` - Latest weight (Withings)
- `GET /nutrition/weight/history?days=30` - Weight history
- `GET /nutrition/favourites` - List meal favourites
- `GET /nutrition/favourite?name=...` - Get favourite
- `POST /nutrition/favourite` - Save favourite
- `DELETE /nutrition/favourite?name=...` - Delete favourite

### Hadley Bricks (HB)

Catch-all proxy: `/hb/{path}` → `localhost:3000/api/{path}` (injects API key automatically).

**Key endpoints:**
- `GET /hb/orders` - Recent orders
- `GET /hb/orders/{id}` - Order details
- `GET /hb/orders/stats` - Order statistics
- `GET /hb/orders/status-summary` - Status summary
- `GET /hb/orders/dispatch-deadlines` - Dispatch deadlines
- `GET /hb/orders/ebay` - eBay orders
- `GET /hb/orders/amazon` - Amazon orders
- `GET /hb/inventory` - Inventory list
- `GET /hb/inventory/summary` - Inventory summary
- `GET /hb/inventory/listing-counts` - Listing counts
- `GET /hb/reports/profit-loss` - P&L report
- `GET /hb/purchases/search` - Search purchases
- `GET /hb/pickups` - Scheduled pickups

**Note:** Any HB API route with `validateAuth()` works via this proxy. Routes using session-only auth will return Unauthorized.

### Voice
STT (speech-to-text), TTS (text-to-speech), and full conversational voice pipeline. All processing runs locally (faster-whisper + Kokoro ONNX).

- `POST /voice/listen` — Transcribe audio to text. Send audio as request body with Content-Type header (wav, ogg, webm, mp3). Returns `{text, format_detected}`
- `POST /voice/speak` — Synthesise text to audio. Body: `{text, voice?: "bm_george", speed?: 1.0}`. Returns audio/wav
- `POST /voice/converse` — Full round-trip: audio in → STT → Peter → TTS → audio out. Returns `{text, reply, audio_url}`. Query params: `sender_name`, `sender_number`, `voice`
- `GET /voice/audio/{filename}` — Serve generated audio files (auto-cleaned after 5 min)
- `GET /voice/voices` — List available TTS voices. Returns `{default, british_male, all}`

**Voices:** British male voices available: `bm_daniel`, `bm_fable`, `bm_george`, `bm_lewis`. Default: `bm_daniel`.

### WhatsApp
- `POST /whatsapp/send?to=<number>&message=<text>` - Send text message
- `POST /whatsapp/send-voice?to=<number>&message=<text>` - Send voice note (TTS) + text message
- `GET /whatsapp/status` - Connection status
- Voice notes: incoming WhatsApp voice notes are auto-transcribed and routed to Peter. Replies include both text and a voice note.

### GCP Monitoring
- `GET /gcp/usage?hours=24` - API request counts and estimated cost from Cloud Monitoring (last N hours)
- `GET /gcp/monthly` - Month-to-date spend estimate with full-month projection and top services breakdown
- Requires service account key at `data/gcp-service-account.json` and `GCP_PROJECT_ID` in .env

### Browser Automation
For sites that block normal HTTP requests (bot protection, Cloudflare, etc.).

**Simple Fetch (any URL, read-only):**
- `GET /browser/fetch?url=<url>&wait_ms=3000` - Fetch any page with real browser, returns visible text

**Full Session Control (for interactions - allowlisted domains only):**
Allowlisted: amazon.co.uk, ebay.co.uk, premierinn.com
- `GET /browser/domains` - List allowed domains
- `POST /browser/session/start` - Start browser session (body: {domain, user_id, channel_id})
- `GET /browser/session/{session_id}` - Get session info
- `POST /browser/session/end` - End session (body: {session_id, save_state})
- `POST /browser/action` - Execute action (body: {session_id, action, params})
  - Actions: navigate, click, click_text, click_role, type, press, scroll, wait
  - Example: `{session_id: "...", action: "click_text", params: {text: "Check availability"}}`
- `GET /browser/screenshot?session_id=<id>&full_page=false` - Take screenshot (base64 PNG)
- `GET /browser/text?session_id=<id>` - Get visible page text

**Example: Check hotel prices**
```
1. POST /browser/session/start {domain: "premierinn.com", user_id: 0, channel_id: 0}
2. POST /browser/action {session_id: "...", action: "navigate", params: {url: "https://..."}}
3. POST /browser/action {session_id: "...", action: "click_text", params: {text: "Check availability"}}
4. POST /browser/action {session_id: "...", action: "type", params: {text: "14/02/2026"}}
5. GET /browser/text?session_id=... (get results)
6. POST /browser/session/end {session_id: "...", save_state: false}
```

### Investment ML Pipeline
- `POST /investment/retrain` - Trigger full Python/LightGBM pipeline (build → features → train → score)
- `POST /investment/retrain?step=build` - Just rebuild training data from price snapshots
- `POST /investment/retrain?step=features` - Just re-engineer features
- `POST /investment/retrain?step=train` - Just retrain LightGBM models
- `POST /investment/retrain?step=score` - Just re-score active sets

**Note:** Full pipeline takes ~5-10 minutes. Returns stdout/stderr and return code. Pipeline lives in `hadley-bricks/scripts/ml/`.

### Schedule Management
- `GET /schedule` - Read current SCHEDULE.md content (raw markdown)
- `PUT /schedule` - Update SCHEDULE.md and trigger reload (body: `{content, reason}`)
- `POST /schedule/reload` - Trigger schedule reload without editing
- `POST /schedule/run/{skill}?channel=#peterbot` - Manually trigger a skill

**Atomic Job CRUD:**
- `GET /schedule/jobs` - List all jobs parsed from SCHEDULE.md (structured JSON)
- `PATCH /schedule/jobs/{skill}` - Update job fields (body: `{schedule?, channel?, enabled?, name?}`)
- `POST /schedule/jobs` - Add job (body: `{name, skill, schedule, channel, enabled?, section?}`)
- `DELETE /schedule/jobs/{skill}` - Remove a job from SCHEDULE.md

**Schedule Pauses:**
- `GET /schedule/pauses` - List active pauses (auto-filters expired)
- `POST /schedule/pauses` - Create pause (body: `{skills, reason, resume_at, paused_by}`)
  - `skills`: list of skill names or `["*"]` for all
- `DELETE /schedule/pauses/{id}` - Remove pause early (unpause)
- `GET /schedule/pauses/check/{skill}` - Check if a skill is paused

**Pending Actions (Confirmation Flow):**
- `POST /schedule/pending-actions` - Create pending action (body: `{type, sender_number, sender_name, description, api_call}`)
- `GET /schedule/pending-actions?sender=<number>` - List pending for sender
- `POST /schedule/pending-actions/{id}/confirm` - Execute the stored API call
- `POST /schedule/pending-actions/{id}/cancel` - Cancel the action

### Vinted Collections
- `GET /vinted/collections?days=7&mark_reported=true` - Get Vinted parcels ready to collect
  - Searches Gmail for `no-reply@vinted.co.uk` "waiting for you" notifications
  - Parses item name, delivery service (InPost/Evri/Royal Mail/Yodel/DPD), and pickup location
  - Deduplicates against `data/vinted_collections_reported.json`
  - Returns `{collections: [{email_id, item, date, service, location, is_new}], new_count, total_count}`
  - `days` (1-90, default 7): how far back to search
  - `mark_reported` (default true): save new email IDs to dedup file

### Fitness Tracking (Post-Japan Cut)

All routes in `hadley_api/fitness_routes.py`. See `docs/playbooks/FITNESS.md` for the full playbook.

- `GET /fitness/programme` — active programme + current week/day number
- `GET /fitness/today` — today's prescribed workout + calorie/protein/steps targets
- `GET /fitness/dashboard` — full daily status (trend weight, nutrition, steps, today's workout, mobility, flags)
- `GET /fitness/weekly-review` — Sunday review bundle with adherence + adjustment
- `GET /fitness/trend?days=30` — smoothed weight trend (7-day SMA, EMA, linear slope, stall detection)
- `GET /fitness/exercises?category=push` — exercise library (optional category filter)
  - Each exercise now includes `video_url` (YouTube search link), `instructions` (5-step how-to), and `equipment` notes
  - Response: `{exercises, by_category: {push, pull, legs, core, conditioning, mobility}, category_order, count}`
- `GET /fitness/mobility/routine` — the fixed 10-minute daily mobility flow
  - Joins the static routine against the exercise library so each move carries name, form cue, instructions, video URL, equipment, muscle group, and per-move duration
  - Response: `{name, total_duration_s, total_duration_min, move_count, moves: [...]}`
- `GET /fitness/mobility/today` — today's slot status + 7-day history + streak
  - Response: `{today: {morning_done, evening_done, ...}, streak_days, history_7d: [{date, done}]}`
  - Streak walks back from today; today-not-done-yet is a grace day (doesn't break the streak)
- `GET /fitness/advice` — PT/nutritionist-quality advisor
  - Cross-references nutrition, weight trend, recovery (sleep, HRV, resting HR), training load (RPE trend), mobility, and programme context
  - Returns structured advice items sorted by severity: `{advice: [{severity, category, headline, detail, action}], snapshot: {...}, counts: {warning, caution, info, positive}}`
  - 23 rules covering: energy balance (deficit depth + training day context), protein adequacy, hydration, weight rate-of-loss, stall/diet-break detection, sleep+training interaction, resting HR trends, HRV status, RPE creep, missed sessions, mobility streak
  - Peter runs this 3x daily (12:00, 16:00, 20:00) and alerts on warning/caution items
- `POST /fitness/workout` — log session + per-exercise sets (auth required)
  - Body: `{session_type, duration_min, rpe, notes, sets: [{exercise_slug, set_no, reps, hold_s}]}`
- `POST /fitness/mobility` — log a mobility slot (auth required)
  - Body: `{slot: "morning"|"evening"|"adhoc", duration_min, routine}`
- `POST /fitness/programme/start` — one-shot programme init (auth required)
  - Body: `{start_date, current_weight_kg, target_loss_kg, duration_weeks}`
  - Archives old active programmes + "Hit 80kg"/"Lose weight" goals
  - Computes TDEE (Mifflin-St Jeor + Garmin activity factor)
  - Creates 6 accountability goals (weight/calories/protein/steps/strength/mobility)
- `POST /fitness/programme/recalibrate` — refresh calorie/protein targets from latest weight (auth required)
  - Body (all optional): `{current_weight_kg, avg_steps, deficit_kcal}` — defaults to 7-day trend weight + 7-day step avg
  - Recomputes Mifflin-St Jeor BMR, TDEE, target calories, target protein
  - Updates the active programme row in-place (tdee_kcal, daily_calorie_target, daily_protein_g)
  - Returns `{old, new, weight_used_kg, bmr, activity_factor, deficit_kcal}`
- `POST /fitness/weekly-checkin` — persist a Sunday snapshot (auth required)

Tables:
- `fitness_programmes` — programme header (start, target, TDEE, targets)
- `fitness_exercises` — exercise library (seeded with 35+ bodyweight movements)
- `fitness_workout_sessions` + `fitness_workout_sets` — workout logs
- `fitness_mobility_sessions` — mobility slots (morning/evening unique per day)
- `fitness_weekly_checkins` — persisted Sunday snapshots

## Environment Variables

Uses the same `.env` as the main Discord bot:
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`
- `NOTION_API_KEY`
- `NOTION_TODOS_DATABASE_ID`
- `NOTION_IDEAS_DATABASE_ID`

### Model Provider

- `GET /model/status` - Get current model provider status (claude/kimi, reason, timestamps)
- `PUT /model/switch` - Switch provider: `{"provider": "claude"|"kimi", "reason": "manual"}`
- `PUT /model/auto-switch` - Toggle auto-recovery: `{"enabled": true|false}`

### Life Admin

Proactive life admin obligation tracking and alerting.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | /life-admin/obligations | No | List obligations (query: status, category) |
| GET | /life-admin/obligations/{id} | No | Get single obligation |
| POST | /life-admin/obligations | Yes | Create obligation |
| PATCH | /life-admin/obligations/{id} | Yes | Update obligation |
| DELETE | /life-admin/obligations/{id} | Yes | Delete obligation |
| POST | /life-admin/obligations/{id}/action | Yes | Mark as actioned (auto-advances recurrence) |
| POST | /life-admin/obligations/{id}/snooze | Yes | Snooze until date |
| GET | /life-admin/alerts | No | Computed alerts by urgency tier |
| GET | /life-admin/dashboard | No | All obligations grouped by status |
| POST | /life-admin/alerts/record | Yes | Record alert sent (prevents re-sending) |
| POST | /life-admin/scans | Yes | Record email scan result |
| GET | /life-admin/scans | No | Recent scan history |

### System Health (Job Monitoring)

- `GET /jobs/health?hours=24` - Unified job health across DM + HB. Returns per-system stats: total, success, errors, success_rate, failures[], per_job[]. DM data from SQLite job_history.db, HB data from Supabase job_execution_history via HB API proxy.

## Notes

- All Google APIs have full CRUD access (read, create, update, delete)
- Calendar dates: use `YYYY-MM-DD` for all-day events, `YYYY-MM-DDTHH:MM` for timed events
- Rate limits apply to some endpoints (e.g., calendar create: 20/minute)
