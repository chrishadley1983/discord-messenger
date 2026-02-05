# Task Dashboard Implementation Summary

## Overview

A full-featured task management system integrated into the Peter Dashboard, providing Kanban-style task organization with four distinct task lists, drag-and-drop functionality, and comprehensive CRUD operations.

---

## Functional Summary

### Task Lists (4 Types)

| List | Icon | Purpose | Statuses |
|------|------|---------|----------|
| **Personal Todo** | 📋 | Chris's personal tasks | inbox → scheduled → in_progress → done |
| **Peter Queue** | 🤖 | Peter's automated work queue | queued → heartbeat_scheduled → in_heartbeat → in_progress → review → done |
| **Ideas** | 💡 | Ideas dump for later review | inbox → scheduled → review → done |
| **Research** | 🔬 | Research items requiring investigation | queued → in_progress → findings_ready → done |

### Core Features

#### 1. Kanban Board View
- Column-based layout showing tasks grouped by status
- Color-coded columns with status indicators
- Task counts per column
- Tab counts showing active tasks per list type

#### 2. Task Cards Display
- Priority indicator (Critical/High/Medium/Low/Someday) with color coding
- Category tags with custom colors
- Scheduled date (🗓️) and Due date (⏰) indicators
- Effort estimate badges
- Heartbeat schedule indicator (⚡)
- Comment and attachment counts
- "by Peter" badge for Peter-created tasks

#### 3. Task Operations

**Create Task:**
- Quick-add modal with title input
- List type selector
- Priority selector

**Edit Task (click to open):**
- Title and description fields
- Status dropdown (valid transitions only)
- Priority dropdown
- Scheduled date picker
- Due date picker
- Effort estimate selector
- Delete button

**Drag and Drop:**
- Drag tasks between status columns
- Visual feedback during drag (column highlight)
- Automatic status update on drop
- Validates allowed status transitions

**Mark Done:**
- Quick "✓ Done" button on each task card

#### 4. Heartbeat Scheduling (Peter Queue)
- "⚡ Add to Heartbeat" button on queued tasks
- Date picker dropdown for scheduling
- Shows upcoming 10 days with existing task counts
- "Add to Current Heartbeat" for immediate work

#### 5. Category/Tag Management
- "⚙️ Tags" button opens configuration modal
- View all categories with color swatches
- Create new tags with custom name and color
- Edit tag names inline
- Click color swatch to change color
- Delete tags (removes from all tasks)

#### 6. Search
- Real-time search filtering across task titles

---

## Technical Summary

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Peter Dashboard                           │
│                   (localhost:5000)                           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Tasks View (JavaScript)                 │    │
│  │  - renderTasks()     - showEditTaskModal()          │    │
│  │  - loadTasks()       - showCategoryConfig()         │    │
│  │  - onTaskDrop()      - createTask/saveTask()        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP (CORS enabled)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Hadley API                                │
│                  (localhost:8100)                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │           task_routes.py (FastAPI Router)            │    │
│  │  Prefix: /ptasks                                     │    │
│  │  Routes: 19 endpoints                                │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────┬───────────────────────────────────────┘
                      │ REST API
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                     Supabase                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                 PostgreSQL Tables                    │    │
│  │  - tasks              - task_categories              │    │
│  │  - task_category_links - task_comments              │    │
│  │  - task_attachments   - task_reminders              │    │
│  │  - task_history                                      │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Database Schema

#### Enums
```sql
task_list_type: personal_todo, peter_queue, idea, research
task_status: inbox, scheduled, in_progress, done, cancelled, queued,
             heartbeat_scheduled, in_heartbeat, review, findings_ready
task_priority: critical, high, medium, low, someday
research_depth: quick, standard, deep
idea_source: manual, conversation, email, web
```

#### Core Tables

**tasks**
- `id` (UUID, PK)
- `list_type` (task_list_type)
- `status` (task_status)
- `priority` (task_priority)
- `title`, `description`
- `due_date`, `scheduled_date`
- `estimated_effort` (trivial, 30min, 2hr, half_day, multi_day)
- `heartbeat_scheduled_for`, `heartbeat_slot_order`
- `created_by`, `assigned_to`
- `sort_order`, `is_pinned`
- Timestamps and Discord reference fields

**task_categories**
- `id` (UUID, PK)
- `name`, `slug` (unique)
- `color` (hex), `icon`
- `sort_order`

**task_category_links** (junction table)
- `task_id` → tasks
- `category_id` → task_categories

**task_comments**
- `id`, `task_id`, `author`, `content`
- `is_system_message` (for automated comments)

### API Endpoints (19 total)

#### Tasks CRUD
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/ptasks` | List tasks with filters |
| GET | `/ptasks/list/{list_type}` | Get tasks by list |
| GET | `/ptasks/{task_id}` | Get single task |
| GET | `/ptasks/counts` | Get counts per list type |
| POST | `/ptasks` | Create task |
| PUT | `/ptasks/{task_id}` | Update task |
| DELETE | `/ptasks/{task_id}` | Delete task |

#### Task Operations
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ptasks/{task_id}/status` | Change status (validated) |
| POST | `/ptasks/{task_id}/heartbeat` | Schedule for heartbeat |
| GET | `/ptasks/heartbeat/plan` | Get heartbeat schedule |
| POST | `/ptasks/{task_id}/reorder` | Reorder single task |
| POST | `/ptasks/bulk/reorder` | Bulk reorder |

#### Comments
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/ptasks/{task_id}/comments` | List comments |
| POST | `/ptasks/{task_id}/comments` | Add comment |

#### Categories
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/ptasks/categories` | List all categories |
| POST | `/ptasks/categories` | Create category |
| PUT | `/ptasks/categories/{id}` | Update category |
| DELETE | `/ptasks/categories/{id}` | Delete category |
| PUT | `/ptasks/{task_id}/categories` | Set task categories |

### Status Transition Rules

The API enforces valid status transitions per list type:

```javascript
// personal_todo
inbox → scheduled, in_progress, done, cancelled
scheduled → inbox, in_progress, done
in_progress → done, scheduled
done → inbox, scheduled, in_progress  // Can reopen

// peter_queue
queued → heartbeat_scheduled, in_heartbeat, cancelled
heartbeat_scheduled → queued, in_heartbeat, cancelled
in_heartbeat → in_progress, queued
in_progress → review, in_heartbeat
review → done, in_progress
done → queued  // Can requeue

// idea
inbox → scheduled, review, done
scheduled → inbox, review
review → done, scheduled
done → inbox, scheduled  // Can reopen

// research
queued → in_progress, cancelled
in_progress → findings_ready, queued
findings_ready → done, in_progress
done → queued  // Can requeue
```

### Frontend Implementation

#### Key JavaScript Functions

```javascript
// Data loading
loadTasks()           // Fetches tasks, categories, counts from API

// Rendering
renderTasks()         // Main render function for Kanban board
renderTaskCard(task)  // Renders individual task card HTML

// Task operations
showTaskModal()       // New task modal
showEditTaskModal(id) // Edit task modal
createTask()          // POST new task
saveTask()            // PUT update task
deleteTask(id)        // DELETE task
markTaskDone(id)      // Quick done action

// Drag and drop
onTaskDragStart(event, id)
onTaskDragEnd(event)
onTaskDragOver(event, colId)
onTaskDrop(event, colId)  // Calls status change API

// Heartbeat
toggleTaskHeartbeat(id)
scheduleTaskHeartbeat(id, date)
renderHeartbeatDropdown(id)

// Category management
showCategoryConfig()
createCat()
updateCatName(id, name)
pickCatColor(id)
deleteCat(id)
```

#### State Variables
```javascript
let taskActiveList = 'peter_queue';  // Current list tab
let taskData = { tasks: [], categories: [], counts: {} };
let taskSearchQuery = '';
let taskDraggedId = null;
let taskHeartbeatTarget = null;
let editingTaskId = null;
let editTaskData = null;
```

### CORS Configuration

The Hadley API includes CORS middleware to allow cross-origin requests from the dashboard:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5000",   # Peter Dashboard
        "http://127.0.0.1:5000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Files Modified/Created

| File | Changes |
|------|---------|
| `hadley_api/task_routes.py` | NEW - 19 API endpoints (~900 lines) |
| `hadley_api/main.py` | Added task_routes import, CORS middleware |
| `peter_dashboard/app.py` | Added Tasks view, ~600 lines of CSS/JS |
| `hadley_api/README.md` | Documented all ptasks endpoints |

### Supabase Migrations Applied

1. `create_tasks_schema` - Tables, enums, indexes, triggers
2. `create_tasks_views` - Views for common queries, RLS policies

---

## Usage

### Starting Services

```bash
# Terminal 1: Hadley API
python -m uvicorn hadley_api.main:app --port 8100 --reload

# Terminal 2: Peter Dashboard
python -m uvicorn peter_dashboard.app:app --port 5000 --reload
```

### Accessing

- **Dashboard:** http://localhost:5000 → Click "Tasks" in sidebar
- **API Docs:** http://localhost:8100/docs → Search "ptasks"

### Quick Actions

1. **Add Task:** Click "+ Add Task" button
2. **Edit Task:** Click any task card
3. **Change Status:** Drag task to different column
4. **Mark Done:** Click "✓ Done" button on card
5. **Manage Tags:** Click "⚙️ Tags" button
6. **Search:** Type in search box
7. **Switch Lists:** Click tabs (My Todos, Peter Queue, Ideas, Research)
