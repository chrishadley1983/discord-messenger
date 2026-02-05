# Peter Dashboard Redesign Specification

## Overview

Complete redesign of the Peter Dashboard with a JunoMind-inspired UI featuring:
- Clean, modern aesthetic with teal accent color
- Collapsible sidebar navigation
- Real-time status monitoring via WebSocket
- Interactive data tables with filtering and search
- Detail panels for drill-down views

---

## 1. Navigation Structure

### Sidebar Sections

```
[Peter Dashboard Logo]

GENERAL
  Dashboard         <- Overview stats, quick health check
  Jobs              <- Schedule monitor (main view)
  Services          <- NSSM/tmux/process monitoring

WORKFLOWS
  Skills            <- 60+ skills browser with triggers
  Parser            <- Parser diagnostics and improvement

DATA
  Logs              <- Unified log viewer (bot, API, jobs)
  Files             <- Config editor (CLAUDE.md, SCHEDULE.md, etc.)
  Memory            <- Peterbot-mem and Second Brain

INTEGRATIONS
  API Explorer      <- 100+ Hadley API endpoints
  Hadley Bricks     <- HB-specific dashboard

SYSTEM
  Settings          <- Configuration and controls
```

### Route Mapping

| Route | View | Primary Data Source |
|-------|------|---------------------|
| `/` | Dashboard | `/api/status`, `/api/claude-code-health` |
| `/jobs` | Schedule Monitor | `/api/jobs`, `/api/job-stats` |
| `/services` | Service Status | `/api/service-status`, WebSocket |
| `/skills` | Skills Browser | `/api/skills`, manifest.json |
| `/parser` | Parser Diagnostics | `/api/parser/*` endpoints |
| `/logs` | Unified Logs | `/api/logs/unified` |
| `/files` | File Editor | `/api/files`, `/api/file/*` |
| `/memory` | Memory Viewer | `/api/memory/*`, `/api/search/*` |
| `/api-explorer` | API Docs | `/api/hadley/endpoints` |
| `/hb` | Hadley Bricks | Proxied from HB API |
| `/settings` | Settings | Local config |

---

## 2. Component Architecture

### Core Components

#### 2.1 Sidebar Component
```
Sidebar
├── SidebarHeader (logo, collapse button)
├── SidebarSection (section label)
│   └── SidebarItem (icon, label, badge, active state)
└── SidebarFooter (version, connection status)
```

**Props:**
- `collapsed: boolean` - Collapsed state (260px vs 60px)
- `activeRoute: string` - Current active route
- `sections: SidebarSection[]` - Section definitions

#### 2.2 Stats Card Component
```
StatsCard
├── CardIcon (emoji or SVG)
├── CardValue (large number)
├── CardLabel (description)
└── CardTrend (optional: up/down indicator)
```

**Variants:**
- `default` - Standard card
- `success` - Green accent
- `warning` - Yellow accent
- `error` - Red accent
- `info` - Teal accent

#### 2.3 Data Table Component
```
DataTable
├── TableHeader
│   ├── SearchBar
│   ├── FilterDropdown
│   └── ColumnToggles
├── TableBody
│   └── TableRow (selectable, clickable)
│       ├── Checkbox
│       ├── DataCells
│       └── StatusBadge
├── TableFooter
│   ├── Pagination
│   └── PageSize selector
└── EmptyState
```

**Features:**
- Column sorting (asc/desc)
- Multi-column filtering
- Row selection (single/multi)
- Pagination (10/25/50/100)
- Column visibility toggles
- Keyboard navigation
- Row click -> detail panel

#### 2.4 Status Badge Component
```
StatusBadge
├── StatusDot (colored circle)
└── StatusLabel (text)
```

**Status Types:**
| Status | Color | Use Case |
|--------|-------|----------|
| `running` | Green (#22c55e) | Active jobs, healthy services |
| `paused` | Yellow (#eab308) | Disabled jobs, maintenance |
| `error` | Red (#ef4444) | Failed jobs, down services |
| `idle` | Gray (#94a3b8) | Waiting, no activity |
| `pending` | Blue (#3b82f6) | Queued, waiting to run |

#### 2.5 Detail Panel Component
```
DetailPanel
├── PanelHeader
│   ├── Title
│   ├── SubTitle
│   └── CloseButton
├── PanelTabs
│   └── Tab (Overview, History, Config, etc.)
├── PanelContent
│   └── [Varies by view]
└── PanelFooter
    └── ActionButtons
```

**Width:** 380px (collapsible to 0)
**Animation:** Slide in from right

#### 2.6 Modal Component
```
Modal
├── Overlay (click to close)
├── ModalContainer
│   ├── ModalHeader (title, close button)
│   ├── ModalBody (scrollable)
│   └── ModalFooter (action buttons)
```

**Sizes:** `sm` (400px), `md` (600px), `lg` (800px), `xl` (1000px)

#### 2.7 Tab Component
```
TabGroup
├── TabList
│   └── Tab (icon, label, badge)
└── TabPanels
    └── TabPanel (content)
```

---

## 3. Color Scheme & Typography

### Primary Colors
```css
:root {
  /* Backgrounds */
  --bg-main: #f8fafc;           /* Main content area */
  --bg-sidebar: #1e293b;        /* Sidebar dark */
  --bg-card: #ffffff;           /* Card backgrounds */
  --bg-hover: #f1f5f9;          /* Hover states */
  --bg-selected: #e0f2fe;       /* Selected rows */

  /* Accent */
  --accent: #0d9488;            /* Teal primary */
  --accent-hover: #0f766e;      /* Teal dark */
  --accent-light: #ccfbf1;      /* Teal light bg */

  /* Text */
  --text-primary: #1e293b;      /* Primary text */
  --text-secondary: #64748b;    /* Secondary text */
  --text-muted: #94a3b8;        /* Muted text */
  --text-inverse: #ffffff;      /* Text on dark bg */

  /* Borders */
  --border: #e2e8f0;            /* Default border */
  --border-focus: #0d9488;      /* Focus ring */

  /* Status Colors */
  --status-running: #22c55e;    /* Success green */
  --status-running-bg: #dcfce7;
  --status-paused: #eab308;     /* Warning yellow */
  --status-paused-bg: #fef9c3;
  --status-error: #ef4444;      /* Error red */
  --status-error-bg: #fee2e2;
  --status-idle: #94a3b8;       /* Idle gray */
  --status-idle-bg: #f1f5f9;
  --status-pending: #3b82f6;    /* Pending blue */
  --status-pending-bg: #dbeafe;

  /* Shadows */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.1);
  --shadow-lg: 0 10px 15px rgba(0,0,0,0.1);
}
```

### Dark Mode (Optional)
```css
[data-theme="dark"] {
  --bg-main: #0f172a;
  --bg-sidebar: #020617;
  --bg-card: #1e293b;
  --bg-hover: #334155;
  --bg-selected: #1e3a5f;

  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;

  --border: #334155;
}
```

### Typography
```css
:root {
  /* Font Families */
  --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', monospace;

  /* Font Sizes */
  --text-xs: 0.75rem;      /* 12px - badges, labels */
  --text-sm: 0.875rem;     /* 14px - body small */
  --text-base: 1rem;       /* 16px - body */
  --text-lg: 1.125rem;     /* 18px - headings */
  --text-xl: 1.25rem;      /* 20px - section titles */
  --text-2xl: 1.5rem;      /* 24px - page titles */
  --text-3xl: 1.875rem;    /* 30px - stats numbers */
  --text-4xl: 2.25rem;     /* 36px - hero numbers */

  /* Font Weights */
  --font-normal: 400;
  --font-medium: 500;
  --font-semibold: 600;
  --font-bold: 700;

  /* Line Heights */
  --leading-tight: 1.25;
  --leading-normal: 1.5;
  --leading-relaxed: 1.75;
}
```

---

## 4. Layout Grid

### Desktop Layout (1400px+)
```
┌─────────────────────────────────────────────────────────────────────┐
│ Header (60px)                                                       │
├──────────┬────────────────────────────────────────────┬─────────────┤
│          │                                            │             │
│ Sidebar  │              Main Content                  │   Detail    │
│ (260px)  │              (flexible)                    │   Panel     │
│          │                                            │   (380px)   │
│          │                                            │             │
│          │                                            │             │
└──────────┴────────────────────────────────────────────┴─────────────┘
```

### Sidebar Collapsed (1200px - 1400px)
```
┌─────────────────────────────────────────────────────────────────────┐
│ Header (60px)                                                       │
├────┬──────────────────────────────────────────────────┬─────────────┤
│    │                                                  │             │
│ 60 │                  Main Content                    │   Detail    │
│ px │                  (flexible)                      │   Panel     │
│    │                                                  │   (380px)   │
│    │                                                  │             │
└────┴──────────────────────────────────────────────────┴─────────────┘
```

### Tablet (768px - 1200px)
```
┌─────────────────────────────────────────────────────────────────────┐
│ Header (60px) [hamburger menu]                                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│                         Main Content                                │
│                         (full width)                                │
│                                                                     │
│ [Sidebar as overlay when opened]                                    │
│ [Detail panel as modal/overlay]                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Mobile (< 768px)
```
┌─────────────────────────────────────────┐
│ Header (56px) [hamburger]               │
├─────────────────────────────────────────┤
│                                         │
│           Main Content                  │
│           (full width)                  │
│           (stacked cards)               │
│                                         │
└─────────────────────────────────────────┘
```

### Breakpoints
```css
--breakpoint-sm: 640px;   /* Mobile landscape */
--breakpoint-md: 768px;   /* Tablet portrait */
--breakpoint-lg: 1024px;  /* Tablet landscape */
--breakpoint-xl: 1280px;  /* Desktop */
--breakpoint-2xl: 1536px; /* Large desktop */
```

---

## 5. WebSocket Data Flow

### Connection Management
```javascript
class WebSocketManager {
  constructor() {
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000; // Start at 1s, exponential backoff
  }

  connect() {
    this.ws = new WebSocket(`ws://${location.host}/ws`);
    this.ws.onmessage = this.handleMessage.bind(this);
    this.ws.onclose = this.handleClose.bind(this);
  }
}
```

### Message Types (Server -> Client)

| Type | Payload | Frequency | Description |
|------|---------|-----------|-------------|
| `status` | ServiceStatus | 5s | Overall system status |
| `job_start` | JobEvent | On event | Job started executing |
| `job_complete` | JobEvent | On event | Job finished (success/fail) |
| `job_queued` | JobEvent | On event | Job added to queue |
| `log_entry` | LogEntry | Real-time | New log entries |
| `service_change` | ServiceEvent | On event | Service status changed |
| `memory_update` | MemoryEvent | On event | New memory observation |
| `error_alert` | AlertEvent | On event | Critical error occurred |

### Payload Schemas

```typescript
interface ServiceStatus {
  timestamp: string;
  services: {
    hadley_api: ServiceState;
    discord_bot: ServiceState;
    claude_mem: ServiceState;
    peterbot_session: ServiceState;
    hadley_bricks: ServiceState;
  };
  jobs: {
    active: number;
    queued: number;
    completed_24h: number;
    failed_24h: number;
  };
  memory: {
    total_observations: number;
    recent_count: number;
  };
}

interface ServiceState {
  status: 'up' | 'down' | 'degraded';
  latency_ms?: number;
  pid?: number;
  uptime_seconds?: number;
  last_error?: string;
}

interface JobEvent {
  job_id: string;
  job_name: string;
  skill: string;
  channel: string;
  status: 'started' | 'completed' | 'failed' | 'queued';
  duration_ms?: number;
  error?: string;
  output_preview?: string;
}

interface LogEntry {
  timestamp: string;
  level: 'debug' | 'info' | 'warning' | 'error';
  source: 'bot' | 'api' | 'scheduler' | 'parser';
  message: string;
  metadata?: Record<string, any>;
}
```

### Client -> Server Messages

| Type | Payload | Description |
|------|---------|-------------|
| `subscribe` | { topics: string[] } | Subscribe to specific topics |
| `unsubscribe` | { topics: string[] } | Unsubscribe from topics |
| `ping` | {} | Keep-alive ping |

---

## 6. API Endpoint Structure

### New Endpoints Required

#### Jobs API
```
GET  /api/jobs                    # List all jobs with status
GET  /api/jobs/{job_id}          # Get job details
GET  /api/jobs/{job_id}/history  # Get job run history
POST /api/jobs/{job_id}/run      # Trigger manual run
POST /api/jobs/{job_id}/enable   # Enable job
POST /api/jobs/{job_id}/disable  # Disable job
GET  /api/job-stats              # Aggregate job statistics
GET  /api/job-queue              # Current job queue
```

#### Unified Logs API
```
GET  /api/logs/unified           # Unified log stream
     ?source=bot,api,scheduler   # Filter by source
     ?level=info,error           # Filter by level
     ?since=2024-01-01T00:00:00  # Since timestamp
     ?limit=100                  # Max entries
     ?search=keyword             # Text search
GET  /api/logs/stats             # Log statistics
```

#### Enhanced Parser API
```
GET  /api/parser/health          # Parser system health
GET  /api/parser/quality-report  # Quality metrics
POST /api/parser/test            # Test parser with sample input
```

#### Enhanced Memory API
```
GET  /api/memory/stats           # Memory system statistics
GET  /api/memory/timeline        # Visual timeline of observations
POST /api/memory/search          # Advanced search with filters
```

### Existing Endpoints (Keep)

From current `app.py`:
```
GET  /                           # Dashboard HTML
GET  /health                     # Health check
GET  /api/status                 # System status
GET  /api/service-status         # Detailed service status
POST /api/stop/{service}         # Stop service
POST /api/restart/{service}      # Restart service
POST /api/restart-all            # Restart all services
GET  /api/files                  # List files
GET  /api/file/{type}/{name}     # Get file content
POST /api/file/append/{type}/{name}  # Append to file
PUT  /api/file/write/{type}/{name}   # Write file
GET  /api/context                # Current context.md
GET  /api/captures               # Recent captures
GET  /api/claude-code-health     # Claude Code health
GET  /api/logs/bot               # Bot logs
GET  /api/screen/{session}       # Tmux screen capture
POST /api/send/{session}         # Send to tmux
GET  /api/memory/peter           # Peter memories
GET  /api/memory/claude          # Claude memories
GET  /api/memory/recent          # Recent memories
GET  /api/hadley/endpoints       # Hadley API endpoints
GET  /api/heartbeat/status       # Heartbeat status
POST /api/heartbeat/ran          # Record heartbeat run
GET  /api/skills                 # List skills
GET  /api/skill/{name}           # Get skill content
GET  /api/peter/state            # Peter state info
GET  /api/peter/quote            # Random Peter quote
GET  /api/parser/debug           # Parser debug info
GET  /api/parser/status          # Parser status
GET  /api/parser/fixtures        # Parser fixtures
GET  /api/parser/captures        # Parser captures
GET  /api/parser/feedback        # Parser feedback
GET  /api/parser/cycles          # Improvement cycles
GET  /api/parser/drift           # Parser drift
POST /api/parser/run-regression  # Run regression tests
POST /api/parser/mark-reviewed   # Mark as reviewed
POST /api/parser/feedback/{id}/resolve  # Resolve feedback
GET  /api/search/memory          # Search memory
GET  /api/search/second-brain    # Search second brain
GET  /api/search/second-brain/stats  # Second brain stats
WS   /ws                         # WebSocket connection
```

### Response Schemas

#### Job List Response
```json
{
  "jobs": [
    {
      "id": "morning-briefing",
      "name": "Morning Briefing",
      "skill": "morning-briefing",
      "schedule": "07:00 UK",
      "channel": "#ai-briefings",
      "status": "running",
      "enabled": true,
      "last_run": "2024-02-05T07:00:02Z",
      "last_duration_ms": 45000,
      "last_success": true,
      "next_run": "2024-02-06T07:00:00Z",
      "run_count_24h": 1,
      "success_rate_24h": 100
    }
  ],
  "total": 25,
  "running": 1,
  "queued": 0
}
```

#### Job Stats Response
```json
{
  "total_jobs": 25,
  "enabled_jobs": 23,
  "jobs_24h": {
    "total": 45,
    "successful": 43,
    "failed": 2,
    "success_rate": 95.6
  },
  "avg_duration_ms": 32000,
  "by_status": {
    "running": 1,
    "idle": 22,
    "paused": 2
  },
  "by_channel": {
    "#ai-briefings": 5,
    "#food-log": 8,
    "#peterbot": 10
  }
}
```

---

## 7. File Structure

```
peter_dashboard/
├── app.py                      # FastAPI backend (main app)
├── requirements.txt            # Python dependencies
├── README.md                   # Documentation
│
├── api/                        # API route modules
│   ├── __init__.py
│   ├── jobs.py                 # Job management endpoints
│   ├── logs.py                 # Log aggregation endpoints
│   ├── parser.py               # Parser endpoints (extracted)
│   ├── memory.py               # Memory endpoints (extracted)
│   └── services.py             # Service management endpoints
│
├── core/                       # Core utilities
│   ├── __init__.py
│   ├── config.py               # Configuration management
│   ├── websocket.py            # WebSocket manager
│   └── service_manager.py      # Process management (existing)
│
├── static/
│   ├── css/
│   │   ├── main.css            # Base styles, variables, reset
│   │   ├── components.css      # Component-specific styles
│   │   └── utilities.css       # Utility classes
│   │
│   ├── js/
│   │   ├── app.js              # Main application logic
│   │   ├── components/
│   │   │   ├── sidebar.js      # Sidebar component
│   │   │   ├── stats-card.js   # Stats card component
│   │   │   ├── data-table.js   # Data table component
│   │   │   ├── status-badge.js # Status badge component
│   │   │   ├── detail-panel.js # Detail panel component
│   │   │   ├── modal.js        # Modal component
│   │   │   └── tabs.js         # Tab component
│   │   │
│   │   ├── views/
│   │   │   ├── dashboard.js    # Dashboard view
│   │   │   ├── jobs.js         # Jobs view
│   │   │   ├── services.js     # Services view
│   │   │   ├── skills.js       # Skills view
│   │   │   ├── parser.js       # Parser view
│   │   │   ├── logs.js         # Logs view
│   │   │   ├── files.js        # Files view
│   │   │   ├── memory.js       # Memory view
│   │   │   └── api-explorer.js # API explorer view
│   │   │
│   │   ├── services/
│   │   │   ├── api.js          # API client
│   │   │   ├── websocket.js    # WebSocket client
│   │   │   └── state.js        # State management
│   │   │
│   │   └── utils/
│   │       ├── dom.js          # DOM utilities
│   │       ├── format.js       # Formatting utilities
│   │       └── storage.js      # LocalStorage utilities
│   │
│   └── assets/
│       ├── logo.svg            # Peter logo
│       └── icons/              # SVG icons
│
└── templates/
    └── index.html              # Main SPA template
```

---

## 8. View Specifications

### 8.1 Dashboard View

**Purpose:** Quick system health overview

**Layout:**
```
┌─────────────────────────────────────────────────────────────────┐
│ Stats Cards (4 columns)                                         │
│ ┌──────────┬──────────┬──────────┬──────────┐                  │
│ │ Active   │ Success  │ Errors   │ Uptime   │                  │
│ │ Jobs: 1  │ Rate: 95%│ Today: 2 │ 99.9%    │                  │
│ └──────────┴──────────┴──────────┴──────────┘                  │
├─────────────────────────────────────────────────────────────────┤
│ Services Status (compact cards)                                 │
│ ┌───────────────┬───────────────┬───────────────┐              │
│ │ Hadley API    │ Discord Bot   │ Claude Mem    │              │
│ │ ● Running     │ ● Running     │ ● Running     │              │
│ │ 45ms         │ PID: 1234     │ 12ms          │              │
│ └───────────────┴───────────────┴───────────────┘              │
├─────────────────────────────────────────────────────────────────┤
│ Recent Activity (last 10 job runs)                              │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Time     Job              Status   Duration               │  │
│ │ 07:00    Morning Briefing ● Done   45s                    │  │
│ │ 07:02    Morning News     ● Done   12s                    │  │
│ │ 07:55    Health Digest    ● Done   8s                     │  │
│ └───────────────────────────────────────────────────────────┘  │
├───────────────────────────────────┬─────────────────────────────┤
│ Upcoming Jobs (next 5)            │ Recent Errors              │
│ ┌─────────────────────────────┐  │ ┌─────────────────────────┐│
│ │ 09:02 Hydration Check      │  │ │ 06:45 Parser: timeout   ││
│ │ 09:05 YouTube Digest       │  │ │ Yesterday: API 503      ││
│ │ 09:35 HB Full Sync         │  │ └─────────────────────────┘│
│ └─────────────────────────────┘  │                            │
└───────────────────────────────────┴─────────────────────────────┘
```

### 8.2 Jobs View (Main View)

**Purpose:** Monitor and manage scheduled jobs

**Table Columns:**
| Column | Width | Sortable | Description |
|--------|-------|----------|-------------|
| (checkbox) | 40px | No | Row selection |
| Status | 100px | Yes | Status badge |
| Name | 200px | Yes | Job name (clickable) |
| Skill | 150px | Yes | Associated skill |
| Schedule | 150px | Yes | Cron expression |
| Channel | 120px | Yes | Target channel |
| Last Run | 150px | Yes | Timestamp |
| Duration | 80px | Yes | Last run duration |
| Success Rate | 100px | Yes | 24h success % |
| Actions | 80px | No | Enable/disable, run now |

**Filters:**
- Status: All, Running, Idle, Paused, Error
- Channel: All, #peterbot, #food-log, etc.
- Search: Text search on name/skill

**Detail Panel (on row click):**
```
┌─────────────────────────────────┐
│ Morning Briefing                │
│ AI and Claude news briefing     │
├─────────────────────────────────┤
│ [Overview] [History] [Config]   │
├─────────────────────────────────┤
│ Status: ● Running               │
│ Last Run: 2 hours ago           │
│ Next Run: Tomorrow 07:00        │
│ Success Rate: 100%              │
│                                 │
│ Schedule: 07:00 UK daily        │
│ Channel: #ai-briefings          │
│ Skill: morning-briefing         │
│                                 │
│ Recent Runs:                    │
│ ┌────────────────────────────┐  │
│ │ Today 07:00 ● 45s         │  │
│ │ Yesterday 07:00 ● 42s     │  │
│ │ 2 days ago 07:00 ● 48s    │  │
│ └────────────────────────────┘  │
├─────────────────────────────────┤
│ [Run Now] [Disable] [View Logs] │
└─────────────────────────────────┘
```

### 8.3 Services View

**Purpose:** Monitor and control system services

**Layout:**
```
┌─────────────────────────────────────────────────────────────────┐
│ Service Cards (grid)                                            │
│ ┌───────────────────────┬───────────────────────┐              │
│ │ Hadley API           │ Discord Bot            │              │
│ │ ━━━━━━━━━━━━━━━━━━   │ ━━━━━━━━━━━━━━━━━━    │              │
│ │ ● Running            │ ● Running              │              │
│ │ Port: 8100          │ PID: 12345             │              │
│ │ Latency: 45ms       │ Uptime: 3d 4h          │              │
│ │ Managed: NSSM       │ Managed: NSSM          │              │
│ │ [Restart] [Stop]    │ [Restart] [Stop]       │              │
│ └───────────────────────┴───────────────────────┘              │
│ ┌───────────────────────┬───────────────────────┐              │
│ │ Claude Memory        │ Peterbot Session       │              │
│ │ ━━━━━━━━━━━━━━━━━━   │ ━━━━━━━━━━━━━━━━━━    │              │
│ │ ● Running            │ ● Running              │              │
│ │ Port: 37777         │ Session: claude-peterbot│              │
│ │ Latency: 12ms       │ Attached: No           │              │
│ │ Managed: Systemd    │ Managed: tmux          │              │
│ │ [Restart]           │ [Restart] [Attach]     │              │
│ └───────────────────────┴───────────────────────┘              │
│ ┌───────────────────────┐                                      │
│ │ Hadley Bricks         │                                      │
│ │ ━━━━━━━━━━━━━━━━━━   │                                      │
│ │ ● Running            │                                      │
│ │ Port: 3000          │                                      │
│ │ Latency: 89ms       │                                      │
│ │ [Restart] [Stop]    │                                      │
│ └───────────────────────┘                                      │
└─────────────────────────────────────────────────────────────────┘
```

### 8.4 Skills View

**Purpose:** Browse and inspect skills

**Layout:**
```
┌───────────────────────────────────────────────────────────────────┐
│ Skills Browser                                      [Search...] │
├───────────────────────────────────────────────────────────────────┤
│ Filters: [All] [Scheduled] [Conversational] [Hadley Bricks]      │
├───────────────────────────────────────────────────────────────────┤
│ Skills Grid (cards)                                               │
│ ┌────────────────┬────────────────┬────────────────┐             │
│ │ morning-       │ health-digest  │ school-run     │             │
│ │ briefing       │                │                │             │
│ │ ────────────── │ ────────────── │ ──────────────│             │
│ │ AI news brief  │ Morning health │ Traffic report │             │
│ │                │ summary        │ for school     │             │
│ │ ⏰ Scheduled   │ ⏰ Scheduled   │ ⏰ Scheduled   │             │
│ │ 💬 Triggers   │ 💬 Triggers   │ 💬 Triggers   │             │
│ └────────────────┴────────────────┴────────────────┘             │
│ ┌────────────────┬────────────────┬────────────────┐             │
│ │ hb-dashboard   │ hb-pnl         │ hb-orders      │             │
│ │ ...            │ ...            │ ...            │             │
│ └────────────────┴────────────────┴────────────────┘             │
└───────────────────────────────────────────────────────────────────┘
```

**Detail Panel (on card click):**
- Full SKILL.md content rendered as markdown
- Trigger keywords
- Schedule information
- Associated channel
- "Test Skill" button (for conversational skills)

### 8.5 Logs View

**Purpose:** Unified log viewer across all sources

**Layout:**
```
┌───────────────────────────────────────────────────────────────────┐
│ Unified Logs                                                      │
├───────────────────────────────────────────────────────────────────┤
│ Filters:                                                          │
│ Source: [All] [Bot] [API] [Scheduler] [Parser]                   │
│ Level:  [All] [Debug] [Info] [Warning] [Error]                   │
│ Time:   [Last Hour] [Last 24h] [Custom]    [Search...]           │
├───────────────────────────────────────────────────────────────────┤
│ Log Entries (virtual scroll)                                      │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ 07:00:02 [INFO] [Scheduler] Starting job: morning-briefing   │ │
│ │ 07:00:02 [DEBUG] [Bot] Sending context to Claude Code        │ │
│ │ 07:00:45 [INFO] [Scheduler] Job completed: morning-briefing  │ │
│ │ 07:00:45 [INFO] [Bot] Response received (1234 chars)         │ │
│ │ 07:02:00 [INFO] [Scheduler] Starting job: news               │ │
│ │ 07:02:00 [ERROR] [API] Request timeout: /weather/current     │ │
│ │ ...                                                          │ │
│ └──────────────────────────────────────────────────────────────┘ │
├───────────────────────────────────────────────────────────────────┤
│ Showing 150 of 2,345 entries          [Load More] [Export CSV]   │
└───────────────────────────────────────────────────────────────────┘
```

### 8.6 Parser View

**Purpose:** Parser diagnostics and improvement monitoring

**Layout:**
```
┌───────────────────────────────────────────────────────────────────┐
│ Parser Diagnostics                                                │
├───────────────────────────────────────────────────────────────────┤
│ Stats Cards                                                       │
│ ┌──────────┬──────────┬──────────┬──────────┐                    │
│ │ Fixtures │ Captures │ Feedback │ Quality  │                    │
│ │ 45       │ 1,234    │ 12 open  │ 94.5%    │                    │
│ └──────────┴──────────┴──────────┴──────────┘                    │
├───────────────────────────────────────────────────────────────────┤
│ Tabs: [Fixtures] [Captures] [Feedback] [Cycles]                   │
├───────────────────────────────────────────────────────────────────┤
│ Fixtures Table                                                    │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ Pattern              Category      Examples  Last Updated    │ │
│ │ morning_briefing     scheduled     12        2 days ago      │ │
│ │ health_report        scheduled     8         1 day ago       │ │
│ │ food_log             conversational 45       Today           │ │
│ └──────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘
```

### 8.7 Files View

**Purpose:** View and edit configuration files

**Layout:**
```
┌────────────────────────┬──────────────────────────────────────────┐
│ Files                  │ CLAUDE.md                                │
│                        │ ────────────────────────────────────────│
│ Windows Files          │ # Claude-Mem: AI Development...         │
│ ├─ CLAUDE.md      ●   │                                          │
│ ├─ PETERBOT_SOUL.md   │ Claude-mem is a Claude Code plugin...   │
│ ├─ SCHEDULE.md        │                                          │
│ ├─ HEARTBEAT.md       │ ## Architecture                          │
│ └─ config.py          │                                          │
│                        │ **5 Lifecycle Hooks**:                   │
│ WSL Files              │ - SessionStart                           │
│ ├─ context.md         │ - UserPromptSubmit                       │
│ ├─ raw_capture.log    │ ...                                      │
│ └─ HEARTBEAT.md       │                                          │
│                        ├──────────────────────────────────────────│
│                        │ [Save] [Revert] [Format]    Line 1, Col 1│
└────────────────────────┴──────────────────────────────────────────┘
```

### 8.8 Memory View

**Purpose:** Browse and search memory systems

**Layout:**
```
┌───────────────────────────────────────────────────────────────────┐
│ Memory Systems                                                    │
├───────────────────────────────────────────────────────────────────┤
│ Tabs: [Peterbot Memory] [Second Brain]                           │
├───────────────────────────────────────────────────────────────────┤
│ Search: [                                    ] [Search]          │
├───────────────────────────────────────────────────────────────────┤
│ Recent Observations                                               │
│ ┌──────────────────────────────────────────────────────────────┐ │
│ │ #548 | 3:26 PM | Chris prefers morning runs before 7am      │ │
│ │ #547 | 2:15 PM | Decided to use teal as accent color        │ │
│ │ #546 | 1:30 PM | Working on dashboard redesign              │ │
│ │ #545 | 12:00 PM | Lunch: salad with grilled chicken         │ │
│ └──────────────────────────────────────────────────────────────┘ │
├───────────────────────────────────────────────────────────────────┤
│ Stats: 548 total | 23 today | 156 this week                     │
└───────────────────────────────────────────────────────────────────┘
```

### 8.9 API Explorer View

**Purpose:** Browse and test Hadley API endpoints

**Layout:**
```
┌────────────────────────┬──────────────────────────────────────────┐
│ Endpoints              │ GET /gmail/unread                        │
│ [Search...]            │ ────────────────────────────────────────│
│                        │ Get unread emails                        │
│ Gmail                  │                                          │
│ ├─ GET /gmail/unread  │ Parameters:                              │
│ ├─ GET /gmail/search  │ ┌────────────────────────────────────┐   │
│ ├─ POST /gmail/send   │ │ limit: 10                          │   │
│ └─ ...                │ │ labels: INBOX                       │   │
│                        │ └────────────────────────────────────┘   │
│ Calendar               │                                          │
│ ├─ GET /calendar/today│ [Try It]                                 │
│ ├─ POST /calendar/...  │                                          │
│ └─ ...                │ Response:                                │
│                        │ ┌────────────────────────────────────┐   │
│ Drive                  │ │ {                                  │   │
│ ├─ GET /drive/search  │ │   "emails": [...]                  │   │
│ └─ ...                │ │ }                                   │   │
│                        │ └────────────────────────────────────┘   │
└────────────────────────┴──────────────────────────────────────────┘
```

---

## 9. Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
- [ ] Set up new file structure
- [ ] Implement CSS design system (variables, base styles)
- [ ] Build core components (Sidebar, StatsCard, StatusBadge)
- [ ] Implement SPA routing
- [ ] Migrate existing endpoints to modular structure

### Phase 2: Main Views (Week 2)
- [ ] Build Dashboard view
- [ ] Build Jobs view with DataTable
- [ ] Build Services view
- [ ] Implement WebSocket integration
- [ ] Add new job analytics endpoints

### Phase 3: Secondary Views (Week 3)
- [ ] Build Skills browser
- [ ] Build Logs view with virtual scroll
- [ ] Build Files editor
- [ ] Build Memory viewer

### Phase 4: Advanced Features (Week 4)
- [ ] Build Parser diagnostics view
- [ ] Build API Explorer
- [ ] Implement detail panels
- [ ] Add keyboard shortcuts
- [ ] Performance optimization

### Phase 5: Polish (Week 5)
- [ ] Responsive design testing
- [ ] Dark mode (optional)
- [ ] Error handling and loading states
- [ ] Documentation
- [ ] User testing and fixes

---

## 10. Technical Decisions

### Frontend Framework
**Decision:** Vanilla JavaScript with custom component system

**Rationale:**
- No build step required
- Fast iteration
- Small bundle size
- Suitable for internal tool
- Easy to maintain

### State Management
**Decision:** Simple reactive state object with event dispatch

```javascript
const state = {
  services: {},
  jobs: [],
  selectedJob: null,
  // ...
};

function setState(updates) {
  Object.assign(state, updates);
  document.dispatchEvent(new CustomEvent('stateChange', { detail: updates }));
}
```

### CSS Strategy
**Decision:** CSS custom properties + utility classes

- CSS variables for theming
- BEM-like naming for components
- Tailwind-inspired utilities for common patterns

### API Client
**Decision:** Fetch API with retry and timeout

```javascript
async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    timeout: 10000,
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  if (!response.ok) throw new ApiError(response);
  return response.json();
}
```

---

## 11. Accessibility

### Requirements
- Keyboard navigation for all interactive elements
- ARIA labels for icons and badges
- Focus visible indicators
- Color contrast ratio >= 4.5:1
- Screen reader announcements for status changes

### Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `g d` | Go to Dashboard |
| `g j` | Go to Jobs |
| `g s` | Go to Services |
| `g l` | Go to Logs |
| `/` | Focus search |
| `Esc` | Close panel/modal |
| `r` | Refresh current view |
| `?` | Show help |

---

## 12. Performance Considerations

### Virtual Scrolling
- Logs view: virtualize for 1000+ entries
- Jobs view: OK up to 100 rows without virtualization

### Lazy Loading
- Load views on demand
- Defer non-critical API calls
- Lazy load skill content

### Caching
- Cache API responses with short TTL (30s)
- LocalStorage for user preferences
- Service worker for static assets (optional)

### WebSocket Optimization
- Debounce frequent updates
- Only send changed data
- Implement reconnection with backoff

---

## Appendix A: Current System Inventory

### Scheduled Jobs (25 jobs from SCHEDULE.md)
1. Parser Improvement (02:00)
2. Morning Quality Report (06:45)
3. Morning Briefing (07:00)
4. Morning News (07:02)
5. Morning Health Digest (07:55)
6. School Run (Mon-Wed,Fri 08:10 / Thu 07:45)
7. YouTube Digest (09:05)
8. Hydration Check-in (7x daily)
9. School Pickup (Mon,Tue,Thu,Fri 14:55 / Wed 16:50)
10. Daily Nutrition Summary (21:00)
11. Weekly Health Summary (Sun 09:10)
12. Monthly Health Summary (1st 09:15)
13. WhatsApp Keepalive (06:00, 22:00)
14. Self-Reflect (12:00, 18:00, 23:00)
15. Email Summary (08:02)
16. Schedule Today (08:04)
17. Schedule Week (Sun 18:00)
18. Notion Todos (08:06)
19. Balance Monitor (hourly+3)
20. Heartbeat (half-hourly+1)
21. Email Purchase Import (02:17)
22. HB Full Sync + Print (09:35)

### Skills (60+ from manifest.json)
Categorized by domain:
- **Health/Nutrition**: health-digest, hydration, nutrition-summary, weekly-health, monthly-health, daily-recipes
- **Scheduling**: morning-briefing, school-run, school-pickup, schedule-today, schedule-week
- **Hadley Bricks**: hb-* (20+ skills)
- **Information**: news, youtube-digest, football-scores, weather, weather-forecast
- **Productivity**: email-summary, email-search, notion-todos, notion-ideas, find-free-time, remind
- **System**: heartbeat, self-reflect, parser-improve, balance-monitor, whatsapp-keepalive

### API Endpoints (100+ from hadley_api/README.md)
- Gmail (17 endpoints)
- Calendar (15 endpoints)
- Drive (12 endpoints)
- Sheets (8 endpoints)
- Docs (6 endpoints)
- Tasks (7 endpoints)
- Contacts (6 endpoints)
- Peterbot Tasks (17 endpoints)
- Notion (10 endpoints)
- Reminders (4 endpoints)
- Weather (2 endpoints)
- Traffic/Directions (3 endpoints)
- Places (4 endpoints)
- EV/Home (4 endpoints)
- Utilities (12 endpoints)
- Nutrition (5 endpoints)
- Hadley Bricks (6 endpoints)
- WhatsApp (2 endpoints)
- Browser Automation (8 endpoints)

### Services (5 monitored)
1. Hadley API (port 8100, NSSM-managed)
2. Discord Bot (NSSM-managed)
3. Claude Memory Worker (port 37777)
4. Peterbot Session (tmux)
5. Hadley Bricks (port 3000)

---

## Appendix B: Migration Path

### From Current to New

1. **Keep backend app.py** as base, refactor to modular structure
2. **Replace DASHBOARD_HTML** with external template
3. **Add new endpoints** incrementally
4. **Static files** in separate directory (not inline)
5. **Parallel deployment** - run on different port during development

### Backwards Compatibility
- Keep existing API endpoints
- WebSocket protocol unchanged
- Service manager unchanged

---

*Document Version: 1.0*
*Created: 2026-02-05*
*Author: Claude Code*
