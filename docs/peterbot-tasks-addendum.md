# Peterbot Tasks — Addendum: Heartbeat Scheduling, Drag-and-Drop & Visual Design

**Extends:** `peterbot-tasks-architecture.md`

---

## 1. Schema Changes for Heartbeat Scheduling

### 1.1 Updated Status Enum

Add `heartbeat_scheduled` to the existing `task_status` enum:

```sql
-- Add new status value
ALTER TYPE task_status ADD VALUE 'heartbeat_scheduled' AFTER 'scheduled';
```

Updated status flow for `peter_queue`:

```
queued ──→ heartbeat_scheduled ──→ in_heartbeat ──→ in_progress ──→ review ──→ done
  │                                       ↑
  └───────────────── (Add Now) ───────────┘
```

- **queued** — Waiting in the backlog. Not yet scheduled.
- **heartbeat_scheduled** — Explicitly scheduled for a future heartbeat cycle. Has a target date.
- **in_heartbeat** — Peter has pulled this into the current active heartbeat cycle.
- **in_progress** — Actively being worked on within the heartbeat.
- **review** — Work complete, awaiting Chris's review.
- **done** — Complete.

### 1.2 New Fields on `tasks` Table

```sql
ALTER TABLE tasks ADD COLUMN heartbeat_scheduled_for DATE;
ALTER TABLE tasks ADD COLUMN heartbeat_slot_order INTEGER DEFAULT 0;

-- Index for the heartbeat poller
CREATE INDEX idx_tasks_heartbeat_schedule 
  ON tasks(heartbeat_scheduled_for) 
  WHERE status = 'heartbeat_scheduled' AND heartbeat_scheduled_for IS NOT NULL;

COMMENT ON COLUMN tasks.heartbeat_scheduled_for IS 
  'Target date for when Peter should pull this into a heartbeat cycle. NULL if not scheduled.';
COMMENT ON COLUMN tasks.heartbeat_slot_order IS 
  'Ordering within a heartbeat day. Lower numbers are worked first.';
```

### 1.3 Heartbeat Plan View

A view for Peter to see what's coming up across scheduled heartbeat days:

```sql
CREATE VIEW v_heartbeat_plan AS
SELECT 
  t.heartbeat_scheduled_for AS plan_date,
  count(*) AS task_count,
  sum(CASE 
    WHEN t.estimated_effort IN ('trivial', '30min') THEN 1
    WHEN t.estimated_effort = '2hr' THEN 2
    WHEN t.estimated_effort = 'half_day' THEN 4
    WHEN t.estimated_effort = 'multi_day' THEN 8
    ELSE 2
  END) AS effort_points,
  array_agg(
    json_build_object(
      'id', t.id,
      'title', t.title,
      'priority', t.priority,
      'effort', t.estimated_effort,
      'slot_order', t.heartbeat_slot_order
    ) ORDER BY t.heartbeat_slot_order, t.priority
  ) AS tasks
FROM tasks t
WHERE t.status = 'heartbeat_scheduled'
  AND t.heartbeat_scheduled_for IS NOT NULL
GROUP BY t.heartbeat_scheduled_for
ORDER BY t.heartbeat_scheduled_for;
```

### 1.4 Updated Heartbeat Hook

```typescript
// In heartbeat service — runs at the start of each heartbeat cycle
async function heartbeatStartCycle(heartbeatId: string): Promise<Task[]> {
  const today = new Date().toISOString().split('T')[0];
  
  // 1. Pull in any tasks scheduled for today or earlier
  const { data: scheduled } = await supabase
    .from('tasks')
    .select('*')
    .eq('status', 'heartbeat_scheduled')
    .lte('heartbeat_scheduled_for', today)
    .order('heartbeat_slot_order')
    .order('priority');

  // 2. Move them to in_heartbeat
  if (scheduled?.length) {
    const ids = scheduled.map(t => t.id);
    await supabase
      .from('tasks')
      .update({ 
        status: 'in_heartbeat', 
        heartbeat_id: heartbeatId,
        heartbeat_scheduled_for: null
      })
      .in('id', ids);
  }

  // 3. If capacity remains, pull from queued backlog
  const remaining = MAX_HEARTBEAT_ITEMS - (scheduled?.length || 0);
  if (remaining > 0) {
    const { data: queued } = await supabase
      .from('tasks')
      .select('*')
      .eq('list_type', 'peter_queue')
      .eq('status', 'queued')
      .order('priority')  // critical first
      .order('sort_order')
      .limit(remaining);

    if (queued?.length) {
      const ids = queued.map(t => t.id);
      await supabase
        .from('tasks')
        .update({ status: 'in_heartbeat', heartbeat_id: heartbeatId })
        .in('id', ids);
    }

    return [...(scheduled || []), ...(queued || [])];
  }

  return scheduled || [];
}
```

### 1.5 "Add to Heartbeat" Discord Command

```
/queue heartbeat <id_or_search>                     -- Add to current heartbeat (now)
/queue heartbeat <id_or_search> schedule <date>     -- Schedule for future heartbeat
/queue heartbeat plan [date]                        -- Show heartbeat plan for a date
/queue heartbeat today                              -- Show what's in today's heartbeat
```

Discord button interaction on task embeds:
```
┌─────────────────────────────────────────────────┐
│ 🤖 Task: Fix Discord embed formatting           │
│ Priority: 🔴 High | Effort: 2hr | Peterbot     │
│                                                  │
│ [⚡ Heartbeat Now] [📅 Schedule] [✅ Done] [···]│
└─────────────────────────────────────────────────┘
```

---

## 2. Drag-and-Drop Implementation

### 2.1 Library: `@dnd-kit`

Use `@dnd-kit/core` + `@dnd-kit/sortable` for production. It handles:
- Mouse, touch, and keyboard drag interactions
- Accessible (ARIA live regions, keyboard nav)
- Collision detection strategies
- Smooth animations via CSS transforms
- Custom drag overlays (ghost images)

```bash
npm install @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities
```

### 2.2 DnD Interaction Model

**Drag types:**

| Interaction | Source | Target | Effect |
|---|---|---|---|
| Status change | Card in Column A | Column B | `task.status = columnB.id` |
| Reorder | Card at position N | Position M in same column | `task.sort_order` updated |
| Cross-list promote | Idea card | Queue/Research drop zone | `task.list_type` changed, `promoted_to` linked |
| Heartbeat schedule | Queued card | Heartbeat Scheduled column | `task.status = 'heartbeat_scheduled'` |

**Visual feedback during drag:**

| State | Visual |
|---|---|
| Idle | Normal card appearance |
| Drag source | Opacity 0.35, slight rotation (1.5°), dashed border |
| Drag overlay | Card follows cursor, elevated shadow (24px blur), scale 1.02 |
| Valid drop target | Column border becomes dashed accent color, background tints |
| Invalid drop target | No visual change (column appears inert) |
| Drop animation | Card snaps to position with spring physics (200ms) |

### 2.3 Component Architecture

```
KanbanBoard
├── DndContext (from @dnd-kit/core)
│   ├── SortableContext (per column, for reordering)
│   │   ├── KanbanColumn
│   │   │   ├── useDroppable()  ← makes column a drop target
│   │   │   └── SortableTaskCard[]
│   │   │       └── useSortable()  ← makes card draggable + sortable
│   │   └── ...more columns
│   └── DragOverlay  ← floating card that follows cursor
│       └── TaskCard (clone, elevated style)
└── Sensors: PointerSensor, KeyboardSensor, TouchSensor
```

### 2.4 Status Transition Validation

Not all column drops should be valid. The board should enforce legal transitions:

```typescript
const VALID_TRANSITIONS: Record<string, Record<string, string[]>> = {
  peter_queue: {
    queued:              ['heartbeat_scheduled', 'in_heartbeat', 'cancelled'],
    heartbeat_scheduled: ['queued', 'in_heartbeat', 'cancelled'],
    in_heartbeat:        ['in_progress', 'queued'],
    in_progress:         ['review', 'in_heartbeat'],
    review:              ['done', 'in_progress'],
    done:                ['queued'],  // reopen
  },
  personal_todo: {
    inbox:       ['scheduled', 'in_progress', 'done', 'cancelled'],
    scheduled:   ['inbox', 'in_progress', 'done'],
    in_progress: ['done', 'scheduled'],
    done:        ['inbox'],
  },
  idea: {
    inbox:     ['scheduled', 'review', 'done'],
    scheduled: ['inbox', 'review'],
    review:    ['done', 'scheduled'],
    done:      [],  // promoted, no going back
  },
  research: {
    queued:         ['in_progress', 'cancelled'],
    in_progress:    ['findings_ready', 'queued'],
    findings_ready: ['done', 'in_progress'],
    done:           ['queued'],
  },
};

// In DndContext onDragEnd:
function handleDragEnd(event: DragEndEvent) {
  const { active, over } = event;
  if (!over) return;
  
  const task = findTask(active.id);
  const targetColumn = over.id;
  const allowed = VALID_TRANSITIONS[task.list_type]?.[task.status] || [];
  
  if (!allowed.includes(targetColumn)) {
    // Snap back — invalid transition
    return;
  }
  
  // Valid — update status
  updateTaskStatus(task.id, targetColumn);
}
```

### 2.5 Drag-and-Drop for Reordering

Within a column, cards should be reorderable via drag. This updates `sort_order`:

```typescript
// After drop within same column:
async function reorderInColumn(columnId: string, orderedIds: string[]) {
  const updates = orderedIds.map((id, index) => ({
    id,
    sort_order: index * 10,  // gaps for future insertions
  }));
  
  // Batch update
  for (const u of updates) {
    await supabase
      .from('tasks')
      .update({ sort_order: u.sort_order })
      .eq('id', u.id);
  }
}
```

### 2.6 Optimistic Updates

All DnD operations should be optimistic — update the UI immediately, then sync to Supabase in the background. If the API call fails, revert:

```typescript
const queryClient = useQueryClient();

function handleDragEnd(event) {
  const { taskId, newStatus } = parseDropEvent(event);
  
  // Optimistic update
  queryClient.setQueryData(['tasks', activeList], (old) =>
    old.map(t => t.id === taskId ? { ...t, status: newStatus } : t)
  );
  
  // Background sync
  updateTaskMutation.mutate(
    { id: taskId, status: newStatus },
    {
      onError: () => {
        // Revert on failure
        queryClient.invalidateQueries(['tasks', activeList]);
        toast.error('Failed to update task');
      },
    }
  );
}
```

---

## 3. Visual Design System

### 3.1 Colour Tokens

```css
:root {
  /* Brand — Hadley Bricks */
  --navy-900: #0f1729;
  --navy-800: #1a2744;
  --navy-700: #253561;
  --navy-600: #2d4a7a;
  --gold-500:  #f59e0b;
  --gold-400:  #fbbf24;
  --gold-300:  #fde68a;
  --gold-100:  #fef9e7;
  --orange-600: #ea580c;
  --orange-500: #f97316;

  /* Surfaces */
  --bg:      #f7f6f3;
  --card:    #ffffff;
  --border:  #e8e5df;
  --subtle:  #f1f5f9;
  
  /* Text */
  --text-primary:   #1e293b;
  --text-secondary:  #475569;
  --text-muted:      #94a3b8;
  
  /* Priority */
  --priority-critical: #dc2626;
  --priority-high:     #ea580c;
  --priority-medium:   #d97706;
  --priority-low:      #2563eb;
  --priority-someday:  #9ca3af;
  
  /* Status */
  --status-success: #16a34a;
  --status-info:    #2563eb;
  --status-warning: #d97706;
  --status-danger:  #dc2626;
  --status-purple:  #7c3aed;
}
```

### 3.2 Typography

```css
/* Primary font — headings, UI labels */
font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;

/* Monospace — counts, dates, IDs, metadata */
font-family: 'JetBrains Mono', 'Fira Code', monospace;
```

| Element | Size | Weight | Font |
|---|---|---|---|
| Page title | 16px | 800 | Outfit |
| Tab label | 13px | 500/700 | Outfit |
| Column header | 12px | 700 | Outfit (uppercase) |
| Card title | 13px | 600 | Outfit |
| Card metadata | 11px | 500 | JetBrains Mono |
| Badge/pill | 11px | 600 | Outfit |
| Count badge | 10-11px | 700 | JetBrains Mono |
| Muted text | 10px | 400 | Outfit |

### 3.3 Card Design

```
┌─ 3.5px priority-colored left border
│
│  ┌──────────────────────────────────────┐
│  │  Title text (13px, weight 600)        │  ← 12px top/14px side padding
│  │                                       │
│  │  [🔴 High]  [⏱ 2hr]                 │  ← Priority pill + effort badge
│  │  [Peterbot] [eBay]                   │  ← Category badges
│  │                                       │
│  │  📎 2  💬 3   📅 Feb 10    by Peter  │  ← Meta row (JetBrains Mono)
│  │  ─────────────────────────────────── │  ← Subtle divider
│  │  [⚡ Heartbeat]  [✓ Done]            │  ← Action buttons
│  └──────────────────────────────────────┘
│
│  border-radius: 10px
│  box-shadow: 0 1px 3px rgba(0,0,0,0.06)
│  hover: translateY(-1px), shadow 0 4px 12px rgba(0,0,0,0.1)
│  drag: opacity 0.35, rotate(1.5deg), scale(0.98)
```

### 3.4 Heartbeat Scheduling Dropdown

The "Add to Heartbeat" button opens a dropdown anchored to the card:

```
┌─────────────────────────────────────┐
│  ⚡ Schedule for Heartbeat          │  ← Gold gradient header
├─────────────────────────────────────┤
│  ┌───────────────────────────────┐  │
│  │ ⚡ Add to Current Heartbeat   │  │  ← Primary action, gold bg
│  │    Start working on this now  │  │
│  └───────────────────────────────┘  │
│  ┌───────────────────────────────┐  │
│  │ ▶  Next Heartbeat — Wed 5 Feb│  │  ← Secondary action
│  │    Queue for the next cycle   │  │
│  └───────────────────────────────┘  │
├─────────────────────────────────────┤
│  PICK A DAY                         │  ← Date grid
│                                     │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐│
│  │ Thu│ │ Fri│ │ Sat│ │ Sun│ │ Mon││
│  │  5 │ │  6 │ │  7 │ │  8 │ │  9 ││
│  │ ●  │ │●●  │ │    │ │    │ │ ●  ││  ← Dots = tasks already
│  └────┘ └────┘ └────┘ └────┘ └────┘│    scheduled that day
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐│
│  │ Tue│ │ Wed│ │ Thu│ │ Fri│ │ Sat││
│  │ 10 │ │ 11 │ │ 12 │ │ 13 │ │ 14 ││
│  └────┘ └────┘ └────┘ └────┘ └────┘│
└─────────────────────────────────────┘

Width: 300px
Border: 1.5px solid gold-300
Shadow: 0 12px 40px rgba(0,0,0,0.15)
Position: absolute, anchored below the button
z-index: 50 (above click-away overlay at z-30)
```

### 3.5 Animations

| Animation | Duration | Easing | Usage |
|---|---|---|---|
| Card hover lift | 200ms | ease | `translateY(-1px)` + shadow increase |
| Drag start | 200ms | ease | Opacity to 0.35, rotate(1.5°) |
| Column highlight | 250ms | ease | Border + background tint transition |
| Drop snap | 200ms | spring | Card snaps to final position |
| Modal appear | 250ms | ease | Slide down + fade in |
| Toast notification | 200ms in, 150ms out | ease | Slide down from top, fade out |
| Heartbeat pulse | 2.5s | infinite | Column header dot glow for heartbeat columns |
| Card enter | 200ms | ease | `translateY(8px)` → 0 + fade in (staggered per card) |

### 3.6 Responsive Behaviour

| Breakpoint | Layout |
|---|---|
| ≥1280px | All columns visible, no horizontal scroll for 4-column lists |
| 960–1279px | Horizontal scroll for 5+ column lists, 4-column lists fit |
| 640–959px | All lists scroll horizontally, columns at 240px |
| <640px (mobile) | Single column view with collapsible status sections, swipe between columns |

---

## 4. Dashboard Route Structure (Updated)

```
/dashboard/tasks                        -- Overview (4-list summary cards)
/dashboard/tasks/todos                  -- Personal todo Kanban
/dashboard/tasks/queue                  -- Peter queue Kanban  
/dashboard/tasks/ideas                  -- Ideas Kanban
/dashboard/tasks/research               -- Research Kanban
/dashboard/tasks/heartbeat              -- Heartbeat planner (calendar-style)
/dashboard/tasks/[id]                   -- Task detail (slide-over or page)
```

### 4.1 Heartbeat Planner Page (`/dashboard/tasks/heartbeat`)

A dedicated calendar-style view showing what's scheduled for upcoming heartbeats:

```
┌────────────────────────────────────────────────────────────────┐
│  Heartbeat Planner                         [← This Week →]    │
├──────────┬──────────┬──────────┬──────────┬──────────────────┤
│  Wed 4   │  Thu 5   │  Fri 6   │  Sat 7   │  Sun 8          │
│  TODAY   │          │          │          │                  │
│          │          │          │          │                  │
│  ┌─────┐ │  ┌─────┐ │  ┌─────┐ │          │                  │
│  │Build│ │  │Refac│ │  │Bulk │ │          │                  │
│  │BL   │ │  │mem  │ │  │eBay │ │          │                  │
│  │sync │ │  │retri│ │  │endpt│ │          │                  │
│  │🔵 M │ │  │🔴 H │ │  │🔴 H │ │          │                  │
│  └─────┘ │  └─────┘ │  └─────┘ │          │                  │
│  ┌─────┐ │          │          │          │                  │
│  │eBay │ │          │          │          │                  │
│  │templ│ │          │          │          │                  │
│  │🔴 H │ │          │          │          │                  │
│  └─────┘ │          │          │          │                  │
│          │          │          │          │                  │
│  2 tasks │  1 task  │  1 task  │  Empty   │  Empty           │
│  ~12 pts │  ~4 pts  │  ~8 pts  │          │                  │
├──────────┴──────────┴──────────┴──────────┴──────────────────┤
│  📊 This week: 4 tasks · ~24 effort points · avg 6/day       │
│  📋 Backlog: 3 queued tasks remaining                        │
└────────────────────────────────────────────────────────────────┘
```

Tasks can be dragged between days to reschedule. Effort points give a rough capacity indicator.

---

## 5. Updated Implementation Phases

The original phases are extended:

### Phase 1 — Foundation (MVP)
_No changes_

### Phase 1.5 — Heartbeat Scheduling
- [ ] Schema migration: `heartbeat_scheduled` status + fields
- [ ] "Add to Heartbeat" button on dashboard task cards
- [ ] Heartbeat scheduling dropdown component
- [ ] `/queue heartbeat` Discord command
- [ ] Heartbeat start-of-cycle auto-pull logic in Peterbot
- [ ] `v_heartbeat_plan` view

### Phase 2 — Intelligence
_As before, plus:_
- [ ] Drag-and-drop with `@dnd-kit` (status changes + reorder)
- [ ] Optimistic updates via React Query
- [ ] Status transition validation
- [ ] Heartbeat planner page (`/dashboard/tasks/heartbeat`)

### Phase 3 — Rich Features
_As before, plus:_
- [ ] Cross-list drag (idea → queue promotion)
- [ ] Effort point capacity planning on heartbeat planner
- [ ] Mobile responsive Kanban (single-column mode)
