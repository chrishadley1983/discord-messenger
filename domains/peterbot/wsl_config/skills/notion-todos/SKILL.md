# Notion Todos

## Purpose
Show and manage tasks from "Claude Managed To Dos" database.

## Triggers
- "my todos", "task list", "what's on my plate"
- "todo list", "tasks", "what do I need to do"
- "pending tasks", "outstanding items"

## Schedule
- 08:00 UK daily (part of morning-briefing, if tasks exist)

## Data Source
Hadley API: `curl http://172.19.64.1:8100/notion/todos`

## Pre-fetcher
`get_notion_todos_data()` - fetches:
- All incomplete tasks
- Task properties: title, status, priority, due date, tags
- Sorted by: priority (high→low), then due date (soonest first)

## Output Format

**If tasks exist:**
```
📋 **To-Do List** ({count} items)

**🔴 High Priority**
• {task title} (due: {date})
• {task title}

**🟡 Medium Priority**
• {task title} (due: {date})
• {task title}

**🟢 Low/No Priority**
• {task title}
• {task title}
```

**If no tasks:**
```
📋 All clear - no pending tasks!
```

## Guidelines
- **Never show raw JSON** - only present the formatted human-readable output
- Group by priority if priority field exists
- Show due dates if present (highlight overdue in bold)
- Max 10 tasks in summary, then "+N more"
- For scheduled runs, skip if no incomplete tasks
- Support status field: Not Started, In Progress, Done

## Conversational
Yes - follow-ups:
- "Mark {task} as done"
- "What's the most urgent?"
- "Add a new task: {description}"
- "Show completed tasks"

## Related Skills
- `notion-add-todo` - add new tasks
- `notion-complete-todo` - mark tasks done (future)
