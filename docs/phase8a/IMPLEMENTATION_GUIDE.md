# Phase 8a Implementation Guide

## Overview

Phase 8a adds Gmail, Google Calendar, Google Drive, and Notion integrations to Peterbot.

**Skills Added:** 8 new skills
**APIs:** Google (OAuth), Notion (API key)
**Scheduled Jobs:** 4 new entries (or consolidated into morning-briefing)

---

## Files to Create/Modify

### New Skill Files (copy to `skills/` directory)

```
skills/
├── email-summary/SKILL.md      ← NEW
├── email-search/SKILL.md       ← NEW
├── schedule-today/SKILL.md     ← NEW
├── schedule-week/SKILL.md      ← NEW
├── find-free-time/SKILL.md     ← NEW
├── drive-search/SKILL.md       ← NEW
├── notion-todos/SKILL.md       ← NEW
├── notion-ideas/SKILL.md       ← NEW
```

### Config Files

| File | Changes |
|------|---------|
| `.env` | Add Google OAuth + Notion credentials |
| `config.py` | Import new env vars |
| `data_fetchers.py` | Add 5 new fetcher functions + register |
| `SCHEDULE.md` | Add 4 scheduled entries (or update morning-briefing) |

---

## Step-by-Step Implementation

### Step 1: Get Notion Database IDs

1. Open "Claude Managed To Dos" in Notion
2. Copy URL, extract database ID (32-char string)
3. Repeat for "Ideas Backlog"
4. Add to `.env`:
   ```
   NOTION_TODOS_DATABASE_ID=xxxxx
   NOTION_IDEAS_DATABASE_ID=xxxxx
   ```

### Step 2: Verify Google OAuth

You mentioned Google OAuth is set up. Verify these are in `.env`:
```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
```

Required scopes:
- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.compose` (for drafts)
- `https://www.googleapis.com/auth/calendar.readonly`
- `https://www.googleapis.com/auth/calendar.events` (for creating)
- `https://www.googleapis.com/auth/drive.readonly`

### Step 3: Copy Skill Files

Copy all SKILL.md files from this package to:
```
/mnt/c/Users/Chris Hadley/domains/peterbot/wsl_config/skills/
```

### Step 4: Update data_fetchers.py

Add the data fetcher functions from `DATA_FETCHERS.md` to:
```
/mnt/c/Users/Chris Hadley/domains/peterbot/data_fetchers.py
```

Don't forget to:
1. Add imports at top
2. Register in `SKILL_DATA_FETCHERS` dict

### Step 5: Update config.py

Add the new config variables from `CONFIG_ADDITIONS.md`.

### Step 6: Update SCHEDULE.md

Add scheduled entries (or consolidate into morning-briefing).

### Step 7: Restart Bot

```bash
# In WSL
cd ~/peterbot
python bot.py
```

### Step 8: Test Skills

```
!skill email-summary
!skill schedule-today
!skill notion-todos
```

Then conversational:
```
"Any emails from Sarah?"
"When am I free tomorrow?"
"Find the budget doc"
"Show my ideas backlog"
```

---

## Skill Summary

| Skill | Type | Trigger | Data Fetcher |
|-------|------|---------|--------------|
| email-summary | Scheduled + Conv | "emails", "inbox" | ✅ |
| email-search | Conversational | "find email from..." | ❌ (real-time) |
| schedule-today | Scheduled + Conv | "what's on today" | ✅ |
| schedule-week | Scheduled + Conv | "this week" | ✅ |
| find-free-time | Conversational | "when am I free" | ❌ (real-time) |
| drive-search | Conversational | "find document" | ❌ (real-time) |
| notion-todos | Scheduled + Conv | "my todos" | ✅ |
| notion-ideas | Conversational | "ideas backlog" | ✅ |

---

## MCP Server Option (Alternative)

Instead of direct API calls in data_fetchers.py, you could use MCP servers:

```json
{
  "mcpServers": {
    "gmail": {
      "command": "npx",
      "args": ["-y", "mcp-google-gmail"]
    },
    "calendar": {
      "command": "npx", 
      "args": ["-y", "mcp-google-calendar"]
    },
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/mcp-server-notion"]
    }
  }
}
```

Pros: Claude Code handles auth, caching, pagination
Cons: Requires MCP server packages, more moving parts

For Phase 8a, **direct API calls are simpler** since we control the data format.

---

## Verification Checklist

- [ ] Notion database IDs obtained
- [ ] Google OAuth credentials verified
- [ ] 8 SKILL.md files copied
- [ ] data_fetchers.py updated with 5 functions
- [ ] SKILL_DATA_FETCHERS dict updated
- [ ] config.py updated
- [ ] .env updated
- [ ] SCHEDULE.md updated
- [ ] Bot restarted
- [ ] `!skill email-summary` works
- [ ] `!skill schedule-today` works
- [ ] `!skill notion-todos` works
- [ ] Conversational triggers work
