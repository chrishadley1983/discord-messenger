# Notion Playbook

Manage todos and ideas in Notion databases.

---

## Hadley API Endpoints

Base URL: `http://172.19.64.1:8100`

### Todos

| Action | Endpoint | Method | Body |
|--------|----------|--------|------|
| List incomplete | `/notion/todos` | GET | - |
| Create todo | `/notion/todos` | POST | `{"title": "...", "priority": "High", "due": "2026-02-10", "tags": ["work"]}` |
| Update todo | `/notion/todos/{id}` | PATCH | `{"status": "Done", "priority": "Low"}` |
| Complete todo | `/notion/todos/{id}/complete` | POST | - |
| Delete (archive) | `/notion/todos/{id}` | DELETE | - |

**Create fields:**
- `title` (required): Task title
- `priority` (optional): High, Medium, Low
- `due` (optional): ISO date (YYYY-MM-DD)
- `tags` (optional): Array of tag names

**Update fields:**
- `title`: New title
- `status`: Done, In Progress, Not Done
- `priority`: High, Medium, Low
- `due`: ISO date

### Ideas

| Action | Endpoint | Method | Body |
|--------|----------|--------|------|
| List recent | `/notion/ideas` | GET | - |
| Create idea | `/notion/ideas` | POST | `{"title": "...", "category": "Business", "notes": "..."}` |
| Update idea | `/notion/ideas/{id}` | PATCH | `{"category": "Personal"}` |
| Delete (archive) | `/notion/ideas/{id}` | DELETE | - |

**Create/Update fields:**
- `title`: Idea title
- `category`: Category name (e.g., Business, Personal, Tech)
- `notes`: Additional notes/description

---

## Trigger Phrases

### Todos
- "Show my todos" / "What's on my todo list?" → GET /notion/todos
- "Add a todo: {task}" / "Create a task: {task}" → POST /notion/todos
- "Mark {task} as done" / "Complete {task}" → POST /notion/todos/{id}/complete
- "Update {task} priority to high" → PATCH /notion/todos/{id}
- "Delete {task} todo" / "Remove {task}" → DELETE /notion/todos/{id}
- "What's the most urgent?" → GET /notion/todos (return highest priority)

### Ideas
- "Show my ideas" / "What ideas do I have?" → GET /notion/ideas
- "Add an idea: {idea}" / "Save this idea: {idea}" → POST /notion/ideas
- "Categorize {idea} as business" → PATCH /notion/ideas/{id}
- "Delete {idea}" / "Remove that idea" → DELETE /notion/ideas/{id}
- "Show business ideas" → GET /notion/ideas (filter by category)

---

## Response Format

### Todo List Response
```
📋 **Your Todos** (3 items)

🔴 **High Priority**
• Call dentist — Due: Feb 10
• Review contract — Due: Feb 12

🟡 **Medium Priority**
• Buy groceries

✅ 2 completed this week
```

### Create/Update Confirmation
```
✅ **Todo created**
• Title: Call dentist
• Priority: High
• Due: Feb 10, 2026
```

### Delete Confirmation
```
🗑️ **Archived:** Call dentist
```

---

## Notes

- Todos filter out completed items automatically
- Todos sort by: priority (high→low), then due date (soonest first)
- Ideas sort by: created date (newest first), limited to 20
- Delete operations archive (soft delete) - recoverable in Notion
- Page IDs are UUIDs like `12345678-1234-1234-1234-123456789abc`
