# Done Criteria: Skills Directory

**Created:** 2026-03-19
**Author:** Define Done Agent + Chris
**Status:** DRAFT
**Project:** Discord-Messenger (Peter Dashboard)
**Location:** `C:\Users\Chris Hadley\claude-projects\Discord-Messenger`

## Feature Summary

Expand the Peter Dashboard Skills view (`localhost:5000/#/skills`) from showing only Peterbot skills (~80) to a unified **Skills Directory** aggregating ~192 skills from 4 sources: Peterbot skills (WSL), global skills (Windows), project commands (per-project `.claude/commands/`), and global commands. Includes multi-axis filtering, source/project badges, shared command grouping, and a stats bar.

---

## Source Paths

| Source | Path | Runs On | Count |
|--------|------|---------|-------|
| Peterbot Skills | `domains/peterbot/wsl_config/skills/*/SKILL.md` (symlinked to WSL) | WSL2 | ~80 |
| Global Skills | `C:\Users\Chris Hadley\.skills\skills\*/SKILL.md` | Windows | 12 |
| Project Commands | `C:\Users\Chris Hadley\claude-projects\<project>\.claude\commands\*.md` | Windows | ~65 |
| Global Commands | `C:\Users\Chris Hadley\.claude\commands\*.md` | Windows | 2 |

### Known Projects with Commands

| Project | Slug | Command Count |
|---------|------|---------------|
| discord-messenger | `discord-messenger` | 14 |
| hadley-bricks-inventory-management | `hadley-bricks-im` | 11 |
| hadley-bricks-shopify | `hadley-bricks-shopify` | 10 |
| peterbot-mem | `peterbot-mem` | 14 |
| family-meal-planner | `family-meal-planner` | 5 |
| finance-tracker | `finance-tracker` | 3 |
| Football Prediction Game | `football-prediction-game` | 1 |
| japan-family-guide | `japan-family-guide` | 1 |

---

## Success Criteria

### Backend API

#### F1: Directory Endpoint — Peterbot Skills
- **Blockers:** None
- **Criterion:** `GET /api/skills/directory` returns all Peterbot skills with standardised schema
- **Schema per entry:**
  ```json
  {
    "id": "peterbot::morning-briefing",
    "name": "morning-briefing",
    "description": "AI and Claude news morning briefing",
    "source": "peterbot",
    "project": null,
    "path": "domains/peterbot/wsl_config/skills/morning-briefing/SKILL.md",
    "runs_on": "wsl",
    "type": "scheduled|triggered|conversational|command",
    "triggers": ["ai news", "claude news", "briefing"],
    "scheduled": true,
    "conversational": true,
    "channel": null,
    "category": null,
    "last_modified": "2026-03-15T10:30:00Z"
  }
  ```
- **Evidence:** Response includes all skills from `manifest.json` (currently 80 entries). Each entry has `source: "peterbot"`, `runs_on: "wsl"`, and metadata parsed from SKILL.md frontmatter or manifest.json.
- **Implementation notes:**
  - Use existing `manifest.json` as primary source (already has triggers, description, scheduled, conversational, channel)
  - Read `manifest.json` from the Windows-side symlink path `domains/peterbot/wsl_config/skills/manifest.json` directly (no WSL call needed)
  - Fall back to WSL `find` + `parse_skill_metadata()` only if manifest is missing
  - `last_modified` from file stat on `SKILL.md`
  - `type` derived: if `scheduled=true` -> "scheduled", if triggers non-empty -> "triggered", if `conversational=true` -> "conversational"
  - `category` can be null initially (F7 adds categorisation)

#### F2: Directory Endpoint — Global Skills
- **Blockers:** F1
- **Criterion:** `GET /api/skills/directory` also returns all 12 global skills from `C:\Users\Chris Hadley\.skills\skills\`
- **Evidence:** Response includes entries with `source: "global-skill"`, `runs_on: "windows"`, name and description parsed from each `SKILL.md`.
- **Implementation notes:**
  - Scan `~/.skills/skills/*/SKILL.md` using `pathlib.Path` (Windows filesystem, no WSL needed)
  - Reuse `parse_skill_metadata()` for SKILL.md parsing
  - Global skills have no triggers/schedule typically — set `type: "command"`
  - `last_modified` from `os.path.getmtime()`

#### F3: Directory Endpoint — Project Commands
- **Blockers:** F1
- **Criterion:** `GET /api/skills/directory` also returns all project commands from `<project>/.claude/commands/*.md`
- **Evidence:** Response includes entries with `source: "project-command"`, `project` field set (e.g. `"discord-messenger"`), `runs_on: "windows"`, `type: "command"`.
- **Implementation notes:**
  - Hardcoded project list with display names (the 8 projects listed above)
  - Scan each `<project>/.claude/commands/*.md`
  - Name derived from filename (e.g. `code-review.md` -> `code-review`)
  - Description: first non-heading, non-empty line of the markdown file (or first 120 chars)
  - No triggers, not scheduled — always `type: "command"`
  - `id` format: `project-command::discord-messenger::code-review`

#### F4: Directory Endpoint — Global Commands
- **Blockers:** F1
- **Criterion:** `GET /api/skills/directory` also returns the 2 global commands from `~/.claude/commands/`
- **Evidence:** Response includes `bug-hunt` and `frontend-design` with `source: "global-command"`, `runs_on: "windows"`, `type: "command"`.
- **Implementation notes:**
  - Scan `~/.claude/commands/*.md`
  - Same parsing as project commands
  - `id` format: `global-command::bug-hunt`

#### F5: Shared Command Grouping
- **Blockers:** F3
- **Criterion:** Commands that exist in multiple projects are grouped in the response with a `shared_with` field listing all projects that have the same command name
- **Evidence:** `code-review` appears once in the response (not 8 times) with `shared_with: ["discord-messenger", "hadley-bricks-im", "hadley-bricks-shopify", "peterbot-mem", "family-meal-planner", "finance-tracker", "football-prediction-game"]` and `project_count: 7`
- **Implementation notes:**
  - After collecting all project commands, group by name
  - If a command name appears in 2+ projects, merge into a single entry:
    - `project`: first project alphabetically (or null)
    - `shared_with`: sorted list of all project slugs
    - `project_count`: length of shared_with
    - `source`: remains `"project-command"`
  - Unique commands (e.g. `purchase-inventory` in hadley-bricks-im only) remain as single entries with `shared_with: ["hadley-bricks-im"]`, `project_count: 1`

#### F6: Response Caching
- **Blockers:** F5
- **Criterion:** Directory endpoint caches results for 60 seconds to avoid repeated filesystem scans
- **Evidence:** Two rapid requests to `/api/skills/directory` return identical results without re-scanning the filesystem (verified by timing — second request < 10ms)
- **Implementation notes:**
  - Simple in-memory cache with TTL (dict + timestamp)
  - `GET /api/skills/directory?refresh=true` bypasses cache
  - Cache key includes no parameters (single global cache)

#### F7: Category Assignment
- **Blockers:** F1
- **Criterion:** Peterbot skills have a `category` field assigned based on name prefix or a static mapping
- **Evidence:** `hb-*` skills have `category: "Hadley Bricks"`, `health-*` and `weekly-health` etc. have `category: "Health & Fitness"`, etc.
- **Implementation notes:**
  - Static mapping dict in Python:
    ```
    hb-* / hadley-bricks / instagram-* / vinted -> "Hadley Bricks"
    health-* / weekly-health / monthly-health / hydration / nutrition-* -> "Health & Fitness"
    kids-* / school-* / spelling-* / practice-* / pocket-money -> "Family & Kids"
    football-* / cricket-* / spurs-* / pl-results / saturday-sport -> "News & Sport"
    meal-* / cooking-* / recipe-* / price-scanner / daily-recipes / grocery-* / shopping-list-* -> "Food & Cooking"
    news / morning-briefing / morning-laughs / youtube-digest / knowledge-digest -> "Daily Briefings"
    balance-* / api-usage / subscription-* / property-* -> "Finance"
    system-health / security-* / whatsapp-health / heartbeat / parser-* / morning-quality-* / self-reflect -> "System & Ops"
    remind / purchase / daily-thoughts / chrome-cdp / ballot-* -> "Utilities"
    github-* -> "Development"
    ```
  - Unmatched skills get `category: "Other"`
  - Global skills, project commands, global commands get `category: null` (not applicable)

#### F8: Detail Endpoint Expansion
- **Blockers:** F1, F2, F3, F4
- **Criterion:** `GET /api/skills/directory/{id}` returns full content for any skill/command across all sources
- **Evidence:** `GET /api/skills/directory/peterbot::morning-briefing` returns full SKILL.md content. `GET /api/skills/directory/project-command::discord-messenger::code-review` returns the command markdown. `GET /api/skills/directory/global-skill::send-email` returns the SKILL.md.
- **Implementation notes:**
  - Parse the `id` to determine source and resolve file path
  - `peterbot::*` -> read from `domains/peterbot/wsl_config/skills/{name}/SKILL.md`
  - `global-skill::*` -> read from `~/.skills/skills/{name}/SKILL.md`
  - `project-command::*::*` -> read from `~/claude-projects/{project}/.claude/commands/{name}.md`
  - `global-command::*` -> read from `~/.claude/commands/{name}.md`
  - Return `{ id, name, source, content, path, last_modified, ...metadata }`

---

### Frontend — Filter Bar

#### F9: Source Filter Dropdown
- **Blockers:** F5 (needs grouped data)
- **Criterion:** A dropdown above the skills grid allows filtering by source: All / Peterbot / Global Skills / Project Commands / Global Commands
- **Evidence:** Selecting "Peterbot" shows only Peterbot skills. Selecting "Project Commands" shows only project commands. Count updates.
- **Implementation notes:**
  - `<select>` element with `onchange` handler
  - Filters the loaded `this.skills` array client-side
  - Persists selection while search is also active (combined filtering)

#### F10: Type Filter Dropdown
- **Blockers:** F9
- **Criterion:** A dropdown filters by type: All / Scheduled / Triggered / Conversational / Command
- **Evidence:** Selecting "Scheduled" shows only skills where `scheduled: true`. "Command" shows entries where `type: "command"`.
- **Implementation notes:**
  - `type` field from API determines filtering
  - Multiple types can apply to one skill (e.g. scheduled + conversational) — show if ANY selected type matches

#### F11: Project Filter Dropdown
- **Blockers:** F9
- **Criterion:** A dropdown filters by project: All / each project name. Only visible/relevant when "Project Commands" source is selected (or "All")
- **Evidence:** Selecting "discord-messenger" shows only commands from that project (including shared commands that include discord-messenger in `shared_with`)
- **Implementation notes:**
  - Populated from unique project slugs in the data
  - When source filter is "Peterbot" or "Global Skills", project filter is disabled/hidden
  - Shared commands match if the selected project is in `shared_with`

#### F12: Category Filter Dropdown
- **Blockers:** F7, F9
- **Criterion:** A dropdown filters by category: All / Hadley Bricks / Health & Fitness / etc. Only relevant for Peterbot skills.
- **Evidence:** Selecting "Hadley Bricks" shows only skills with `category: "Hadley Bricks"`
- **Implementation notes:**
  - Populated from unique categories in the data
  - Disabled/hidden when source is not "Peterbot" or "All"

#### F13: Combined Filtering
- **Blockers:** F9, F10, F11, F12
- **Criterion:** All filters (source, type, project, category) and search text work together as AND conditions
- **Evidence:** Setting source="Peterbot" + type="Scheduled" + search="health" shows only Peterbot scheduled skills matching "health" (e.g. health-digest, weekly-health, monthly-health)
- **Implementation notes:**
  - Single `applyFilters()` method chains all conditions
  - Search still matches against name, description, and triggers

---

### Frontend — Card Improvements

#### F14: Source Badge on Cards
- **Blockers:** F1
- **Criterion:** Each skill card shows a coloured source badge: "Peterbot" (indigo), "Global Skill" (teal), "Project Command" (amber), "Global Command" (rose)
- **Evidence:** Cards visually distinguish between sources at a glance
- **Implementation notes:**
  - New `.skill-badge-source-*` CSS classes for each source colour
  - Badge appears in the card's badges row alongside existing scheduled/trigger/chat badges

#### F15: Project Badge on Cards
- **Blockers:** F5
- **Criterion:** Project command cards show which project(s) they belong to. Shared commands show "N projects" badge.
- **Evidence:** `code-review` card shows "7 projects" badge. `purchase-inventory` shows "hadley-bricks-im" badge. Peterbot skills show no project badge.
- **Implementation notes:**
  - If `project_count > 1`: show `"${project_count} projects"` badge
  - If `project_count === 1`: show project slug badge
  - If no project: no badge

#### F16: Runs-On Indicator
- **Blockers:** F1
- **Criterion:** Cards show a subtle indicator for where the skill runs: "WSL" or "Win"
- **Evidence:** Peterbot skills show "WSL" tag. All others show "Win" tag.
- **Implementation notes:**
  - Small pill/tag in top-right or alongside name, muted colour
  - CSS: `.skill-runs-on` with `.skill-runs-on-wsl` (subtle blue) and `.skill-runs-on-win` (subtle grey)

---

### Frontend — Stats Bar

#### F17: Stats Bar
- **Blockers:** F5
- **Criterion:** A stats bar below the header shows: total count, and breakdown by source
- **Evidence:** Shows something like: "159 skills — 80 Peterbot | 12 Global Skills | 65 Project Commands | 2 Global Commands". Numbers update when filters are applied (showing filtered count vs total).
- **Implementation notes:**
  - Horizontal bar with pill-shaped stat chips
  - Format: `"${filtered} of ${total} skills"` when filtered, `"${total} skills"` when unfiltered
  - Source breakdown always visible, each with count
  - Uses `.stats-bar` CSS class, flex layout

---

### Frontend — Detail Panel

#### F18: Enhanced Detail Panel
- **Blockers:** F8, F14, F15
- **Criterion:** Clicking a card opens the detail panel showing: name, description, source badge, project(s), runs-on, full file path, last modified date, trigger chips (if any), and full markdown content
- **Evidence:** Clicking `morning-briefing` shows all metadata plus rendered SKILL.md content. Clicking `code-review` shows shared projects list, path, and command markdown.
- **Implementation notes:**
  - Reuse existing `DetailPanel.open()` mechanism
  - Add "Source" row with coloured badge
  - Add "Projects" row (for shared commands, list all project slugs as chips)
  - Add "Path" row showing relative file path (monospace)
  - Add "Last modified" row with formatted date
  - Add "Runs on" row
  - Existing trigger chips and markdown preview remain

#### F19: Shared Command Project List in Detail
- **Blockers:** F5, F18
- **Criterion:** When viewing a shared command (e.g. `code-review`), the detail panel lists all projects that use it as clickable chips
- **Evidence:** `code-review` detail shows: "Used in: discord-messenger, hadley-bricks-im, hadley-bricks-shopify, peterbot-mem, family-meal-planner, finance-tracker, football-prediction-game" as styled chips
- **Implementation notes:**
  - Render `shared_with` array as `.skill-trigger-chip` styled elements (reuse trigger chip styling)
  - Each chip shows the project display name

---

### Backward Compatibility

#### F20: Preserve Existing `/api/skills` Endpoint
- **Blockers:** None
- **Criterion:** The existing `/api/skills` and `/api/skill/{name}` endpoints continue to work unchanged
- **Evidence:** `GET /api/skills` returns the same Peterbot-only data as before. No breaking changes for any other consumers.
- **Implementation notes:**
  - Do NOT modify existing endpoints
  - New functionality is entirely under `/api/skills/directory` and `/api/skills/directory/{id}`
  - The SkillsView JS object replaces its data source from `/api/skills` to `/api/skills/directory` but the old endpoints remain

---

## Dependency Graph

```
F1 (Peterbot skills API)
├── F2 (Global skills) ─────────────────────┐
├── F3 (Project commands) ──┐                │
│   └── F5 (Shared grouping)│                │
├── F4 (Global commands) ───┤                │
│                           ├── F6 (Cache)   │
├── F7 (Categories)         │                │
│                           │                │
├── F8 (Detail endpoint) ◄──┴────────────────┘
│
├── F9 (Source filter) ◄── F5
│   ├── F10 (Type filter)
│   ├── F11 (Project filter)
│   └── F12 (Category filter) ◄── F7
│       └── F13 (Combined filtering)
│
├── F14 (Source badges)
├── F15 (Project badges) ◄── F5
├── F16 (Runs-on indicator)
├── F17 (Stats bar) ◄── F5
│
├── F18 (Detail panel) ◄── F8, F14, F15
│   └── F19 (Shared project list) ◄── F5, F18
│
└── F20 (Backward compat) — no blockers
```

## Implementation Order (Suggested)

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | F1, F20 | Core API with Peterbot skills + backward compat |
| 2 | F2, F3, F4, F7 | Add remaining sources + categories (parallel) |
| 3 | F5, F6 | Grouping + caching |
| 4 | F8 | Detail endpoint for all sources |
| 5 | F9, F14, F16, F17 | Frontend foundation: source filter, badges, stats |
| 6 | F10, F11, F12, F15 | Remaining filters + project badges |
| 7 | F13 | Combined filtering |
| 8 | F18, F19 | Enhanced detail panel |

## Files to Modify

| File | Changes |
|------|---------|
| `peter_dashboard/app.py` | New endpoints: `/api/skills/directory`, `/api/skills/directory/{id}`. New functions for scanning each source. Category mapping. Cache logic. |
| `peter_dashboard/static/js/app.js` | Replace `SkillsView.loadData()` to use new endpoint. Add filter bar HTML. Add `applyFilters()`. Update `renderSkills()` for new badges. Update `select()` for enhanced detail. Add stats bar. |
| `peter_dashboard/static/css/main.css` | New classes: `.skill-badge-source-*`, `.skill-runs-on`, `.stats-bar`, `.filter-bar`, `.skill-project-chip`. |

## Documentation Updates

| File | Update |
|------|--------|
| `hadley_api/README.md` | N/A (dashboard, not API) |
| `peter_dashboard/` | Inline code comments sufficient |
