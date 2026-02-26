# Peter Dashboard Task System: Analysis & Improvement Roadmap

## Current State Assessment

Your task system already has a strong foundation that many commercial tools charge good money for. The four distinct list types with bespoke status workflows (personal_todo, peter_queue, ideas, research) are genuinely more sophisticated than what you'd get from Trello or Todoist out of the box. The heartbeat scheduling concept — tying tasks to Peter's autonomous work cycles — is something no commercial tool offers because it's unique to your AI-agent workflow.

Here's what you've nailed:

- **Multi-workflow Kanban** with validated status transitions per list type
- **19 REST API endpoints** — clean separation of concerns
- **Drag-and-drop** with visual feedback and transition validation
- **Category/tag system** with full CRUD and colour management
- **Heartbeat integration** linking tasks to Peter's autonomous cycles
- **Comment system** with system message support for audit trails
- **Database design** that's properly normalised with junction tables, history tracking, and reminders tables ready for use

---

## Feature Gap Analysis: What the Best Commercial Tools Do

### Tier 1: High-Impact, Missing Entirely

| Feature | Who Does It Well | Why It Matters for You |
|---------|-----------------|----------------------|
| **Subtasks / Checklists** | Todoist, Linear, Asana | Break "Build eBay listing engine" into actionable steps without creating separate tasks. Essential for Peter Queue items that have multi-step implementation phases. |
| **Recurring Tasks** | Todoist (best-in-class), TickTick | "Review Vinted scraper results" is probably weekly. "Check BrickLink inventory sync" might be daily. Currently you'd re-create these manually. |
| **Task Dependencies** | Asana, ClickUp, Linear | "Deploy API changes" blocked by "Write tests" — prevents starting work that can't proceed yet. Critical for Peter Queue where build order matters. |
| **WIP Limits** | Jira, Businessmap, KanbanFlow | Cap "In Progress" at 3 items to prevent context-switching. Research shows teams with WIP limits deliver 37% faster. Even as a solo operator, this keeps focus tight. |
| **Activity / Audit Log UI** | Linear, Asana, Trello | You have `task_history` in the DB but no UI to view it. "When did this move to in_progress? Who changed the priority?" — essential for reviewing Peter's autonomous actions. |

### Tier 2: High-Impact, Partially Built

| Feature | Current State | Gap |
|---------|--------------|-----|
| **Reminders** | `task_reminders` table exists | No notification delivery (Discord ping? Dashboard alert? Push notification?) |
| **Comments** | API exists, `task_comments` table ready | No UI in the dashboard to view/add comments on task cards |
| **Attachments** | `task_attachments` table exists | No upload/download UI |
| **Search** | Title-only text search | No filtering by priority, category, date range, or combined criteria |
| **History** | `task_history` table exists | No UI, no timeline view of task lifecycle |

### Tier 3: Nice-to-Have, Differentiating

| Feature | Inspiration | Application |
|---------|------------|-------------|
| **Keyboard shortcuts** | Linear (Cmd+K command palette) | Quick-add with `N`, mark done with `D`, navigate lists with `1-4`. Linear's entire UX philosophy is built on this — and your dashboard is already keyboard-friendly territory. |
| **Natural language input** | Todoist ("Review scraper results every Monday at 9am") | Type "Book Amsterdam accommodation by 15 Feb medium priority running" and have it parse into structured fields. |
| **Quick filters / saved views** | Linear (custom views), Asana | "Show me all high-priority Hadley Bricks tasks due this week" as a one-click filter. |
| **Card aging** | Trello, Businessmap | Visual indicator when tasks have been sitting in a column too long — the card gradually changes opacity or gets a warning badge. |
| **Cycle time analytics** | Businessmap, Jira, Kanbanize | How long do tasks typically sit in each column? Cumulative flow diagram showing throughput over time. Where are your bottlenecks? |
| **Swimlanes** | Jira, Businessmap | Horizontal lanes within columns — e.g., "In Progress" split by project (Hadley Bricks vs Peterbot vs Personal). |
| **Bulk operations** | Asana, ClickUp | Multi-select tasks → change priority / move to column / assign category in one action. |
| **Pomodoro / time tracking** | KanbanFlow, Toggl integration | Track actual effort vs estimated effort. Your `estimated_effort` field is ready for this. |

---

## Competitive Comparison Matrix

| Capability | Your Dashboard | Trello | Todoist | Linear | Asana | ClickUp |
|-----------|---------------|--------|---------|--------|-------|---------|
| Custom status workflows | ✅ Per list type | ❌ Generic | ❌ Generic | ✅ Per team | ✅ Custom | ✅ Custom |
| AI/Bot task creation | ✅ Peter creates tasks | ❌ | ❌ | ❌ | ❌ | ❌ |
| Heartbeat scheduling | ✅ Unique | ❌ | ❌ | ❌ | ❌ | ❌ |
| Subtasks | ❌ | ✅ Checklists | ✅ 4 levels | ✅ Sub-issues | ✅ Rich | ✅ Nested |
| Recurring tasks | ❌ | ✅ Butler | ✅ Best-in-class | ✅ Cycles | ✅ | ✅ |
| Dependencies | ❌ | ⚠️ Power-Up | ❌ | ✅ | ✅ Paid | ✅ |
| WIP limits | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Keyboard shortcuts | ❌ | ✅ Basic | ✅ Good | ✅ Best-in-class | ✅ | ✅ |
| Advanced filters | ⚠️ Title only | ✅ Labels | ✅ Filters | ✅ Views | ✅ Rich | ✅ Rich |
| Activity log UI | ❌ (DB ready) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Analytics/metrics | ❌ | ❌ | ⚠️ Karma | ✅ Good | ✅ Dashboards | ✅ Rich |
| API access | ✅ Full control | ✅ | ✅ | ✅ | ✅ | ✅ |
| Discord integration | ✅ Native | ⚠️ Webhook | ❌ | ❌ | ❌ | ✅ |
| Self-hosted / owned | ✅ Full ownership | ❌ SaaS | ❌ SaaS | ❌ SaaS | ❌ SaaS | ❌ SaaS |
| Cost | £0 | £0-10/mo | £4-6/mo | £8/mo | £10-25/mo | £7-12/mo |

**Your unique advantages that no commercial tool matches:**
1. Peter can autonomously create, categorise, and schedule tasks
2. Heartbeat integration ties task execution to AI agent work cycles
3. Full data ownership with Supabase — no vendor lock-in
4. Custom status machines per list type
5. Deep integration with your entire Peterbot ecosystem (Discord, Claude Code, skills)

---

## Recommended Implementation Phases

### Phase 1: Quick Wins (1-2 days each)

**1a. Comments UI** — You have the API, just need the UI panel in the edit modal. Show threaded comments with timestamps and "by Peter" badges for system messages. This immediately gives visibility into Peter's reasoning when he creates or modifies tasks.

**1b. Activity Timeline** — Surface `task_history` as a collapsible timeline in the edit modal. "Created → Priority changed to High → Moved to In Progress → Comment added". Linear does this beautifully as a sidebar.

**1c. Advanced Filters** — Add filter dropdowns above the Kanban columns: priority, category, date range, effort estimate. Store active filters in URL params so they're bookmarkable.

**1d. WIP Limits** — Add a configurable max-count per column. When exceeded, the column header turns red and drag-drop is blocked (or warned). Simple but transformative for focus.

### Phase 2: Structural Improvements (2-5 days each)

**2a. Subtasks / Checklists** — Add a `parent_task_id` field to the tasks table. Render as indented checklists within the task card. For Peter Queue items, this maps perfectly to build steps: "Write tests → Implement feature → Code review → Merge".

**2b. Recurring Tasks** — New fields: `recurrence_rule` (cron-like or natural language), `recurrence_end`, `last_occurrence`. When a recurring task is completed, auto-create the next instance. Peter's heartbeat can handle this during overnight processing.

**2c. Keyboard Shortcuts** — Steal from Linear: `N` = new task, `D` = mark done, `1-4` = switch lists, `/` = focus search, `Cmd+K` = command palette. Register a global keydown handler. This alone transforms the dashboard from "click-heavy" to "power-user fast".

**2d. Reminders via Discord** — Wire up `task_reminders` to send Discord DMs via Peter. "Hey Chris, 'Book Amsterdam accommodation' is due in 2 days." Peter's already got the Discord integration — this is just a new trigger.

### Phase 3: Analytics & Intelligence (3-7 days each)

**3a. Cycle Time Dashboard** — Track time-in-status for every task. Show average cycle times per list type. "Personal todos average 3 days inbox-to-done. Peter Queue items average 2 heartbeat cycles." Cumulative flow diagram showing throughput trends.

**3b. Card Aging** — Visual indicator on cards that have been in a non-done column for too long. Configurable thresholds per column: "In Progress > 3 days = yellow, > 7 days = red". Opacity fade like Trello's aging feature.

**3c. Smart Scheduling** — Peter analyses your task backlog and suggests an optimal daily plan based on priorities, due dates, effort estimates, and current WIP. "You have 3 high-priority items due this week. Suggested focus for today: [task1], [task2]."

**3d. Natural Language Task Input** — "Review Vinted results every Monday 30min medium Hadley Bricks Vinted" → parsed into all fields automatically. Peter could handle the NLP parsing via Claude.

### Phase 4: Power Features (Future)

**4a. Dependencies** — `task_dependencies` junction table with `blocks/blocked_by` relationship types. Visually show blocked tasks as greyed out with a lock icon. Automatically unblock when the blocking task completes.

**4b. Swimlanes** — Horizontal grouping within columns by project/category. Toggle between "flat" and "swimlane" views. Useful when you have Hadley Bricks, Peterbot, and personal tasks all in progress.

**4c. Calendar View** — Alternative to Kanban showing tasks on a timeline by scheduled/due date. Todoist's calendar view is the gold standard here. Useful for seeing the week ahead at a glance.

**4d. Effort Tracking** — Compare `estimated_effort` to actual time (either manually entered or derived from heartbeat cycle data). Over time, calibrate estimation accuracy: "You consistently underestimate 'half_day' tasks by 40%."

---

## Architecture Considerations

**For subtasks and dependencies**, you'll want to decide between:
- **Flat with parent_id** (simpler, what Todoist does) — a `parent_task_id` nullable FK on the tasks table
- **Separate junction table** (more flexible, what Asana does) — allows multiple relationship types (blocks, relates_to, duplicates)

Recommendation: start with `parent_task_id` for subtasks, add a `task_relationships` table later for dependencies. Keep them separate — they serve different purposes.

**For recurring tasks**, consider storing the rule on the task itself rather than a separate table. When completed, the task spawns a new instance with the next occurrence date. Store `recurrence_pattern` as a simple string ("daily", "weekly:mon", "monthly:15", "cron:0 9 * * 1") and parse it in the API layer.

**For analytics**, you already have `task_history` — the main work is aggregation queries and a charting library on the frontend. Recharts or Chart.js would integrate cleanly with your existing vanilla JS approach.

---

## Summary: Your Competitive Position

You're at roughly **Trello-level functionality** right now, but with significantly better workflow customisation and the unique Peter/heartbeat integration that no commercial tool offers. The gaps are primarily in features that commercial tools have had years to polish: subtasks, recurring tasks, advanced filtering, and analytics.

The good news is that your architecture is already designed for most of these — `task_history`, `task_reminders`, `task_attachments`, and `task_comments` tables all exist and just need UI surfaces and wiring. You're maybe 2-3 focused phases away from having something that genuinely rivals Linear or Todoist for your specific use case, while maintaining the AI-agent integration that makes your system fundamentally different from anything on the market.

**If you could only pick three improvements**, go with:
1. **Subtasks** — the single biggest gap for managing complex work
2. **Recurring tasks** — eliminates the most common manual overhead
3. **Activity timeline UI** — gives you visibility into Peter's autonomous actions
