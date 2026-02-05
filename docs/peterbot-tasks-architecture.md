# Peterbot Task Management System — Architecture Specification

## Overview

A unified task management system with four distinct list types, accessible via Discord (Peterbot) and a web dashboard UI. Built on Supabase with real-time subscriptions powering both interfaces.

---

## 1. The Four Lists

### 1.1 Personal ToDo (`personal_todo`)
**Owner:** Chris | **Managed by:** Peter (scheduling, reminders)

Chris's personal task list. Peter can schedule tasks, set reminders, nudge about overdue items, and mark things done on Chris's behalf. Think of Peter as a PA managing Chris's action items.

**Key behaviours:**
- Peter can proactively remind Chris via Discord DM or channel
- Supports recurring tasks (e.g., "Chase supplier every Monday")
- Due date + scheduled date (when to surface it) are distinct
- Can be created from Discord natural language: *"Peter, remind me to update the eBay listings on Friday"*

### 1.2 Peter Work Queue (`peter_queue`)
**Owner:** Peter | **Worked by:** Peter (via heartbeat)

A backlog of work items Peter can pull from during heartbeat cycles. These are defined, actionable tasks — not vague ideas. Peter selects items based on priority, dependencies, and current context.

**Key behaviours:**
- Items have an estimated complexity/effort field
- Peter can auto-assign to himself during heartbeat
- Completion produces artefacts (PRs, messages, reports) linked back to the task
- Feeds from approved ideas (promotion from Ideas Dump)
- Status includes `queued` → `in_heartbeat` → `in_progress` → `review` → `done`

### 1.3 Ideas Dump (`idea`)
**Owner:** Chris + Peter | **Quick capture, slow process**

A low-friction capture space. Chris fires off ideas via Discord message and Peter logs them. Peter can also add ideas from conversation analysis, research findings, or pattern spotting. Ideas can be promoted to the Work Queue or Research Queue once refined.

**Key behaviours:**
- Minimal required fields — just a title/description is enough to capture
- Can be enriched later with categories, links, feasibility notes
- Peter can export/search across ideas + past conversations to find undelivered concepts
- Source tracking: where did this idea come from? (Discord message, conversation, research, etc.)
- Promotion workflow: idea → refined → approved → moved to `peter_queue` or `research`

### 1.4 Proactive Research Queue (`research`)
**Owner:** Peter | **Autonomous investigation**

Topics for Peter to research proactively — the kind of exploratory work that feeds the business. Peter picks items up, investigates, and produces findings that may generate new ideas or work items.

**Key behaviours:**
- Research produces structured findings (summary, sources, recommendations)
- Findings can spawn new ideas or work queue items (linked)
- Supports research depth levels: `shallow` (quick scan), `standard`, `deep` (comprehensive)
- Peter can self-generate research topics based on patterns and trends
- Status: `queued` → `researching` → `findings_ready` → `reviewed` → `actioned` / `parked`

---

## 2. Database Schema (Supabase)

### 2.1 Enums

```sql
-- List types
CREATE TYPE task_list_type AS ENUM (
  'personal_todo',
  'peter_queue',
  'idea',
  'research'
);

-- Unified status with per-list interpretation
CREATE TYPE task_status AS ENUM (
  'inbox',           -- Captured but not triaged
  'scheduled',       -- Has a scheduled/due date (personal_todo)
  'queued',          -- Ready to be worked (peter_queue, research)
  'in_heartbeat',    -- Peter has picked this up for current heartbeat cycle
  'in_progress',     -- Actively being worked
  'review',          -- Awaiting review/approval
  'findings_ready',  -- Research complete, awaiting review
  'done',            -- Completed
  'cancelled',       -- Abandoned
  'parked'           -- On hold / not now
);

CREATE TYPE task_priority AS ENUM (
  'critical',   -- Drop everything
  'high',       -- Do soon
  'medium',     -- Normal priority
  'low',        -- When you get to it
  'someday'     -- No urgency at all
);

CREATE TYPE research_depth AS ENUM (
  'shallow',    -- Quick scan, 5-10 min
  'standard',   -- Normal research pass
  'deep'        -- Comprehensive investigation
);

CREATE TYPE idea_source AS ENUM (
  'discord_message',
  'conversation',     -- From Claude/Peterbot conversation analysis
  'research',         -- Spawned from research findings
  'manual',           -- Added via dashboard
  'pattern',          -- Peter spotted a pattern/opportunity
  'external'          -- From external source (article, competitor, etc.)
);
```

### 2.2 Core Tables

```sql
-- ===========================================
-- CATEGORIES (shared across all list types)
-- ===========================================
CREATE TABLE task_categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL UNIQUE,
  slug TEXT NOT NULL UNIQUE,
  color TEXT,                          -- Hex colour for UI badges
  icon TEXT,                           -- Optional icon identifier
  description TEXT,
  sort_order INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Seed some sensible defaults
INSERT INTO task_categories (name, slug, color) VALUES
  ('Hadley Bricks', 'hadley-bricks', '#F59E0B'),
  ('Peterbot', 'peterbot', '#6366F1'),
  ('FamilyFuel', 'familyfuel', '#10B981'),
  ('Infrastructure', 'infrastructure', '#6B7280'),
  ('eBay', 'ebay', '#E11D48'),
  ('BrickLink', 'bricklink', '#3B82F6'),
  ('Vinted', 'vinted', '#14B8A6'),
  ('Amazon', 'amazon', '#F97316'),
  ('Running', 'running', '#22C55E'),
  ('Personal', 'personal', '#8B5CF6'),
  ('Finance', 'finance', '#EAB308'),
  ('Home', 'home', '#78716C');


-- ===========================================
-- TASKS (the main table)
-- ===========================================
CREATE TABLE tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Classification
  list_type task_list_type NOT NULL,
  status task_status NOT NULL DEFAULT 'inbox',
  priority task_priority NOT NULL DEFAULT 'medium',
  
  -- Content
  title TEXT NOT NULL,
  description TEXT,                     -- Markdown supported
  
  -- Dates
  due_date TIMESTAMPTZ,                 -- When it's due
  scheduled_date TIMESTAMPTZ,           -- When to surface/start it
  completed_at TIMESTAMPTZ,
  
  -- Recurrence (for personal_todo)
  recurrence_rule JSONB,                -- iCal RRULE as JSON
  -- e.g., {"freq": "weekly", "byday": ["MO"], "interval": 1}
  next_occurrence TIMESTAMPTZ,          -- Pre-calculated next due date
  
  -- Ideas-specific
  idea_source idea_source,              -- Where did this idea come from?
  source_reference TEXT,                -- Discord message ID, conversation URL, etc.
  promoted_to UUID REFERENCES tasks(id),-- If idea was promoted to a queue/research item
  
  -- Research-specific
  research_depth research_depth,
  research_findings JSONB,              -- Structured findings
  -- e.g., {"summary": "...", "sources": [...], "recommendations": [...]}
  
  -- Peter queue-specific
  estimated_effort TEXT,                -- 'trivial', '30min', '2hr', 'half_day', 'multi_day'
  heartbeat_id TEXT,                    -- Which heartbeat cycle picked this up
  
  -- Relationships
  parent_task_id UUID REFERENCES tasks(id), -- Sub-task support
  spawned_from_id UUID REFERENCES tasks(id),-- Research → idea/task lineage
  
  -- Metadata
  created_by TEXT NOT NULL DEFAULT 'chris', -- 'chris' or 'peter'
  assigned_to TEXT DEFAULT 'chris',         -- 'chris' or 'peter'
  sort_order INTEGER DEFAULT 0,
  is_pinned BOOLEAN DEFAULT false,
  
  -- Discord context
  discord_message_id TEXT,              -- Original Discord message that created this
  discord_channel_id TEXT,              -- Channel for responses/reminders
  
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for common query patterns
CREATE INDEX idx_tasks_list_type ON tasks(list_type);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_priority ON tasks(priority);
CREATE INDEX idx_tasks_due_date ON tasks(due_date) WHERE due_date IS NOT NULL;
CREATE INDEX idx_tasks_scheduled_date ON tasks(scheduled_date) WHERE scheduled_date IS NOT NULL;
CREATE INDEX idx_tasks_list_status ON tasks(list_type, status);
CREATE INDEX idx_tasks_assigned ON tasks(assigned_to, status);
CREATE INDEX idx_tasks_heartbeat ON tasks(heartbeat_id) WHERE heartbeat_id IS NOT NULL;

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tasks_updated_at
  BEFORE UPDATE ON tasks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- ===========================================
-- TASK ↔ CATEGORY (many-to-many)
-- ===========================================
CREATE TABLE task_category_links (
  task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
  category_id UUID REFERENCES task_categories(id) ON DELETE CASCADE,
  PRIMARY KEY (task_id, category_id)
);

CREATE INDEX idx_task_category_task ON task_category_links(task_id);
CREATE INDEX idx_task_category_cat ON task_category_links(category_id);


-- ===========================================
-- ATTACHMENTS
-- ===========================================
CREATE TABLE task_attachments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  
  filename TEXT NOT NULL,
  file_path TEXT NOT NULL,               -- Supabase storage path
  file_size INTEGER,
  mime_type TEXT,
  
  -- Or external link
  external_url TEXT,                     -- Link to external resource
  
  uploaded_by TEXT DEFAULT 'chris',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_attachments_task ON task_attachments(task_id);


-- ===========================================
-- COMMENTS / ACTIVITY THREAD
-- ===========================================
CREATE TABLE task_comments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  
  author TEXT NOT NULL,                  -- 'chris' or 'peter'
  content TEXT NOT NULL,                 -- Markdown
  
  -- For Peter's automated updates
  is_system_message BOOLEAN DEFAULT false,  -- "Status changed to in_progress"
  
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_comments_task ON task_comments(task_id);


-- ===========================================
-- REMINDERS
-- ===========================================
CREATE TABLE task_reminders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  
  remind_at TIMESTAMPTZ NOT NULL,
  channel TEXT NOT NULL DEFAULT 'discord',  -- 'discord', 'dashboard'
  message TEXT,                             -- Custom reminder message
  
  is_sent BOOLEAN DEFAULT false,
  sent_at TIMESTAMPTZ,
  
  -- Recurring reminders
  is_recurring BOOLEAN DEFAULT false,
  recurrence_rule JSONB,                    -- Same format as task recurrence
  
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_reminders_pending ON task_reminders(remind_at) 
  WHERE is_sent = false;
CREATE INDEX idx_reminders_task ON task_reminders(task_id);


-- ===========================================
-- AUDIT / HISTORY LOG
-- ===========================================
CREATE TABLE task_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  
  action TEXT NOT NULL,                  -- 'created', 'status_changed', 'priority_changed', etc.
  field_name TEXT,                       -- Which field changed
  old_value TEXT,
  new_value TEXT,
  
  actor TEXT NOT NULL,                   -- 'chris' or 'peter'
  
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_history_task ON task_history(task_id);
CREATE INDEX idx_history_created ON task_history(created_at);


-- ===========================================
-- VIEWS for common queries
-- ===========================================

-- Chris's active todos with reminders
CREATE VIEW v_chris_active_todos AS
SELECT 
  t.*,
  array_agg(DISTINCT c.name) FILTER (WHERE c.name IS NOT NULL) as categories,
  (
    SELECT remind_at FROM task_reminders r 
    WHERE r.task_id = t.id AND r.is_sent = false 
    ORDER BY remind_at LIMIT 1
  ) as next_reminder
FROM tasks t
LEFT JOIN task_category_links tcl ON tcl.task_id = t.id
LEFT JOIN task_categories c ON c.id = tcl.category_id
WHERE t.list_type = 'personal_todo'
  AND t.status NOT IN ('done', 'cancelled')
GROUP BY t.id;

-- Peter's available work (ready to pull into heartbeat)
CREATE VIEW v_peter_available_work AS
SELECT 
  t.*,
  array_agg(DISTINCT c.name) FILTER (WHERE c.name IS NOT NULL) as categories
FROM tasks t
LEFT JOIN task_category_links tcl ON tcl.task_id = t.id
LEFT JOIN task_categories c ON c.id = tcl.category_id
WHERE t.list_type = 'peter_queue'
  AND t.status = 'queued'
GROUP BY t.id
ORDER BY 
  CASE t.priority
    WHEN 'critical' THEN 0
    WHEN 'high' THEN 1
    WHEN 'medium' THEN 2
    WHEN 'low' THEN 3
    WHEN 'someday' THEN 4
  END,
  t.sort_order,
  t.created_at;

-- Unprocessed ideas
CREATE VIEW v_unprocessed_ideas AS
SELECT 
  t.*,
  array_agg(DISTINCT c.name) FILTER (WHERE c.name IS NOT NULL) as categories
FROM tasks t
LEFT JOIN task_category_links tcl ON tcl.task_id = t.id
LEFT JOIN task_categories c ON c.id = tcl.category_id
WHERE t.list_type = 'idea'
  AND t.status IN ('inbox', 'scheduled')
  AND t.promoted_to IS NULL
GROUP BY t.id
ORDER BY t.created_at DESC;

-- Active research with findings
CREATE VIEW v_active_research AS
SELECT 
  t.*,
  array_agg(DISTINCT c.name) FILTER (WHERE c.name IS NOT NULL) as categories,
  (SELECT count(*) FROM tasks spawned WHERE spawned.spawned_from_id = t.id) as spawned_items
FROM tasks t
LEFT JOIN task_category_links tcl ON tcl.task_id = t.id
LEFT JOIN task_categories c ON c.id = tcl.category_id
WHERE t.list_type = 'research'
  AND t.status NOT IN ('done', 'cancelled', 'parked')
GROUP BY t.id
ORDER BY 
  CASE t.priority
    WHEN 'critical' THEN 0
    WHEN 'high' THEN 1
    WHEN 'medium' THEN 2
    WHEN 'low' THEN 3
    WHEN 'someday' THEN 4
  END;
```

### 2.3 Row Level Security

```sql
-- Enable RLS
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_history ENABLE ROW LEVEL SECURITY;

-- Since this is single-user (Chris + Peter service role),
-- policies are straightforward:

-- Authenticated user (Chris via dashboard) gets full access
CREATE POLICY "auth_full_access" ON tasks
  FOR ALL USING (auth.role() = 'authenticated');

-- Service role (Peter) gets full access
CREATE POLICY "service_full_access" ON tasks
  FOR ALL USING (auth.role() = 'service_role');

-- Repeat pattern for other tables...
```

### 2.4 Supabase Realtime

```sql
-- Enable realtime for live dashboard updates
ALTER PUBLICATION supabase_realtime ADD TABLE tasks;
ALTER PUBLICATION supabase_realtime ADD TABLE task_comments;
ALTER PUBLICATION supabase_realtime ADD TABLE task_reminders;
```

### 2.5 Storage Bucket

```sql
-- Attachments bucket
INSERT INTO storage.buckets (id, name, public)
VALUES ('task-attachments', 'task-attachments', false);

-- Storage policy
CREATE POLICY "Authenticated access"
ON storage.objects FOR ALL
USING (bucket_id = 'task-attachments' AND auth.role() = 'authenticated');
```

---

## 3. Discord Interaction Design

### 3.1 Slash Commands

```
/todo add <title> [due:<date>] [priority:<level>] [category:<name>]
/todo list [status:<status>] [due:today|week|overdue]
/todo done <id_or_search>
/todo snooze <id_or_search> <until>
/todo schedule <id_or_search> <date>

/queue add <title> [effort:<estimate>] [priority:<level>] [category:<name>]
/queue list [status:<status>] [priority:<level>]
/queue next                          -- Show top priority item
/queue grab <id_or_search>           -- Peter claims for heartbeat

/idea <description>                  -- Quick capture, minimal friction
/idea add <title> [source:<source>] [category:<name>]
/idea list [category:<name>] [status:<status>]
/idea promote <id_or_search> [to:queue|research]
/idea search <query>                 -- Search ideas + past conversations

/research add <topic> [depth:<level>] [priority:<level>]
/research list [status:<status>]
/research findings <id>              -- Show research results
/research spawn <research_id> <type:idea|queue> <title>  -- Create from findings
```

### 3.2 Natural Language Interaction

Peter should parse intent from natural messages. These are the patterns to recognise:

```
Capture Patterns (→ idea):
  "Peter, idea: <anything>"
  "Peter, add idea <anything>"
  "Peter, save this idea: <anything>"
  "Peter, jot down <anything>"
  "Peter, note: <anything>"

Todo Patterns (→ personal_todo):
  "Peter, remind me to <task> [on/by <date>]"
  "Peter, I need to <task> [by <date>]"
  "Peter, add to my list: <task>"
  "Peter, schedule <task> for <date>"
  "Peter, todo: <task>"

Queue Patterns (→ peter_queue):
  "Peter, you should <task>"
  "Peter, add to your queue: <task>"
  "Peter, when you get a chance, <task>"
  "Peter, future task: <task>"

Research Patterns (→ research):
  "Peter, look into <topic>"
  "Peter, research <topic>"
  "Peter, investigate <topic>"
  "Peter, dig into <topic>"
  "Peter, find out about <topic>"
```

### 3.3 Proactive Discord Behaviours

Peter should proactively use Discord to:

| Trigger | Action |
|---------|--------|
| Task due today | Morning summary DM: "You've got 3 things due today: ..." |
| Task overdue | Escalating nudges: gentle → firm → "This has been overdue 5 days" |
| Heartbeat start | Post which queue items Peter is picking up |
| Heartbeat complete | Post summary of completed work with links to artefacts |
| Research findings ready | Post summary + ask if Chris wants to review |
| Ideas pile up | Weekly ideas digest: "You have 12 unprocessed ideas. Top 3 by theme: ..." |
| Pattern spotted | "I've noticed 4 ideas around X — worth consolidating into a project?" |

### 3.4 Discord UI Components

Use Discord's interactive components for quick actions:

```
┌─────────────────────────────────────────────────┐
│ 📋 Your Tasks Due Today                         │
│                                                  │
│ 🔴 Update eBay listing templates (overdue 2d)   │
│ 🟡 Review Vinted scraper results                │
│ 🟢 Chase BrickLink order #4521                  │
│                                                  │
│ [✅ Done] [⏰ Snooze] [📋 Show All]              │
└─────────────────────────────────────────────────┘
```

- **Button rows** for quick status changes (Done, Snooze, Reassign)
- **Select menus** for priority/category changes
- **Modals** for adding descriptions or scheduling details
- **Thread creation** for task discussion

---

## 4. Dashboard UI Design

### 4.1 Page Structure

Add to the existing Hadley Bricks dashboard as a new top-level section: **Tasks**.

```
/dashboard/tasks                    -- Overview / combined view
/dashboard/tasks/todos              -- Chris's personal todo list
/dashboard/tasks/queue              -- Peter's work queue
/dashboard/tasks/ideas              -- Ideas dump
/dashboard/tasks/research           -- Research queue
/dashboard/tasks/[id]               -- Task detail view
```

### 4.2 Overview Page (`/dashboard/tasks`)

A unified dashboard showing all four lists at a glance:

```
┌────────────────────────────────────────────────────────────────┐
│  Tasks                                          [+ Quick Add]  │
├──────────────┬──────────────┬───────────────┬─────────────────┤
│  📋 My Todos │  🤖 Peter Q  │  💡 Ideas     │  🔬 Research    │
│  ───────────  │  ──────────  │  ──────────── │  ──────────────│
│  3 due today │  7 queued    │  12 unprocessed│  2 in progress │
│  1 overdue   │  2 in prog   │  3 this week  │  1 findings    │
│              │              │               │    ready       │
│  [View All]  │  [View All]  │  [View All]   │  [View All]    │
├──────────────┴──────────────┴───────────────┴─────────────────┤
│  ⏰ Upcoming                                                   │
│  ─────────────────────────────────────────────                 │
│  Today    Review Vinted results         🟡 medium    📋 todo  │
│  Today    Chase BrickLink #4521         🟢 low       📋 todo  │
│  Tomorrow Update listing templates      🔴 high      📋 todo  │
│  Fri      Research Qwen3-TTS pricing    🟡 medium    🔬 rsrch │
├────────────────────────────────────────────────────────────────┤
│  📊 Recent Activity                                            │
│  ─────────────────                                             │
│  Peter completed "Fix Discord embed formatting"    2h ago      │
│  New idea captured: "Marketplace price alerts"     3h ago      │
│  Research findings ready: "Vinted API options"     yesterday   │
└────────────────────────────────────────────────────────────────┘
```

### 4.3 List Views

Each list type gets a filterable, sortable view:

**Filters bar:**
- Status (multi-select chips)
- Priority (multi-select chips)  
- Category (multi-select with colour dots)
- Due date range
- Search (full-text across title + description)
- Created by (Chris / Peter)

**View modes:**
- **List view** (default) — compact rows with inline status/priority/category badges
- **Kanban view** — columns by status, drag-and-drop to change status
- **Calendar view** (todos only) — tasks plotted on due/scheduled dates

**Bulk actions:**
- Multi-select → change status, priority, category
- Multi-select → delete / archive

### 4.4 Task Detail Panel

Slide-over or dedicated page showing full task context:

```
┌──────────────────────────────────────────────────────┐
│  Update eBay listing templates                    ✏️  │
│  ─────────────────────────────────────────────────── │
│                                                      │
│  Status: [🟡 Scheduled ▾]    Priority: [🔴 High ▾]  │
│  Due: Feb 10, 2026           Scheduled: Feb 7, 2026 │
│  Category: [eBay] [Hadley Bricks]                    │
│  Assigned: Chris             Created by: Peter       │
│                                                      │
│  ── Description ──────────────────────────────────── │
│  Need to update all active listing templates to      │
│  include the new shipping policy and refresh the     │
│  photo requirements section.                         │
│                                                      │
│  ── Attachments ──────────────────────────────────── │
│  📎 new-shipping-policy.pdf        [+ Add]           │
│  🔗 https://ebay.co.uk/...                           │
│                                                      │
│  ── Reminders ────────────────────────────────────── │
│  ⏰ Feb 7 09:00 - "Start on listing templates"       │
│  ⏰ Feb 10 17:00 - "Templates due today"   [+ Add]   │
│                                                      │
│  ── Sub-tasks ────────────────────────────────────── │
│  ☑ Draft new template copy                           │
│  ☐ Update photos section                             │
│  ☐ Apply to all active listings           [+ Add]    │
│                                                      │
│  ── Activity ─────────────────────────────────────── │
│  Chris: "Focus on the top 20 listings first"  2d ago │
│  Peter: Status changed inbox → scheduled      3d ago │
│  Peter: Created from Discord message          3d ago │
│  ────────────────────────────────────────────────── │
│  [Add comment...]                                    │
└──────────────────────────────────────────────────────┘
```

### 4.5 Quick Add Modal

Triggered by `[+ Quick Add]` button or keyboard shortcut (`N`):

```
┌──────────────────────────────────────────────┐
│  Quick Add Task                              │
│                                              │
│  Title: [________________________________]   │
│                                              │
│  List: (•) My Todo  ( ) Peter Queue          │
│        ( ) Idea     ( ) Research             │
│                                              │
│  Priority: [Medium ▾]                        │
│  Due date: [Pick date...]                    │
│  Category: [Select... ▾]                     │
│                                              │
│  Description (optional):                     │
│  [________________________________]          │
│  [________________________________]          │
│                                              │
│              [Cancel]  [Create Task]         │
└──────────────────────────────────────────────┘
```

---

## 5. Peterbot Integration Architecture

### 5.1 Module Structure

```
peterbot/
├── modules/
│   └── tasks/
│       ├── index.ts                 -- Module registration
│       ├── commands/
│       │   ├── todo.ts              -- /todo slash command handler
│       │   ├── queue.ts             -- /queue slash command handler
│       │   ├── idea.ts              -- /idea slash command handler
│       │   └── research.ts          -- /research slash command handler
│       ├── nlp/
│       │   └── task-intent.ts       -- Natural language → task intent parser
│       ├── services/
│       │   ├── task-service.ts      -- CRUD operations via Supabase
│       │   ├── reminder-service.ts  -- Reminder scheduling + delivery
│       │   ├── heartbeat-hook.ts    -- Hook into heartbeat for queue pulling
│       │   └── idea-scanner.ts      -- Scan conversations for undelivered ideas
│       ├── components/
│       │   ├── task-embed.ts        -- Discord embed builders
│       │   ├── task-buttons.ts      -- Button/select component builders
│       │   └── task-modals.ts       -- Modal form builders
│       └── cron/
│           ├── morning-digest.ts    -- Daily summary at configured time
│           ├── overdue-nudge.ts     -- Periodic overdue check
│           ├── weekly-ideas.ts      -- Weekly ideas digest
│           └── reminder-poller.ts   -- Poll and fire due reminders
```

### 5.2 Task Service Interface

```typescript
interface TaskService {
  // CRUD
  create(input: CreateTaskInput): Promise<Task>;
  update(id: string, input: UpdateTaskInput): Promise<Task>;
  delete(id: string): Promise<void>;
  getById(id: string): Promise<Task>;
  
  // List queries
  listByType(type: TaskListType, filters?: TaskFilters): Promise<Task[]>;
  getOverdue(): Promise<Task[]>;
  getDueToday(): Promise<Task[]>;
  getDueThisWeek(): Promise<Task[]>;
  
  // Status transitions
  markDone(id: string, actor: string): Promise<Task>;
  snooze(id: string, until: Date): Promise<Task>;
  promote(ideaId: string, targetList: 'peter_queue' | 'research'): Promise<Task>;
  grabForHeartbeat(taskId: string, heartbeatId: string): Promise<Task>;
  
  // Search
  search(query: string, filters?: TaskFilters): Promise<Task[]>;
  searchIdeasAndConversations(query: string): Promise<SearchResult[]>;
  
  // Reminders
  addReminder(taskId: string, input: CreateReminderInput): Promise<Reminder>;
  getPendingReminders(): Promise<Reminder[]>;
  markReminderSent(reminderId: string): Promise<void>;
  
  // Comments
  addComment(taskId: string, input: CreateCommentInput): Promise<Comment>;
  
  // Attachments
  addAttachment(taskId: string, input: CreateAttachmentInput): Promise<Attachment>;
  
  // Bulk
  bulkUpdateStatus(ids: string[], status: TaskStatus): Promise<void>;
}

interface TaskFilters {
  status?: TaskStatus[];
  priority?: TaskPriority[];
  categories?: string[];
  assignedTo?: string;
  dueBefore?: Date;
  dueAfter?: Date;
  search?: string;
}
```

### 5.3 Heartbeat Integration

During heartbeat cycles, Peter should:

1. **Check queue** — Pull top-priority items from `peter_queue` with status `queued`
2. **Claim items** — Move to `in_heartbeat` with heartbeat ID
3. **Work items** — Execute tasks, update status to `in_progress`
4. **Report completion** — Move to `done`, add comment with artefact links
5. **Check research** — If queue is clear, pick up research items

```typescript
// In heartbeat hook
async function heartbeatTaskPull(heartbeatId: string): Promise<Task[]> {
  const available = await taskService.listByType('peter_queue', {
    status: ['queued'],
  });
  
  // Pick top 3 by priority + effort (prefer quick wins)
  const selected = selectForHeartbeat(available, {
    maxItems: 3,
    preferEffort: ['trivial', '30min'],
  });
  
  for (const task of selected) {
    await taskService.grabForHeartbeat(task.id, heartbeatId);
  }
  
  return selected;
}
```

### 5.4 Reminder System

A polling-based reminder system (simplest to implement, upgrade to pg_cron later if needed):

```typescript
// Runs every 60 seconds
async function pollReminders() {
  const pending = await supabase
    .from('task_reminders')
    .select('*, task:tasks(*)')
    .eq('is_sent', false)
    .lte('remind_at', new Date().toISOString())
    .order('remind_at');

  for (const reminder of pending.data) {
    await sendDiscordReminder(reminder);
    await supabase
      .from('task_reminders')
      .update({ is_sent: true, sent_at: new Date().toISOString() })
      .eq('id', reminder.id);
    
    // Handle recurring
    if (reminder.is_recurring && reminder.recurrence_rule) {
      const nextDate = calculateNext(reminder.recurrence_rule);
      await supabase.from('task_reminders').insert({
        ...reminder,
        id: undefined,
        remind_at: nextDate,
        is_sent: false,
        sent_at: null,
      });
    }
  }
}
```

---

## 6. Idea Scanner — Cross-Source Intelligence

One of Peter's most valuable capabilities: scanning across sources to find ideas that haven't been delivered yet.

### 6.1 Sources to Scan

| Source | Method | What to look for |
|--------|--------|-----------------|
| Ideas dump | Direct DB query | Status = `inbox` items older than 7 days |
| Past Discord conversations | Discord message history search | Messages with idea-like language from Chris |
| Claude conversation history | Conversation search API | Topics discussed but never actioned |
| Research findings | DB query on research tasks | Recommendations not yet spawned into work items |
| Task comments | DB query | "We should also..." patterns in comments |

### 6.2 Idea Export / Review Command

```
/idea review              -- Start an interactive idea review session
/idea export [format]     -- Export all ideas as markdown/CSV
/idea stale               -- Show ideas that haven't been touched in 14+ days
/idea themes              -- Peter analyses ideas and groups by theme
```

---

## 7. API Layer (for Dashboard)

### 7.1 Supabase Client Queries

Since the dashboard is Next.js + Supabase, use the Supabase client directly with RLS:

```typescript
// hooks/useTasks.ts
export function useTasks(listType: TaskListType, filters?: TaskFilters) {
  return useQuery(['tasks', listType, filters], async () => {
    let query = supabase
      .from('tasks')
      .select(`
        *,
        categories:task_category_links(
          category:task_categories(*)
        ),
        attachments:task_attachments(count),
        comments:task_comments(count),
        next_reminder:task_reminders(remind_at)
      `)
      .eq('list_type', listType)
      .order('sort_order')
      .order('created_at', { ascending: false });
    
    if (filters?.status?.length) {
      query = query.in('status', filters.status);
    }
    if (filters?.priority?.length) {
      query = query.in('priority', filters.priority);
    }
    // ... more filters
    
    return query;
  });
}
```

### 7.2 Realtime Subscriptions

```typescript
// Live updates when Peter creates/modifies tasks
useEffect(() => {
  const channel = supabase
    .channel('task-changes')
    .on('postgres_changes', {
      event: '*',
      schema: 'public',
      table: 'tasks',
    }, (payload) => {
      // Invalidate react-query cache for affected list
      queryClient.invalidateQueries(['tasks', payload.new?.list_type]);
    })
    .subscribe();
    
  return () => { supabase.removeChannel(channel); };
}, []);
```

---

## 8. Implementation Phases

### Phase 1 — Foundation (MVP)
- [ ] Supabase schema migration (all tables, enums, views, indexes)
- [ ] `TaskService` class with full CRUD
- [ ] `/todo add`, `/todo list`, `/todo done` slash commands
- [ ] `/idea <text>` quick capture command
- [ ] Basic task embed display in Discord
- [ ] Dashboard: task list page with filters (single list view)
- [ ] Dashboard: quick add modal

### Phase 2 — Intelligence
- [ ] Natural language intent parsing for all four list types
- [ ] `/queue` slash commands + heartbeat integration hook
- [ ] `/research` slash commands
- [ ] Reminder system (polling + Discord delivery)
- [ ] Morning digest cron
- [ ] Dashboard: overview page with all four lists
- [ ] Dashboard: task detail panel with comments

### Phase 3 — Rich Features
- [ ] Attachments (Supabase storage + Discord file handling)
- [ ] Sub-tasks
- [ ] Kanban view on dashboard
- [ ] Idea promotion workflow (idea → queue/research)
- [ ] Overdue nudge system with escalation
- [ ] Recurring tasks
- [ ] Discord button/select interactions for quick status changes

### Phase 4 — Autonomous Intelligence
- [ ] Idea scanner across sources (Discord history, conversation search, stale ideas)
- [ ] Weekly ideas digest with theme grouping
- [ ] Peter self-generating research topics
- [ ] Research → idea/task spawning with lineage tracking
- [ ] Calendar view for todos
- [ ] Bulk operations on dashboard
- [ ] Export/reporting

---

## 9. Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Single `tasks` table vs separate tables per list | **Single table with `list_type` discriminator** | Simpler queries, shared infrastructure, easy promotion between lists |
| Reminder delivery | **Polling (60s interval)** | Simple, reliable, good enough for personal use. Upgrade to pg_cron/edge functions later if needed |
| Discord interaction model | **Slash commands + NLP fallback** | Slash commands for structured input, NLP for conversational flow |
| Task IDs in Discord | **Short display IDs** (first 8 chars of UUID) + **fuzzy title search** | Nobody wants to type full UUIDs. `/todo done ebay` should match "Update eBay listing templates" |
| Dashboard framework | **Extend existing Hadley Bricks dashboard** | Reuse existing auth, layout, Supabase config. New route group under `/dashboard/tasks` |
| Attachments | **Supabase Storage** | Already in the stack, handles auth, cheap |
| History/audit | **Separate `task_history` table** | Don't pollute the main tasks table, enables timeline view |
