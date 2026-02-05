# Phase 8a: Gmail / Calendar / Drive / Notion Integration

## Overview

Add 8 new skills for personal productivity integration:
- **Gmail**: Inbox summary, email search
- **Calendar**: Today's schedule, week view, find free time
- **Drive**: Document search
- **Notion**: Todos, ideas backlog

---

## Prerequisites (User Actions Required)

### 1. Google OAuth Setup

**Status:** User mentioned OAuth is set up - needs verification

**Required Scopes:**
- `gmail.readonly` - Read emails
- `gmail.compose` - Draft emails (future)
- `calendar.readonly` - Read calendar
- `calendar.events` - Create events (future)
- `drive.readonly` - Search drive

**Credentials Needed in .env:**
```
GOOGLE_CLIENT_ID=<from GCP console>
GOOGLE_CLIENT_SECRET=<from GCP console>
GOOGLE_REFRESH_TOKEN=<from OAuth flow>
```

**Action:** Verify credentials exist and scopes are sufficient

### 2. Notion Database IDs

**Databases:**
1. "Claude Managed To Dos" - Task management
2. "Ideas Backlog" - Ideas capture

**How to Get IDs:**
1. Open database in Notion
2. Copy URL: `https://notion.so/workspace/{DATABASE_ID}?v=...`
3. Extract 32-char ID before the `?`

**Credentials Needed in .env:**
```
NOTION_API_KEY=REDACTED_NOTION_TOKEN
NOTION_TODOS_DATABASE_ID=<extract from URL>
NOTION_IDEAS_DATABASE_ID=<extract from URL>
```

**Action:** Get both database IDs from Notion URLs

---

## Implementation Tasks

### Task 1: Config Setup

**Files:** `.env`, `config.py`

1. Add to `.env`:
```bash
# Google OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...

# Notion
NOTION_API_KEY=REDACTED_NOTION_TOKEN
NOTION_TODOS_DATABASE_ID=...
NOTION_IDEAS_DATABASE_ID=...
```

2. Add to `config.py`:
```python
# Phase 8a: Google
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")

# Phase 8a: Notion
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
NOTION_TODOS_DATABASE_ID = os.getenv("NOTION_TODOS_DATABASE_ID")
NOTION_IDEAS_DATABASE_ID = os.getenv("NOTION_IDEAS_DATABASE_ID")
```

**Dependencies:** None

---

### Task 2: Data Fetchers

**File:** `domains/peterbot/data_fetchers.py`

**New Functions:**
| Function | API | Purpose |
|----------|-----|---------|
| `get_google_access_token()` | Google OAuth | Helper - refresh access token |
| `get_email_summary_data()` | Gmail | Unread emails, count, snippets |
| `get_schedule_today_data()` | Calendar | Today's events |
| `get_schedule_week_data()` | Calendar | 7-day event overview |
| `get_notion_todos_data()` | Notion | Incomplete tasks |
| `get_notion_ideas_data()` | Notion | Ideas backlog |

**Register in SKILL_DATA_FETCHERS:**
```python
"email-summary": get_email_summary_data,
"schedule-today": get_schedule_today_data,
"schedule-week": get_schedule_week_data,
"notion-todos": get_notion_todos_data,
"notion-ideas": get_notion_ideas_data,
```

**Note:** email-search, find-free-time, drive-search are conversational-only (no pre-fetcher - real-time queries)

**Dependencies:** Task 1

---

### Task 3: Copy Skill Files

**Source:** `docs/phase8a/skills/`
**Destination:** `domains/peterbot/wsl_config/skills/`

| Skill | Type | Has Fetcher |
|-------|------|-------------|
| email-summary | Scheduled + Conversational | Yes |
| email-search | Conversational only | No |
| schedule-today | Scheduled + Conversational | Yes |
| schedule-week | Scheduled + Conversational | Yes |
| find-free-time | Conversational only | No |
| drive-search | Conversational only | No |
| notion-todos | Scheduled + Conversational | Yes |
| notion-ideas | Conversational only | Yes |

**Dependencies:** None (can run parallel with Task 2)

---

### Task 4: Schedule Updates

**File:** `domains/peterbot/wsl_config/SCHEDULE.md`

**Option A - Separate Jobs:**
```markdown
| Email Summary | email-summary | 08:00 UK | #peterbot | yes |
| Schedule Today | schedule-today | 08:00 UK | #peterbot | yes |
| Schedule Week | schedule-week | 18:00 Sun UK | #peterbot | yes |
| Notion Todos | notion-todos | 08:00 UK | #peterbot | yes |
```

**Option B - Consolidate into Morning Briefing:**
Update morning-briefing skill to include:
- Schedule Today
- Email Summary (if unread > 0)
- Notion Todos (if pending > 0)

**Recommendation:** Option A first for testing, then consolidate if desired.

**Dependencies:** Tasks 2 & 3

---

### Task 5: Test Each Skill

**Manual Tests:**
```
!skill email-summary
!skill schedule-today
!skill schedule-week
!skill notion-todos
!skill notion-ideas
```

**Conversational Tests:**
```
"Any emails from Sarah?"          → email-search
"When am I free tomorrow?"        → find-free-time
"Find the budget doc"             → drive-search
"Show my ideas backlog"           → notion-ideas
```

**Dependencies:** Tasks 1-4, bot restart

---

## Decision Points

### Q1: MCP Servers vs Direct API?

**Option A: Direct API (Recommended for Phase 8a)**
- Simpler setup
- We control data format exactly
- Already have patterns in data_fetchers.py

**Option B: MCP Servers**
- Claude Code handles auth, caching
- More moving parts
- Better for complex queries

**Recommendation:** Direct API for now. Can migrate to MCP later.

### Q2: Conversational-only Skills - Real-time or Pre-fetch?

**email-search, find-free-time, drive-search** have no data fetcher.

**Options:**
1. Peter calls API directly (needs MCP or tools)
2. Peter requests data, scheduler fetches, returns result
3. Just use web search (won't work for private data)

**Recommendation:** Need MCP servers for Peter to query these in real-time.

### Q3: Morning Briefing Consolidation?

**Current:** Separate scheduled jobs at 08:00
**Alternative:** Single "morning-briefing" that includes all summaries

**Recommendation:** Keep separate initially, consolidate after testing.

---

## Implementation Order

```
Phase 8a-1: Setup (30 mins)
├── 1.1 Verify Google OAuth credentials
├── 1.2 Get Notion database IDs
├── 1.3 Update .env
└── 1.4 Update config.py

Phase 8a-2: Scheduled Skills (1-2 hrs)
├── 2.1 Add data fetchers (email-summary, schedule-*, notion-*)
├── 2.2 Copy skill files
├── 2.3 Update SCHEDULE.md
├── 2.4 Restart bot
└── 2.5 Test !skill commands

Phase 8a-3: Conversational Skills (1-2 hrs)
├── 3.1 Evaluate MCP server approach
├── 3.2 Configure MCP for Gmail/Calendar/Drive
├── 3.3 Test conversational triggers
└── 3.4 Fine-tune skill instructions

Phase 8a-4: Polish (30 mins)
├── 4.1 Update manifest.json (auto on reload)
├── 4.2 Add memory inserts for skill usage
├── 4.3 Consider morning-briefing consolidation
└── 4.4 Document in PHASE8A_SUMMARY.md
```

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Google OAuth expired/invalid | High | Test token refresh first |
| Notion DB structure different than expected | Medium | Adapt property parsing |
| Rate limits (Gmail 10 req/sec) | Low | Add delays in fetchers |
| MCP servers not available for Peter | High | May need alternative for real-time queries |
| Too many 08:00 notifications | Medium | Consolidate or stagger times |

---

## Verification Checklist

- [ ] Google OAuth credentials verified
- [ ] Google scopes include gmail.readonly, calendar.readonly, drive.readonly
- [ ] Notion database IDs obtained
- [ ] .env updated with all credentials
- [ ] config.py imports new env vars
- [ ] data_fetchers.py has 5 new functions
- [ ] SKILL_DATA_FETCHERS dict updated
- [ ] 8 skill folders copied to skills/
- [ ] SCHEDULE.md updated (4 new entries)
- [ ] Bot restarted
- [ ] `!skill email-summary` works
- [ ] `!skill schedule-today` works
- [ ] `!skill notion-todos` works
- [ ] Conversational triggers work
- [ ] manifest.json regenerated with new skills
