# Fix Command

You are now operating as the **Fix Agent**. Follow the comprehensive instructions in `docs/agents/fix-agent/spec.md`.

## Quick Reference

### Usage
```
/fix <description of the issue>
```

### Examples
```powershell
/fix orders page showing wrong date format
/fix inventory count not updating after sale
/fix typo on dashboard header
/fix slow query on products page
```

### Process Flow

1. **Analyse** - Understand the issue, search codebase, find root cause
2. **Plan** - Present fix approach, wait for explicit approval
3. **Branch** - Create `fix/<slug>` branch (only after approval)
4. **Build** - Implement approved fix only
5. **Verify** - TypeScript, lint, affected tests, smoke tests
6. **Handoff** - Commit, push, ready for `/code-review branch`

### Key Rules

- **ALWAYS wait for approval** before creating branch or writing code
- **Stay focused** - fix only what was approved
- **Note additional issues** found, don't fix them (scope control)
- **Escalate** if scope grows beyond 10 files

### Guardrails

| Threshold | Action |
|-----------|--------|
| > 5 files | Warning: "This fix is larger than typical. Consider feature track?" |
| > 10 files | Block: "Too large for fix track. Use `/define-done` instead." |
| > 100 lines | Warning: "Significant change. Confirm this is still a fix?" |

### Approval Gate

**What counts as approval:**
- "Yes", "Approved", "Go ahead", "Do it", "Looks good, proceed"

**What does NOT count as approval:**
- Silence, questions, "Maybe we should..."

### Output

- Fix report: `docs/fixes/YYYY-MM-DD_<slug>.md`
- Branch ready for code review
- Prompt: "Ready for `/code-review branch`"

### When to Use Fix Track

**Use `/fix` when:**
- Clear, isolated bug fix
- Small UI tweak
- Copy/text change
- Performance fix with obvious solution
- Single file or tightly scoped change

**Use Feature Track instead when:**
- Adding new functionality
- Significant refactoring
- Changes touching multiple systems
- Unclear scope or requirements

ARGUMENTS: <description of the issue>
