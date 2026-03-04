# Seed Adapter Test Checklist

**Last verified:** 2026-03-04
**Next check:** After 1am job runs (2026-03-05 morning)

---

## 1. Daily Job Verification (run each morning)

### 1a. Check the 1am job actually ran
```bash
# In WSL — check today's bot log for seed job output
cat "$LOCALAPPDATA/discord-assistant/logs/$(date +%Y-%m-%d).log" | grep -i "incremental_seed\|seed import\|Seed import"
```

**Expected:** Lines showing each adapter ran with imported/skipped/failed counts.

### 1b. Check Supabase for new seed items
```sql
-- In Supabase SQL Editor
SELECT source_system, count(*) as total,
       count(source_url) as with_source_url,
       min(created_at)::date as earliest,
       max(created_at)::date as latest
FROM knowledge_items
WHERE source_system LIKE 'seed:%'
GROUP BY source_system
ORDER BY source_system;
```

**Expected:** Rows for `seed:bookmarks`, `seed:email`, `seed:garmin`, `seed:gcal`, `seed:github`. All should have `with_source_url > 0`.

### 1c. Verify dedup is working
```sql
-- Should return 0 rows if dedup works (no duplicate source_urls)
SELECT source_url, count(*) as dupes
FROM knowledge_items
WHERE source_system LIKE 'seed:%' AND source_url IS NOT NULL
GROUP BY source_url
HAVING count(*) > 1;
```

**Expected:** Empty result set.

---

## 2. Per-Adapter Checks

### 2a. Calendar (`seed:gcal`)
| Check | Expected | Status |
|-------|----------|--------|
| source_system = `seed:gcal` | Yes | |
| source_url format = `gcal://{event_id}` | Yes | |
| title populated | Yes (event summary) | |
| created_at matches event date | Yes | |
| topics include `calendar` | Yes | |

### 2b. Email (`seed:email`)
| Check | Expected | Status |
|-------|----------|--------|
| source_system = `seed:email` | Yes | |
| source_url format = `gmail://{message_id}` | Yes | |
| title = `Email: {subject}` | Yes | |
| topics include `email` + category | Yes | |
| Categories searched: travel, purchases, lego, etc. | Yes | |

**Known limitation:** Email body is snippet-only (Hadley API `/gmail/search` returns snippets, not full bodies). Full body needs a new `/gmail/message/{id}` endpoint.

### 2c. GitHub (`seed:github`)
| Check | Expected | Status |
|-------|----------|--------|
| source_system = `seed:github` | Yes | |
| source_url = GitHub commit/repo URL | Yes | |
| READMEs imported for each repo | Yes | |
| Commits from last 7 days imported | Yes | |
| Merge commits filtered out | Yes | |
| topics include `github`, `code`, repo-specific | Yes | |

**Repos monitored:** peterbot-mem, discord-messenger, finance-tracker, family-meal-planner, hadley-bricks-inventory-management

### 2d. Garmin (`seed:garmin`)
| Check | Expected | Status |
|-------|----------|--------|
| source_system = `seed:garmin` | Yes | |
| source_url = `https://connect.garmin.com/modern/activity/{id}` | Yes | |
| title = activity name | Yes | |
| content includes distance, duration, pace | Yes | |
| topics include `garmin`, `fitness`, activity-type | Yes | |

**Note:** `years_back: 0.02` in incremental job = ~1 week window. If no activities in that window, 0 items fetched (not an error).

### 2e. Bookmarks (`seed:bookmarks`)
| Check | Expected | Status |
|-------|----------|--------|
| source_system = `seed:bookmarks` | Yes | |
| source_url = bookmark URL (http/https) | Yes | |
| Reads from Chrome live Bookmarks file | Yes | |
| Chrome timestamp parsed to datetime | Yes | |
| Folder path extracted to topics | Yes | |

**File:** `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Bookmarks` (JSON, no export needed)

### 2f. Claude Chat History (`seed:claude_history`)
| Check | Expected | Status |
|-------|----------|--------|
| **Manual only** — requires Anthropic export | N/A | |
| Monthly reminder set? | TODO | |

**Action needed:** Set up monthly Peter reminder or Google Calendar event for 1st of each month to export from https://console.anthropic.com and run manually.

---

## 3. Infrastructure Checks

### 3a. Bot is running
```powershell
# Check NSSM service
nssm status DiscordBot
```

### 3b. Hadley API is running
```bash
curl -s http://localhost:8100/health | head -1
# OR from WSL:
curl -s http://172.19.64.1:8100/health | head -1
```

### 3c. Garmin session valid
```bash
# Check session directory exists and has recent files
ls -la "$LOCALAPPDATA/discord-assistant/garmin_session/"
```

### 3d. GitHub token valid
```bash
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user | grep login
```

---

## 4. Known Issues & Debt

| Issue | Severity | Status |
|-------|----------|--------|
| Email body = snippet only (no full text) | MEDIUM | Needs Hadley API `/gmail/message/{id}` endpoint |
| Claude History manual-only | LOW | Need monthly reminder setup |
| Old seed items (pre-fix) have NULL source_url | LOW | Will self-heal as dedup prevents re-import of items with same content |
| Garmin `years_back: 0.02` may miss weeks with no activity | LOW | Acceptable — garmin activities are sparse |

---

## 5. Manual Test Script

Run this from `C:\Users\Chris Hadley\claude-projects\Discord-Messenger`:

```bash
python -X utf8 -c "
import asyncio, sys, os
sys.path.insert(0, '.')

async def test_all():
    from domains.second_brain.seed.adapters.calendar import CalendarEventsAdapter
    from domains.second_brain.seed.adapters.email import EmailImportAdapter
    from domains.second_brain.seed.adapters.github import GitHubProjectsAdapter
    from domains.second_brain.seed.adapters.garmin import GarminActivitiesAdapter
    from domains.second_brain.seed.adapters.bookmarks import BookmarksAdapter

    adapters = [
        ('Calendar', CalendarEventsAdapter({'years_back': 0.1})),
        ('Email', EmailImportAdapter({'years_back': 0.1, 'categories': ['travel'], 'per_category_limit': 3})),
        ('GitHub', GitHubProjectsAdapter({'days_back': 7})),
        ('Garmin', GarminActivitiesAdapter({'years_back': 0.1})),
        ('Bookmarks', BookmarksAdapter({'file_path': os.path.join(os.getenv('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data', 'Default', 'Bookmarks')})),
    ]

    for name, adapter in adapters:
        valid, err = await adapter.validate()
        items = await adapter.fetch(limit=3) if valid else []
        status = 'PASS' if valid and len(items) > 0 else ('PASS (0 items)' if valid else f'FAIL: {err}')
        print(f'  {name}: {status} ({len(items)} items)')

asyncio.run(test_all())
"
```

**Expected:** All 5 show PASS with 1+ items.
