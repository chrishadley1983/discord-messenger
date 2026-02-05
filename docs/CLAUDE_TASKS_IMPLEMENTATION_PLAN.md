# Claude Code Tasks Implementation Plan

## Overview

This document outlines how to implement Claude Code Tasks (v2.1.16+) as the default task management system across all projects, replacing the existing TodoWrite-based approach and integrating with your current agent ecosystem.

---

## Current State Analysis

### What You Have Now

| Component | Current Approach | Pain Points |
|-----------|-----------------|-------------|
| Task Planning | `task_plan.md` files | Manual, session-ephemeral |
| Progress Tracking | TodoWrite tool | Flat list, no dependencies, lost on context switch |
| Feature Workflow | `/define-done` → `/build-feature` → `/verify-done` | Manual state passing between agents |
| Agent Coordination | Markdown files + slash commands | No shared state across sessions |
| Specs | `docs/features/<feature>/done-criteria.md` | Good but disconnected from task execution |

### What Tasks Provide

| Capability | Benefit |
|------------|---------|
| DAG dependencies | Task 3 can't start until Tasks 1 & 2 complete |
| Filesystem persistence | `~/.claude/tasks/` survives sessions |
| Shared state via `CLAUDE_CODE_TASK_LIST_ID` | Multiple sessions coordinate |
| Status tracking | pending → in_progress → completed |
| Anti-hallucination | Claude can't claim completion without evidence |

---

## Implementation Plan

### Phase 1: Global CLAUDE.md Updates

Update `C:\Users\Chris Hadley\.claude\CLAUDE.md` with task management defaults:

```markdown
# Global Claude Code Instructions

## Task Management (Required)

### Default Behaviour
- Use TaskCreate for any task with 3+ steps
- Use TaskUpdate to track progress in real-time
- Set dependencies via `addBlockedBy` parameter
- Mark tasks complete IMMEDIATELY upon finishing

### When to Use Tasks vs. TodoWrite
| Scenario | Tool |
|----------|------|
| 3+ step implementation | TaskCreate |
| Multi-file changes | TaskCreate |
| Dependency chains | TaskCreate |
| Simple single-step fix | Skip (just do it) |
| Quick research | Skip |

### Task Creation Pattern
```
/user: implement <feature>
/claude: Break into tasks → TaskCreate with dependencies → Execute sequentially
```

### Shared Task Lists (Multi-Session)
For concurrent work, set environment variable:
```powershell
$env:CLAUDE_CODE_TASK_LIST_ID = "project-feature-name"
```

### Hydration Pattern (Spec → Tasks)
When working from a spec file, hydrate tasks at session start:
1. Read the spec (e.g., `docs/features/<feature>/done-criteria.md`)
2. TaskCreate for each criterion
3. Set dependencies based on implementation order
4. Reference spec file in task descriptions

## Notes
- Prisma imports should use named import: `import { prisma } from '@/lib/prisma'`
- All dynamic API routes should use Next.js 15 async params pattern: `{ params }: { params: Promise<{ id: string }> }`
```

### Phase 2: Project CLAUDE.md Integration

Add to each project's `CLAUDE.md` (Discord-Messenger, Hadley-Bricks):

```markdown
## Task Management

### Task-First Development
Before writing code, break the work into tasks using TaskCreate:
1. Read the governing spec (done-criteria.md, feature-spec.md)
2. Create tasks for each implementation step
3. Set dependencies with `addBlockedBy`
4. Execute tasks in order, updating status

### Integration with Agents

| Agent | Task Integration |
|-------|-----------------|
| `/define-done` | Outputs criteria → these become task templates |
| `/build-feature` | Creates tasks from done-criteria.md, executes autonomously |
| `/verify-done` | Each criterion becomes a verification task |
| `/test-plan` | Each test gap becomes a task |

### Shared Task Lists for Complex Features
For multi-session coordination:
```powershell
# Terminal 1: Feature implementation
$env:CLAUDE_CODE_TASK_LIST_ID = "inventory-export"

# Terminal 2: Tests (shares same task list)
$env:CLAUDE_CODE_TASK_LIST_ID = "inventory-export"
```

### Task Naming Convention
| Pattern | Example |
|---------|---------|
| Feature criterion | `F1: Add export button to /inventory page` |
| Test task | `test: Unit tests for export service` |
| Docs task | `docs: Update API.md with export endpoint` |
| Infra task | `infra: Add database migration for exports` |

**Note:** Feature criteria tasks (F1, F2, etc.) include implicit verification.
Task is only marked complete when `/verify-done` passes for that criterion.

### Background Tasks
Use for long-running operations (>30s):
- Test suite execution
- Build processes
- Database migrations
- Security audits

Press `Ctrl+B` to background a running task.
```

### Phase 3: Agent Spec Updates

Update agent specifications to leverage Tasks natively.

**Design Decision: Combined Tasks (Verification Implicit)**

Tasks combine implementation and verification into a single item. A task is only marked
`completed` when the internal `/verify-done` check passes. This keeps the task list
simpler while preserving the iterative impl→verify loop.

#### `/define-done` Enhancement

Add to `docs/agents/define-done/spec.md`:

```markdown
## Task Generation

After finalizing criteria, offer to generate a task template:

### Output: tasks.md
Create `docs/features/<feature>/tasks.md`:
```markdown
# Tasks: <feature-name>

## Implementation Tasks (verification implicit)

- [ ] F1: <criterion F1 implementation + verification>
  - blocked_by: none
  - criterion: "F1 - <criterion text>"
  - verify_type: AUTO

- [ ] F2: <criterion F2 implementation + verification>
  - blocked_by: F1
  - criterion: "F2 - <criterion text>"
  - verify_type: AUTO

- [ ] F3: <criterion F3 implementation + verification>
  - blocked_by: F2
  - criterion: "F3 - <criterion text>"
  - verify_type: HUMAN
```

Each task includes both implementation AND verification. Task is only complete when verified.
This file can be hydrated into Claude Code Tasks at session start.
```

#### `/build-feature` Enhancement

Add to `docs/agents/build-feature/spec.md`:

```markdown
## Task-Based Execution (Combined impl+verify)

### Session Start
1. Check for existing task list: `TaskList`
2. If empty, hydrate from `docs/features/<feature>/tasks.md`
3. If no tasks.md, create tasks from `done-criteria.md`

### Execution Loop (Iterative with Retry)
```
For each task in dependency order:
  1. TaskUpdate → status: in_progress
  2. Execute implementation
  3. Run /verify-done internally for this criterion
     - If FAIL → fix implementation, go to step 2 (retry)
     - If PASS → continue to step 4
  4. TaskUpdate → status: completed
  5. git commit
  6. Next task becomes unblocked
```

The retry loop is internal to each task. A task stays `in_progress` until verification
passes. This preserves the iterative `/build-feature` ↔ `/verify-done` flow while
keeping the task list clean (no separate verify tasks).

### Subagent Delegation
For maximum context isolation:
```
/user: implement feature with subagents

/claude:
  1. TaskCreate for all criteria (combined impl+verify)
  2. For each task:
     a. Task tool → subagent executes (impl + verify loop)
     b. Subagent returns result (only when verified)
     c. TaskUpdate → completed
     d. git commit
  3. Main agent orchestrates, subagents implement+verify
```

### Task-Based Resume
When `--resume` is used:
1. TaskList to see current state
2. Find first pending/in_progress task
3. Resume from there with full context
4. If `in_progress`, may need to re-verify before continuing
```

### Phase 4: Environment Setup

#### PowerShell Profile Updates

Add to `$PROFILE` (usually `~\Documents\PowerShell\Microsoft.PowerShell_profile.ps1`):

```powershell
# Claude Code Task Management
function Set-ClaudeTaskList {
    param([string]$Name)
    $env:CLAUDE_CODE_TASK_LIST_ID = $Name
    Write-Host "Task list set to: $Name" -ForegroundColor Green
}

function Clear-ClaudeTaskList {
    Remove-Item Env:\CLAUDE_CODE_TASK_LIST_ID -ErrorAction SilentlyContinue
    Write-Host "Task list cleared - using session-scoped tasks" -ForegroundColor Yellow
}

# Aliases
Set-Alias -Name ctask -Value Set-ClaudeTaskList
Set-Alias -Name ctaskclear -Value Clear-ClaudeTaskList

# Project-specific task list functions
function Start-HadleyBricksFeature {
    param([string]$FeatureName)
    Set-ClaudeTaskList "hb-$FeatureName"
    cd "C:\Users\Chris Hadley\hadley-bricks-inventory-management"
}

function Start-PeterbotFeature {
    param([string]$FeatureName)
    Set-ClaudeTaskList "pb-$FeatureName"
    cd "C:\Users\Chris Hadley\Discord-Messenger"
}
```

#### Usage Examples

```powershell
# Start a new feature with shared task list
ctask "inventory-export"

# In another terminal, join the same task list
ctask "inventory-export"

# Clear to use session-scoped tasks
ctaskclear

# Project-specific shortcuts
Start-HadleyBricksFeature "ebay-sync"
Start-PeterbotFeature "smart-home"
```

### Phase 5: Workflow Patterns

#### Pattern 1: Spec-Driven Development

```
1. Human creates/refines spec: docs/features/<feature>/done-criteria.md
2. Session start: Claude hydrates tasks from spec
3. Claude executes tasks in dependency order
4. Each task verified before marking complete
5. Session end: Task state persisted
6. New session: Resume from last state
```

#### Pattern 2: Subagent Delegation

```
Main Agent (Orchestrator):
  ├── TaskCreate: Design database schema
  ├── TaskCreate: Implement API endpoints (blocked by schema)
  ├── TaskCreate: Build UI components (blocked by API)
  └── TaskCreate: Write tests (blocked by UI)

For each task:
  Main Agent → Task tool → Subagent
  Subagent executes with clean context
  Subagent returns result
  Main Agent: TaskUpdate → completed
  Main Agent: git commit
  Next task unblocked
```

#### Pattern 3: Multi-Session Coordination

```
Terminal 1 (Implementation):
  $env:CLAUDE_CODE_TASK_LIST_ID = "feature-x"
  TaskCreate: impl tasks
  Execute impl tasks

Terminal 2 (Testing):
  $env:CLAUDE_CODE_TASK_LIST_ID = "feature-x"
  TaskList → sees impl progress
  TaskCreate: test tasks (blocked by impl)
  Wait for impl completion
  Execute test tasks

Terminal 3 (Documentation):
  $env:CLAUDE_CODE_TASK_LIST_ID = "feature-x"
  TaskCreate: docs tasks (blocked by impl)
  Execute docs tasks when unblocked
```

### Phase 6: Migration Path

#### Immediate (No Code Changes)
1. Update global `CLAUDE.md` with task management section
2. Update project `CLAUDE.md` files
3. Add PowerShell profile functions
4. Start using tasks manually

#### Short-term (Agent Updates)
1. Update `/define-done` to output `tasks.md` (combined impl+verify format)
2. Update `/build-feature` to hydrate tasks from spec with internal verify loop
3. `/verify-done` remains as internal verification (called within task execution)

#### Medium-term (Full Integration)
1. Deprecate TodoWrite usage in favour of Tasks
2. Add task-based resume to all agents
3. Implement shared task list patterns
4. Add task-based metrics and reporting

---

## Recommended Global CLAUDE.md (Final)

```markdown
# Global Claude Code Instructions

## Task Management (Default Behaviour)

### Always Use Tasks For
- Any implementation with 3+ steps
- Multi-file changes
- Work with dependencies (A must finish before B)
- Features that may span multiple sessions
- Coordination between multiple Claude sessions

### Task Commands
| Command | Purpose |
|---------|---------|
| `TaskCreate` | Create new task with dependencies |
| `TaskUpdate` | Change status, add/remove blockers |
| `TaskList` | View all tasks and status |
| `TaskGet` | Get details of specific task |

### Dependency Pattern
```
TaskCreate: "Build API endpoint"
  → no blockers (can start immediately)

TaskCreate: "Build UI component"
  → addBlockedBy: ["Build API endpoint"]
  → cannot start until API is complete
```

### Status Updates
- Mark `in_progress` BEFORE starting work
- Mark `completed` IMMEDIATELY after finishing
- Only ONE task should be `in_progress` at a time
- Never mark complete without evidence/verification

### Shared Task Lists
For multi-session work, coordinate via:
```powershell
$env:CLAUDE_CODE_TASK_LIST_ID = "project-feature"
```

Multiple Claude sessions with the same ID share task state.

### Hydration from Specs
When working from a spec file:
1. Read the spec at session start
2. Create tasks for each implementation step
3. Set dependencies based on order
4. Reference spec in task descriptions

### Background Tasks
For operations >30 seconds:
- Press `Ctrl+B` to background
- Continue other work while it runs
- Max ~10 concurrent tasks

## Code Conventions

- Prisma imports: `import { prisma } from '@/lib/prisma'`
- Next.js 15 async params: `{ params }: { params: Promise<{ id: string }> }`
```

---

## Project-Specific Additions

### Discord-Messenger CLAUDE.md Addition

```markdown
## Task Management

### Peterbot Development Tasks
When implementing Peterbot features:
1. Create tasks for each skill component
2. Set dependencies: API → Skill → Schedule → Test
3. Use `CLAUDE_CODE_TASK_LIST_ID=pb-<feature>`

### Integration with Scheduler
Scheduled job development (combined impl+verify):
- `F1: Add data fetcher` (no blockers, verify: fetcher returns data)
- `F2: Create skill SKILL.md` (blocked by F1, verify: skill executes)
- `F3: Add to SCHEDULE.md` (blocked by F2, verify: job registered)
- `F4: Test scheduled execution` (blocked by F3, verify: runs on schedule)

### Multi-System Changes
For changes spanning bot + API + dashboard:
```powershell
$env:CLAUDE_CODE_TASK_LIST_ID = "pb-cross-system"
```
All three can be worked on in parallel with proper blocking.
```

### Hadley-Bricks CLAUDE.md Addition

```markdown
## Task Management

### Feature Track with Tasks
The `/define-done` → `/build-feature` workflow now uses Tasks:

1. `/define-done` creates `tasks.md` template
2. Session start: Hydrate tasks from template
3. `/build-feature` executes tasks in order
4. Each criterion = one task
5. Dependencies enforce implementation order

### Dual-Write Task Pattern
For Sheets + Supabase changes:
- `F1: Update Sheets adapter` (no blockers, verify: adapter works)
- `F2: Update Supabase repository` (parallel with F1, verify: repo works)
- `F3: Update dual-write service` (blocked by F1+F2, verify: sync flows)

### Worktree + Task List Coordination
Each worktree should use its own task list:
```powershell
# Feature worktree
cd "C:\Users\Chris Hadley\hadley-bricks-feature-export"
$env:CLAUDE_CODE_TASK_LIST_ID = "hb-export"

# Fix worktree (separate task list)
cd "C:\Users\Chris Hadley\hadley-bricks-fix-sync"
$env:CLAUDE_CODE_TASK_LIST_ID = "hb-sync-fix"
```
```

---

## Verification Checklist

After implementation, verify:

- [ ] Global CLAUDE.md updated with task management section
- [ ] Discord-Messenger CLAUDE.md includes task integration
- [ ] Hadley-Bricks CLAUDE.md includes task integration
- [ ] PowerShell profile has task helper functions
- [ ] `/define-done` outputs `tasks.md` template
- [ ] `/build-feature` hydrates tasks from spec
- [ ] Tasks used by default for 3+ step implementations
- [ ] `CLAUDE_CODE_TASK_LIST_ID` used for multi-session work
- [ ] Background tasks used for long operations

---

## Rollback Plan

If issues arise, add to global CLAUDE.md:
```markdown
CLAUDE_CODE_ENABLE_TASKS=false
```

This reverts to TodoWrite-based tracking until issues are resolved.
