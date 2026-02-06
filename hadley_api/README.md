# Hadley API

Local API proxy for Peter's real-time queries. Full CRUD access to Google services.

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
- `POST /gmail/send?to=<email>&subject=<text>&body=<text>` - Send email
- `POST /gmail/draft?to=<email>&subject=<text>&body=<text>` - Create draft
- `POST /gmail/reply?message_id=<id>&body=<text>` - Reply to email
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
  - `summary` (required), `start`, `end`, `location`, `description`
  - `color` - 1=lavender, 2=sage, 3=grape, 4=flamingo, 5=banana, 6=tangerine, 7=peacock, 8=graphite, 9=blueberry, 10=basil, 11=tomato
  - `visibility` - default, public, private, confidential
  - `transparency` - opaque (busy) or transparent (free)
  - `guests_can_modify`, `guests_can_invite`, `guests_can_see_guests` (booleans)
  - `reminders` - minutes comma-separated (e.g., "10,60" for 10min and 1hr)
- `POST /calendar/quickadd?text=Meeting tomorrow at 3pm` - Quick add event
- `POST /calendar/recurring?summary=<title>&start=<date>&rrule=<rule>` - Create recurring event
- `POST /calendar/invite?event_id=<id>&email=<email>` - Add attendee
- `PUT /calendar/event` - Update event with full options:
  - `id` (required), `summary`, `start`, `end`, `location`, `description`
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
- `POST /drive/create?name=<name>&content=<text>` - Create file
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

**Write:**
- `POST /reminders` — Create reminder (body: `{task, run_at, user_id, channel_id}`)
  - `run_at` must be ISO 8601 and in the future
  - Returns the created reminder object
- `PATCH /reminders/{id}` — Update reminder (body: `{task?, run_at?}`)
  - Only updates provided fields; `run_at` must be in the future
- `DELETE /reminders/{id}` — Cancel/delete a reminder

**Note:** The Discord bot's polling loop picks up new reminders every 60 seconds, so API-created reminders will be scheduled automatically without a bot restart.

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

### WhatsApp
- `POST /whatsapp/send?to=<number>&message=<text>` - Send message
- `GET /whatsapp/status` - Connection status

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

### Schedule Management
- `GET /schedule` - Read current SCHEDULE.md content
- `PUT /schedule` - Update SCHEDULE.md and trigger reload (body: `{content, reason}`)
- `POST /schedule/reload` - Trigger schedule reload without editing

## Environment Variables

Uses the same `.env` as the main Discord bot:
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`
- `NOTION_API_KEY`
- `NOTION_TODOS_DATABASE_ID`
- `NOTION_IDEAS_DATABASE_ID`

## Notes

- All Google APIs have full CRUD access (read, create, update, delete)
- Calendar dates: use `YYYY-MM-DD` for all-day events, `YYYY-MM-DDTHH:MM` for timed events
- Rate limits apply to some endpoints (e.g., calendar create: 20/minute)
