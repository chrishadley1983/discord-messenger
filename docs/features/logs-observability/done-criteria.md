# Done Criteria: Logs Observability Page (Datadog-Inspired)

**Created:** 2026-03-19
**Author:** Define Done Agent + Chris
**Status:** DRAFT
**Project:** Discord-Messenger (Peter Dashboard)
**Location:** `C:\Users\Chris Hadley\claude-projects\Discord-Messenger`

## Feature Summary

Transform the Peter Dashboard logs page (`/#/logs`) from a flat text dump into a Datadog-inspired observability tool with live tail, pattern grouping, severity coloring, log volume timeline, faceted filtering, structured detail expansion, and noise suppression.

---

## Success Criteria

### F1: Log Volume Timeline (Histogram Bar Chart)

- **Blockers:** None
- **Criterion:** A stacked bar chart at the top of the logs page shows log volume over time, bucketed by severity
- **Evidence:**
  - New endpoint `GET /api/logs/histogram?hours=6&buckets=60` returns array of `{ timestamp, counts: { DEBUG, INFO, WARNING, ERROR } }`
  - Frontend renders a stacked bar chart (D3 or inline SVG), ~80px tall, 100% width
  - Bars colored by severity: grey (DEBUG), teal (INFO), amber (WARNING), red (ERROR)
  - Hovering a bar shows tooltip with bucket time + count breakdown
  - Clicking a bar filters the log table to that time window
  - Chart auto-refreshes with new data
  - Default: last 6 hours, 60 buckets (6-minute intervals)
- **Implementation notes:**
  - Backend: New `histogram` endpoint in `logs.py`. Parse timestamps only (skip message parsing) for speed. Bucket into intervals.
  - Frontend: `LogsTimeline` sub-component above log table. D3 scales for x/y. SVG `<rect>` for bars.
  - Colors: `--text-muted` (DEBUG), `--accent` (INFO), `--status-paused` (WARNING), `--status-error` (ERROR)

---

### F2: Severity Color Coding and Visual Hierarchy

- **Blockers:** None
- **Criterion:** Every log row has severity-based visual styling making the page instantly scannable
- **Evidence:**
  - 3px left border per severity: transparent (DEBUG), `--accent` (INFO), amber (WARNING), red (ERROR)
  - WARNING rows have faint amber background tint
  - ERROR rows have faint red background tint
  - `[LEVEL]` rendered as colored pill/badge (not plain text)
  - Level colors consistent between histogram (F1), log rows, and facet sidebar (F3)
- **Implementation notes:**
  - CSS classes: `.log-entry.level-error`, `.log-entry.level-warning`, etc.
  - Level badge: `<span class="log-level-badge level-error">ERROR</span>` with `border-radius`, `padding: 1px 6px`, `font-size: 10px`
  - Add CSS RGB custom properties for rgba() backgrounds: `--status-error-rgb`, `--status-paused-rgb`

---

### F3: Faceted Filtering Sidebar

- **Blockers:** F2
- **Criterion:** A left sidebar panel shows clickable facets with counts, enabling multi-select filtering
- **Evidence:**
  - New endpoint `GET /api/logs/facets?hours=6` returns `{ sources: [{name, count}], levels: [{name, count}], top_patterns: [{pattern, count, sample}] }`
  - Sidebar ~220px wide, left of log table, scrollable
  - **Sources section:** Each source with count badge, multi-select toggle
  - **Levels section:** Each level with colored dot + count, multi-select toggle
  - **Top Patterns section:** Top 5-10 frequent message patterns, clickable to filter
  - Facet counts update when filters change (cross-filtering)
  - Sections collapsible/expandable
  - Mobile: hides into slide-out drawer
- **Implementation notes:**
  - Backend: Reuse `_parse_logs_from_file`, aggregate into counts. `top_patterns` reuses regex normalization from `/errors`.
  - Frontend: `LogsView.render()` changes to `grid-template-columns: 220px 1fr`. Track `this.activeSources` and `this.activeLevels` as Sets.

---

### F4: Log Pattern Grouping

- **Blockers:** None
- **Criterion:** Identical/similar consecutive log lines are auto-collapsed into a single row with repeat count
- **Evidence:**
  - New endpoint param: `GET /api/logs/unified?group=true`
  - Each entry gains `group_key` (normalized message) and `group_count`
  - Consecutive entries with same `group_key` collapse: `[timestamp] [source] [level] message (x15)` with count in grey pill
  - Clicking grouped entry expands to show all individual entries with timestamps
  - Toggle button in toolbar switches grouping on/off (default: on)
  - Pattern normalization strips: IP:port, hex IDs, UUIDs, session IDs, numeric sequences
  - Multi-line tracebacks grouped with preceding error line into single expandable entry
- **Implementation notes:**
  - Backend: Grouping logic after filtering in `get_unified_logs`. Shared `normalize_message()` function used by both `/unified?group=true` and `/errors`.
  - Frontend: `.log-entry-grouped` class with "stacked" visual. `<details>` or JS toggle for expansion.

---

### F5: Live Tail with Auto-Scroll

- **Blockers:** F2
- **Criterion:** Real-time log streaming with smart auto-scroll behavior
- **Evidence:**
  - "Live Tail" toggle button in toolbar (green dot when active)
  - When active: polls `GET /api/logs/unified?since=<last_timestamp>&limit=50` every 2 seconds
  - New entries animate in at bottom with green highlight fade (1s)
  - Auto-scrolls to bottom on each batch
  - Scrolling up >50px pauses auto-scroll; floating "Jump to live" pill appears
  - Clicking pill resumes auto-scroll
  - Live tail respects current filters
  - Auto-pauses on tab switch, resumes on return
  - Header shows "Showing N logs (live)" with pulsing green dot
  - High volume indicator if >100 entries per poll
- **Implementation notes:**
  - Frontend only — backend already supports `since`. Store `this.lastTimestamp`.
  - Auto-scroll detection: `scrollHeight - scrollTop - clientHeight < 50`.
  - CSS: `@keyframes log-entry-flash { from { background: var(--accent-light); } to { background: transparent; } }`

---

### F6: Structured Log Detail Panel

- **Blockers:** F4
- **Criterion:** Clicking a log entry opens detail panel with structured metadata
- **Evidence:**
  - Panel header shows level badge + timestamp
  - Body shows: full message (monospace, word-wrap), metadata key-value table, source badge, collapsible raw log line(s)
  - "Show surrounding logs" button loads 5 lines before/after from same source
  - Tracebacks displayed in code block with Python file paths highlighted
  - HTTP status codes color-coded (2xx green, 4xx amber, 5xx red)
- **Implementation notes:**
  - Reuse `DetailPanel.open()`. `LogEntry.to_dict()` already includes `metadata`.
  - Backend: Add `raw_lines` to grouped response. New endpoint `GET /api/logs/context?source=<name>&timestamp=<iso>&lines=5`.

---

### F7: Search with Structured Query Syntax

- **Blockers:** F3
- **Criterion:** Search box supports structured queries like `source:bot level:error port bind`
- **Evidence:**
  - Qualifiers: `source:<name>`, `level:<level>`, `module:<name>`, `status:<code>`
  - Free text combined with AND for message search
  - Autocomplete dropdown on qualifier typing (e.g. `source:` shows sources)
  - Active query shown as removable chips below search bar
  - Facet clicks (F3) update chips and vice versa
  - Debounced at 300ms
- **Implementation notes:**
  - Frontend parser: `/(\w+):(\S+)/g` extracts qualifiers, remainder = free text.
  - Chip bar: `<div class="query-chips">` below search input.
  - Backend already supports `source`, `level`, `search` params — frontend maps parsed query to params.

---

### F8: Saved Views / Quick Filters

- **Blockers:** F3, F7
- **Criterion:** Pre-built one-click filter presets as pill buttons above the log table
- **Evidence:**
  - Pills: "All", "Errors Only", "Warnings+", "Startup", "Scheduler", "HTTP Requests", "No Health Checks"
  - Each applies predefined filter combination:
    - **All**: Clear filters
    - **Errors Only**: `level:ERROR,CRITICAL`
    - **Warnings+**: `level:WARNING,ERROR,CRITICAL`
    - **Startup**: search for "Starting", "logging in", "connected to Gateway"
    - **Scheduler**: search for scheduler/job/cron, source:bot
    - **HTTP Requests**: source:hadley_api
    - **No Health Checks**: exclude `GET /health` lines
  - Active view highlighted with accent color
  - Filters reflected in facets (F3) and search chips (F7)
  - Custom saved views via localStorage
- **Implementation notes:**
  - Array of view definitions with `{ name, icon, filters }`. Clicking sets filter state.
  - "No Health Checks" needs `exclude` param on backend or frontend post-filtering.
  - localStorage key: `peter_logs_saved_views`

---

### F9: Multi-line Traceback Collapsing

- **Blockers:** F4, F2
- **Criterion:** Python tracebacks are collapsed into single expandable rows
- **Evidence:**
  - Detects `Traceback (most recent call last):` blocks + continuation lines
  - Collapsed: `[timestamp] [ERROR] [source] ExceptionType: message (3 frames)` with expand icon
  - Expanded: full traceback in monospace code block, file paths highlighted, final exception line bold red, frame count badge
  - `RequestsDependencyWarning` spam auto-collapsed with "(repeated)" indicator
- **Implementation notes:**
  - Backend: Second pass in parser merges traceback blocks into parent error entry. `LogEntry.extra_lines: List[str]` for frames.
  - `NOISE_PATTERNS` list: `RequestsDependencyWarning`, `BigQuery billing unavailable`. Entries get `noise: true` flag.

---

### F10: Noise Suppression Toggle

- **Blockers:** F4, F9
- **Criterion:** Toggle to hide known noise patterns, focusing on what matters
- **Evidence:**
  - "Hide Noise" toggle in toolbar (eye-slash icon)
  - Suppresses: `GET /health`, `RequestsDependencyWarning`, `BigQuery billing unavailable`, `discord.gateway RESUMED`
  - Inline indicator: "N noise lines hidden" where suppressed lines would be
  - Clicking indicator shows them dimmed
  - Default: noise suppression ON
  - Patterns configurable via `NOISE_PATTERNS` list in backend
- **Implementation notes:**
  - Backend: `suppress_noise` param on `/unified`. Matching entries get `noise: true` flag (still returned for accurate counts).
  - Frontend: thin grey bar `<div class="log-noise-indicator">47 noise lines hidden</div>`
  - State in localStorage.

---

## Dependency Graph

```
F1 (Histogram)          -- no deps
F2 (Severity Colors)    -- no deps
F3 (Facet Sidebar)      -- F2
F4 (Pattern Grouping)   -- no deps
F5 (Live Tail)          -- F2
F6 (Detail Panel)       -- F4
F7 (Query Syntax)       -- F3
F8 (Saved Views)        -- F3, F7
F9 (Traceback Collapse) -- F4, F2
F10 (Noise Suppression) -- F4, F9
```

## Implementation Order (Suggested)

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | F2, F4 | Severity colors + pattern grouping (highest impact, lowest complexity) |
| 2 | F1 | Log volume histogram (signature Datadog visual) |
| 3 | F9, F10 | Traceback collapsing + noise suppression (noise cleanup) |
| 4 | F3, F5 | Faceted sidebar + live tail (interactive power features) |
| 5 | F6 | Structured detail panel |
| 6 | F7, F8 | Query syntax + saved views (polish) |

## Files to Modify

| File | Changes |
|------|---------|
| `peter_dashboard/api/logs.py` | New endpoints: `/histogram`, `/facets`, `/context`. Grouping logic. Traceback merging. `NOISE_PATTERNS`. `normalize_message()`. `suppress_noise` param. |
| `peter_dashboard/app.py` | Register new endpoints. |
| `peter_dashboard/static/js/app.js` | Rewrite `LogsView` (~lines 3560-3707): `LogsTimeline`, `renderFacets()`, `renderLogEntry()` with severity/grouping/traceback, live tail polling, query parser, saved views, noise toggle. |
| `peter_dashboard/static/css/main.css` | New: `.log-entry.level-*`, `.log-level-badge`, `.logs-timeline`, `.logs-facets`, `.facet-item`, `.log-entry-grouped`, `.log-entry-flash`, `.log-traceback`, `.log-noise-indicator`, `.query-chips`, `.saved-view-pills`, `.live-indicator`. RGB custom properties. |
| `bot.py` | (Root cause fixes) `warnings.filterwarnings`, WhatsApp port check, `_create_logged_task()`. |
| `integrations/whatsapp.py` | Belt-and-suspenders warning filter. |

## Documentation Updates

| File | Update |
|------|--------|
| `CLAUDE.md` (project) | Add note: "Background tasks use `_create_logged_task()` to ensure exceptions are logged" |
| `hadley_api/README.md` | N/A (dashboard endpoints, not Hadley API) |
