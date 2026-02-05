# Parser System Dashboard Page - Implementation Plan

## Overview

Add a comprehensive dashboard page for monitoring the self-improving parser system. This page will display fixture statistics, capture quality, feedback, improvement cycles, and format drift alerts.

---

## Page Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  🔧 Parser System                                    [Refresh]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │
│  │ PASS RATE   │  │ CAPTURES    │  │ FEEDBACK    │  │ CYCLES  │ │
│  │   72.7%     │  │   142       │  │   3 pending │  │   5     │ │
│  │ 8/11 ✅     │  │ 8 failures  │  │ 1 high      │  │ 4 good  │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────┘ │
│                                                                  │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                  │
│  [Fixtures] [Captures] [Feedback] [Cycles] [Drift]    <- Tabs   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                                                              ││
│  │  Tab Content (varies by selected tab)                        ││
│  │                                                              ││
│  │  - Fixtures: Category breakdown, failing fixtures list       ││
│  │  - Captures: Recent 24h with quality signals                 ││
│  │  - Feedback: Pending items with category/priority            ││
│  │  - Cycles: Improvement history with commit/rollback status   ││
│  │  - Drift: Format drift alerts by skill                       ││
│  │                                                              ││
│  └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                  │
│  Actions:                                                        │
│  [Run Regression] [Review Cycle] [Mark Reviewed] [View Report]   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tab Contents

### Tab 1: Fixtures
- **Summary cards**: Total, Passing, Failing, Untested
- **Category breakdown** (grid): Each category with pass rate bar
- **Chronic failures** (table): Fixtures that have failed 3+ times
- **Actions**: Run regression, Promote capture

### Tab 2: Captures (24h)
- **Quality signal counts**: Empty, ANSI, Echo, Reacted
- **Recent captures** (table): Time, Channel, Skill, Quality flags
- **Filter**: By quality issue type
- **Action**: View capture details, Promote to fixture

### Tab 3: Feedback
- **Pending count** by category (parser_issue, format_drift, etc.)
- **Feedback list** (table): Time, Category, Skill, Description, Priority
- **Actions**: View details, Resolve, Mark as duplicate

### Tab 4: Improvement Cycles
- **Recent cycles** (table): Date, Target stage, Committed, Score change
- **Review status**: Cycles since last human review (warning if ≥4)
- **Actions**: View cycle details, Mark reviewed

### Tab 5: Format Drift
- **Skill health** (grid): Each monitored skill with avg score
- **Drift alerts** (table): Recent alerts with skill, issue, recommendation
- **Actions**: View spec, Update spec

---

## API Endpoints Required

### GET /api/parser/status
Overall parser system status for the summary cards.

```json
{
  "fixtures": {
    "total": 11,
    "passing": 8,
    "failing": 3,
    "untested": 0,
    "pass_rate": 0.727
  },
  "captures_24h": {
    "total": 142,
    "failures": 8,
    "empty": 2,
    "ansi": 3,
    "echo": 1,
    "reacted": 2
  },
  "feedback": {
    "pending": 3,
    "high_priority": 1,
    "by_category": {"parser_issue": 2, "format_drift": 1}
  },
  "cycles": {
    "total": 5,
    "committed": 4,
    "since_review": 2
  },
  "drift_alerts": 1
}
```

### GET /api/parser/fixtures
Fixture details for the Fixtures tab.

```json
{
  "by_category": {
    "simple_text": {"total": 2, "passed": 2},
    "ansi_contaminated": {"total": 2, "passed": 0},
    ...
  },
  "chronic_failures": [
    {"id": "abc123", "category": "ansi_contaminated", "fail_count": 5}
  ],
  "recent_results": [
    {"id": "abc123", "passed": false, "score": 0.80, "failed_dims": ["ansi_cleanliness"]}
  ]
}
```

### GET /api/parser/captures
Recent captures for the Captures tab.

```json
{
  "captures": [
    {
      "id": "cap123",
      "captured_at": "2026-02-04T10:30:00",
      "channel_name": "peterbot",
      "skill_name": "morning-briefing",
      "was_empty": false,
      "had_ansi": true,
      "had_echo": false,
      "user_reacted": "🔧",
      "promoted": false
    }
  ],
  "stats": {
    "total": 142,
    "failures": 8
  }
}
```

### GET /api/parser/feedback
Pending feedback for the Feedback tab.

```json
{
  "feedback": [
    {
      "id": "fb123",
      "created_at": "2026-02-04T09:15:00",
      "input_method": "reaction",
      "category": "parser_issue",
      "skill_name": "morning-briefing",
      "description": "ANSI codes visible in output",
      "priority": "normal",
      "status": "pending"
    }
  ],
  "summary": {
    "total": 3,
    "high_priority": 1,
    "by_category": {"parser_issue": 2, "format_drift": 1}
  }
}
```

### GET /api/parser/cycles
Improvement cycle history for the Cycles tab.

```json
{
  "cycles": [
    {
      "id": "cyc123",
      "started_at": "2026-02-04T02:00:00",
      "target_stage": "strip_ansi",
      "committed": true,
      "score_before": 0.936,
      "score_after": 0.949,
      "fixtures_improved": 4,
      "regressions": 0
    }
  ],
  "review_status": {
    "cycles_since_review": 2,
    "review_required": false,
    "max_without_review": 5
  }
}
```

### GET /api/parser/drift
Format drift status for the Drift tab.

```json
{
  "skill_health": [
    {
      "skill_name": "morning-briefing",
      "display_name": "Morning Briefing",
      "avg_score": 0.92,
      "status": "healthy",
      "drift_count": 0
    }
  ],
  "alerts": [
    {
      "id": "alert123",
      "skill_name": "health-digest",
      "captured_at": "2026-02-04T08:00:00",
      "format_score": 0.75,
      "drift_details": ["Missing sections: sleep"]
    }
  ]
}
```

### POST /api/parser/run-regression
Trigger a regression test run.

### POST /api/parser/run-cycle
Run an improvement cycle (dry-run or full).

### POST /api/parser/mark-reviewed
Mark human review complete.

### POST /api/parser/feedback/{id}/resolve
Resolve a feedback item.

---

## Implementation Steps

### Step 1: Add API Endpoints (app.py)

Add new endpoints to `peter_dashboard/app.py`:

```python
# Parser System API endpoints
@app.get("/api/parser/status")
async def get_parser_status():
    """Get overall parser system status."""
    from domains.peterbot.capture_parser import get_parser_capture_store
    from domains.peterbot.feedback_processor import get_feedback_processor
    from domains.peterbot.scheduled_output_scorer import get_scheduled_output_scorer
    from domains.peterbot.parser_improver import get_parser_improver

    store = get_parser_capture_store()
    feedback = get_feedback_processor()
    scorer = get_scheduled_output_scorer()
    improver = get_parser_improver()

    # Gather all stats
    fixture_stats = store.get_fixture_stats()
    capture_stats = store.get_capture_stats(hours=24)
    feedback_summary = feedback.get_pending_summary()

    # ... build response
```

### Step 2: Add Navigation Item

In the HTML sidebar section (~line 2000 in app.py):

```html
<div class="nav-item" data-view="parser" onclick="switchView('parser')">
    🔧 Parser System
</div>
```

### Step 3: Add switchView Case

In the JavaScript switchView function (~line 2936):

```javascript
case 'parser': renderParser(); break;
```

### Step 4: Add Render Functions

Add JavaScript functions for rendering the parser page:

```javascript
let parserTab = 'fixtures';

async function renderParser() {
    const content = document.getElementById('content');
    content.innerHTML = '<h2>Loading parser system...</h2>';

    const status = await api('/parser/status');

    content.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
            <h2>🔧 Parser System</h2>
            <button class="btn btn-secondary" onclick="renderParser()">Refresh</button>
        </div>

        <!-- Summary Cards -->
        <div class="grid grid-4" style="margin-bottom: 1.5rem;">
            ${renderParserSummaryCards(status)}
        </div>

        <!-- Tabs -->
        <div class="memory-tabs" style="margin-bottom: 1rem;">
            <div class="memory-tab ${parserTab === 'fixtures' ? 'active' : ''}"
                 onclick="switchParserTab('fixtures')">Fixtures</div>
            <div class="memory-tab ${parserTab === 'captures' ? 'active' : ''}"
                 onclick="switchParserTab('captures')">Captures</div>
            <div class="memory-tab ${parserTab === 'feedback' ? 'active' : ''}"
                 onclick="switchParserTab('feedback')">Feedback</div>
            <div class="memory-tab ${parserTab === 'cycles' ? 'active' : ''}"
                 onclick="switchParserTab('cycles')">Cycles</div>
            <div class="memory-tab ${parserTab === 'drift' ? 'active' : ''}"
                 onclick="switchParserTab('drift')">Drift</div>
        </div>

        <!-- Tab Content -->
        <div id="parser-tab-content"></div>

        <!-- Actions -->
        <div style="margin-top: 1.5rem; display: flex; gap: 0.5rem;">
            <button class="btn btn-primary" onclick="runParserRegression()">
                Run Regression
            </button>
            <button class="btn btn-secondary" onclick="runParserCycle()">
                Review Cycle
            </button>
            <button class="btn btn-secondary" onclick="markParserReviewed()">
                Mark Reviewed
            </button>
        </div>
    `;

    await loadParserTab(parserTab);
}

function renderParserSummaryCards(status) {
    const passRate = (status.fixtures.pass_rate * 100).toFixed(1);
    const passClass = passRate >= 90 ? 'success' : passRate >= 70 ? 'warning' : 'error';

    return `
        <div class="card">
            <div class="card-header">
                <span class="card-title">Pass Rate</span>
            </div>
            <div style="font-size: 2rem; color: var(--${passClass});">
                ${passRate}%
            </div>
            <div style="color: var(--text-secondary);">
                ${status.fixtures.passing}/${status.fixtures.total} fixtures
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <span class="card-title">Captures (24h)</span>
            </div>
            <div style="font-size: 2rem;">
                ${status.captures_24h.total}
            </div>
            <div style="color: var(--text-secondary);">
                ${status.captures_24h.failures} failures
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <span class="card-title">Feedback</span>
            </div>
            <div style="font-size: 2rem;">
                ${status.feedback.pending}
            </div>
            <div style="color: var(--text-secondary);">
                ${status.feedback.high_priority} high priority
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <span class="card-title">Cycles</span>
            </div>
            <div style="font-size: 2rem;">
                ${status.cycles.total}
            </div>
            <div style="color: var(--text-secondary);">
                ${status.cycles.committed} committed
            </div>
        </div>
    `;
}

async function switchParserTab(tab) {
    parserTab = tab;
    document.querySelectorAll('.memory-tab').forEach(t => {
        t.classList.toggle('active', t.textContent.toLowerCase() === tab);
    });
    await loadParserTab(tab);
}

async function loadParserTab(tab) {
    const container = document.getElementById('parser-tab-content');
    container.innerHTML = '<p>Loading...</p>';

    switch(tab) {
        case 'fixtures': await renderFixturesTab(container); break;
        case 'captures': await renderCapturesTab(container); break;
        case 'feedback': await renderFeedbackTab(container); break;
        case 'cycles': await renderCyclesTab(container); break;
        case 'drift': await renderDriftTab(container); break;
    }
}
```

### Step 5: Add Tab Render Functions

Each tab has its own render function that fetches data and displays it.

---

## Files to Modify

| File | Changes |
|------|---------|
| `peter_dashboard/app.py` | Add 6 new API endpoints + navigation + render functions |
| `domains/peterbot/capture_parser.py` | Ensure all stats methods exist |
| `domains/peterbot/feedback_processor.py` | Ensure summary methods exist |
| `domains/peterbot/parser_improver.py` | Add API-friendly status methods |

---

## Styling Notes

Use existing dashboard CSS classes:
- `.card` for stat boxes
- `.memory-tabs` / `.memory-tab` for tabs
- `.grid grid-4` for summary cards
- `.btn btn-primary` / `.btn btn-secondary` for actions
- `var(--success)`, `var(--warning)`, `var(--error)` for status colors

---

## Testing

1. Start dashboard: `python peter_dashboard/app.py`
2. Navigate to http://localhost:8200
3. Click "Parser System" in sidebar
4. Verify:
   - Summary cards show correct data
   - All 5 tabs load and display content
   - Actions work (Run Regression, etc.)
   - Auto-refresh updates data

---

## Future Enhancements

1. **Real-time updates** via WebSocket for capture stream
2. **Fixture editor** - View/edit expected output
3. **Capture detail modal** - Full raw/parsed comparison
4. **Improvement cycle log viewer** - Detailed logs from each run
5. **Export** - Download fixtures/captures as JSON
