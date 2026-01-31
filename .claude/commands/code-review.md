# Code Review Command

You are now operating as the **Code Review Agent**. Follow the comprehensive instructions in `docs/reviews/code-review-agent.md`.

## Quick Reference

### Usage
```
/code-review <mode>
```

### Available Modes

| Mode | Description |
|------|-------------|
| `staged` | Review staged changes only |
| `branch` | Review all changes vs main |
| `security` | Security-focused review |
| `performance` | Performance-focused review |
| `dry` | Find duplicate/redundant code |
| `architecture` | File organisation check |
| `full` | Complete review (all checks) |

### Examples
```powershell
/code-review staged         # Before committing
/code-review branch         # Before PR/merge
/code-review security       # Security audit
```

### Standard Workflow

1. **Before committing:** `/code-review staged`
2. **Before merging:** `/code-review branch`
3. **Security audit:** `/code-review security`

### Review Categories

- Correctness: Logic errors, edge cases
- Security: Credentials, RLS, input validation
- Performance: N+1 queries, re-renders
- Standards: TypeScript, patterns, conventions

### Hadley Bricks Checklist

- [ ] Platform credentials encrypted?
- [ ] Adapter pattern followed?
- [ ] Repository pattern followed?
- [ ] Dual-write implemented?
- [ ] RLS policies for new tables?
- [ ] Tests added for new code?

### Severity Levels

- **Critical**: Security issues, data loss, bugs
- **Major**: Logic errors, missing validation
- **Minor**: Style, suggestions
- **Nitpick**: Preferences
