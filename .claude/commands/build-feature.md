# Build Feature Command

You are now operating as the **Build Feature Agent**. Follow the comprehensive instructions in `docs/agents/build-feature/spec.md`.

## Quick Reference

### Usage
```
/build-feature <feature-name> [options]
```

### Available Options

| Option | Default | Description |
|--------|---------|-------------|
| `--max-iterations` | 5 | Maximum build-verify cycles |
| `--resume` | false | Continue from saved state |
| `--dry-run` | false | Plan only, no code changes |
| `--skip-verify` | false | Build only, no verification (debugging) |
| `--autonomous` | false | Maximum autonomy, only BLOCK for credentials/destructive |
| `--cautious` | false | BLOCK immediately on any failure (no recovery attempts) |

### Autonomy Levels

| Flag | Behaviour |
|------|-----------|
| (default) | Attempt recovery, BLOCK if stuck |
| `--autonomous` | Maximum autonomy, only BLOCK for credentials/destructive actions |
| `--cautious` | BLOCK immediately on any failure (no recovery attempts) |

### Examples
```powershell
/build-feature inventory-export              # Start fresh build (default autonomy)
/build-feature inventory-export --autonomous # Maximum autonomy
/build-feature inventory-export --cautious   # BLOCK on any issue
/build-feature inventory-export --max-iterations=10
/build-feature inventory-export --resume     # After human fix
/build-feature inventory-export --dry-run    # Preview plan only
```

## The Autonomous Loop

Once triggered, the agent operates without human input until exit:

```
Human: /build-feature inventory-export

Build Feature Agent:
  ├── Iteration 1: Build → Verify → FAILED (2 criteria)
  ├── Iteration 2: Fix → Verify → FAILED (1 criterion)
  ├── Iteration 3: Fix → Verify → CONVERGED ✅
  └── Exit: Report success, pending HUMAN_VERIFY review
```

## Prerequisites

Before running:
- `docs/features/<feature>/done-criteria.md` must exist (run `/define-done` first)
- Git working directory should be clean (recommended)

**Note:** The agent will attempt to start the app automatically if not running (unless `--cautious`).

## Feature Branch Workflow

The agent automatically creates a feature branch if on main:

```powershell
# If on main, creates:
git checkout -b feature/<feature-name>
```

**Why feature branches are mandatory:**
- GitHub branch protection prevents direct push to main
- All changes must go through pull requests
- Feature branches enable code review before merge

## Autonomous Recovery

The agent attempts to fix common blockers before escalating to human:

| Check Failed | Recovery Action | Max Attempts |
|--------------|-----------------|--------------|
| App not running | `npm run dev` in background | 3 |
| Port 3000 in use | `npx kill-port 3000` then start | 2 |
| Database unreachable | Check Supabase MCP, retry | 3 |
| Missing node_modules | `npm install` | 1 |
| Build errors on start | Read error, attempt fix, restart | 2 |

All recovery actions are logged in the build output.

## Exit Conditions

| Condition | Status | Human Action |
|-----------|--------|--------------|
| All AUTO_VERIFY pass | CONVERGED | Review HUMAN_VERIFY, then test/merge |
| Max iterations reached | ESCALATED | Review history, decide approach |
| Same failure 2x | ESCALATED | Different approach needed |
| Regression detected | ESCALATED | Review what broke |
| App not running | RECOVERED | Auto: start server |
| Port conflict | RECOVERED | Auto: kill-port + restart |
| Build error | RECOVERED | Auto: attempt fix, restart |
| Recovery exhausted | BLOCKED | Review recovery log, fix manually |
| Credentials missing | BLOCKED | Provide secrets |
| Destructive action needed | BLOCKED | Confirm & execute manually |
| Ambiguous requirement | BLOCKED | Clarify criteria |
| External dependency down | BLOCKED | Wait for service restoration |
| File in scope guard | BLOCKED | Approve or make manual change, then `--resume` |

## Scope Guards

These files require explicit approval before modification:

**Requires Approval:**
- `package.json`, `package-lock.json`
- `*.config.js`, `*.config.ts`
- `supabase/migrations/*`
- `.env*`, `CLAUDE.md`

**Requires Confirmation:**
- `lib/auth/*`
- `lib/supabase/*`
- `middleware.ts`

**Limits:**
- Max 10 files per iteration
- Max 500 lines changed per iteration

## Anti-Thrashing Protection

The agent detects and exits on:
- **Repeated failure:** Same failure signature 2 iterations in a row
- **Oscillation:** Alternating between two failure states (A→B→A)
- **Regression:** Previously passing criteria now failing

## Criteria as Contract

The `done-criteria.md` file is the ONLY specification. The agent:
- Does NOT invent requirements
- Does NOT add unrequested features
- Does NOT "improve" beyond criteria
- Builds EXACTLY what's specified, nothing more

## Output Files

| File | Purpose |
|------|---------|
| `docs/features/<feature>/build-state.json` | Current iteration state |
| `docs/features/<feature>/build-log.md` | Human-readable build history |

## Internal Verify Done Call

After each build iteration, the agent calls Verify Done internally:
- Uses `--auto-only` mode (skips HUMAN_VERIFY during loop)
- Parses `verify-report.json` for verdict
- Uses `failureSignature` for anti-thrashing detection

## Iteration Context Management

**First iteration:** Load criteria, CLAUDE.md, related source files
**Subsequent iterations:** Also load previous verify-report, build-state, failure context

To manage context window, summarize previous iterations rather than retain full history.

## Next Steps After CONVERGED

1. Review HUMAN_VERIFY criteria (screenshots in `evidence/`)
2. `/test-plan <feature>` - Generate test coverage
3. `/code-review branch` - Review all changes
4. `/merge-feature feature/<feature>` - Create PR and merge to main

## Handoff to Human (on ESCALATED)

When escalated, the agent provides:
- Full iteration history summary
- Analysis of stuck point
- Possible root causes
- Recommended human action
- Command to resume after fix

## Hadley Bricks Patterns

When building for Hadley Bricks, follow:
- Repository pattern for data access
- shadcn/ui components for UI
- Sonner for toast notifications
- Zod for request validation
- Google Sheets dual-write where applicable
