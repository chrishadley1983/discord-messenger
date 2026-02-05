---
name: hb-task-complete
description: Mark a Hadley Bricks workflow task as complete
trigger:
  - "complete task"
  - "done with"
  - "finished task"
  - "mark complete"
  - "task done"
scheduled: false
conversational: true
channel: null
---

# Hadley Bricks Task Complete

## Purpose

Marks a workflow task as complete in the Hadley Bricks system. User can reference by task ID or description. This is a WRITE operation that modifies data.

## Input Parsing

User provides task reference:
- "Complete task 5" → By ID
- "Done with shipping AMZ-123" → By description/order
- "Finished listing the DeLorean" → By context
- "Mark the reprice task done" → By type

## Confirmation Flow

**IMPORTANT:** This skill modifies data. Always confirm before executing.

1. Parse task reference from user message
2. Fetch task details to confirm correct task
3. Show task details and ask for confirmation
4. Execute completion on confirmation
5. Show updated task list

## Output Format

**Step 1 - Confirmation:**
```
✅ **Complete Task?**

Task #5: Ship order AMZ-123
└ 75192 Millennium Falcon to London
Priority: High | Due: 2pm

Reply "yes" to confirm or specify a different task.
```

**Step 2 - Completed:**
```
✅ **Task Completed!**

Marked as done: Ship order AMZ-123

📊 Progress today: 3/8 tasks done
Next high priority: Ship EBY-456 by 3pm
```

## Rules

- Always confirm before marking complete
- Show task details for verification
- Update progress count after completion
- Suggest next task if available
- If multiple tasks match, ask for clarification

## Ambiguity Handling

If task reference is ambiguous:
```
✅ **Which Task?**

Found multiple matches for "shipping":
1. Ship AMZ-123 - 75192 to London (High)
2. Ship EBY-456 - 10300 to Manchester (High)

Which one did you complete? (Reply with number)
```

## Error Handling

If task not found:
```
✅ **Task Not Found**

Couldn't find a task matching "XYZ".

Current tasks:
• Ship AMZ-123 (High)
• List new items (Medium)
• Review pricing (Low)

Which task did you want to complete?
```

If already completed:
```
✅ **Already Done**

Task "Ship AMZ-123" was already marked complete at 10:34am.

Did you mean a different task?
```

If API fails:
```
✅ **Task Completion**

⚠️ Could not update task - is Hadley Bricks running?

Please try again or mark complete in the app.
```

## Examples

**By ID:**
User: "Complete task 3"
```
✅ **Complete Task?**

Task #3: List 2 new sets
└ 10300 DeLorean, 40567 Forest Hideout
Priority: Medium

Confirm completion? (yes/no)
```

User: "yes"
```
✅ **Task Completed!**

✓ List 2 new sets

📊 Progress: 4/8 tasks done
Remaining high priority: 1 (Ship EBY-789)
```

**By description:**
User: "Done shipping the Millennium Falcon order"
```
✅ **Complete Task?**

Task #1: Ship order AMZ-123
└ 75192 Millennium Falcon to London
Priority: High

Is this the task you completed?
```

**Multiple completions:**
User: "Finished all the shipping"
```
✅ **Mark Multiple Complete?**

Found 3 shipping tasks:
1. Ship AMZ-123 - 75192 Millennium Falcon ✓
2. Ship AMZ-456 - 10300 DeLorean ✓
3. Ship EBY-789 - 21330 Home Alone ✓

Mark all 3 as complete? (yes/no)
```

User: "yes"
```
✅ **3 Tasks Completed!**

✓ Ship AMZ-123
✓ Ship AMZ-456
✓ Ship EBY-789

🎉 All shipping done for today!
📊 Progress: 5/8 tasks done
```
