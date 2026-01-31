# Merge Feature Command

You are now operating as the **Merge Feature Agent**. Follow the comprehensive instructions in `docs/agents/merge-feature-agent.md`.

## Quick Reference

### Usage
```
/merge-feature <mode>
```

### Available Modes

| Mode | Description |
|------|-------------|
| `<branch-name>` | Merge specific branch to main (with deploy verification) |
| `auto` | Auto-detect current feature branch |
| `list` | List unmerged branches |
| `status` | Show merge status |
| `check` | Check merge readiness (no action taken) |
| `preview` | Run critical path tests against Vercel preview |
| `verify-production` | Run critical path tests against production |
| `rollback` | Revert last merge and redeploy |

### Examples
```powershell
/merge-feature feature/bricklink-orders    # Full merge with deploy verification
/merge-feature check                        # Check if ready to merge
/merge-feature preview                      # Test preview deployment
/merge-feature verify-production            # Test production health
/merge-feature rollback                     # Revert last merge
/merge-feature list                         # List unmerged branches
```

### Track Detection

The agent detects the track from branch name:
- **FEATURE track:** `feature/*`, `chore/*`, `refactor/*` → Full prerequisites
- **FIX track:** `fix/*`, `hotfix/*`, `bugfix/*` → Abbreviated checks

### Prerequisites

**FEATURE track:**
1. Done criteria exists in `docs/features/<name>/`
2. Verify Done passed
3. `/test-execute pre-merge` passed
4. `/code-review branch` completed

**FIX track:**
1. `/code-review branch` completed

### Permissions

For this project:
- ❌ Cannot push directly to main (GitHub branch protection)
- ✅ Can create pull requests via `gh pr create`
- ✅ Can merge PRs via GitHub after checks pass
- ✅ Can delete local and remote branches
- ✅ Can force delete branches after merge confirmed
- ❌ Never force push to main

### Extended Merge Process

1. Detect track from branch name
2. Check prerequisites (track-specific)
3. Pre-merge verification
4. Fetch latest main
5. Execute merge with `--no-ff`
6. Post-merge verification (TypeScript, lint, tests)
7. Push to origin
8. **Wait for Vercel deployment** (NEW)
9. **Run production verification** (NEW)
10. **Update last-deploy.json** (NEW)
11. Delete merged branches
12. Generate merge report

### Configuration Files

| File | Purpose |
|------|---------|
| `docs/agents/merge-feature/config.json` | URLs, timeouts, track settings |
| `docs/agents/merge-feature/critical-paths.spec.ts` | Playwright verification tests |
| `docs/agents/merge-feature/last-deploy.json` | Last deployment record (for rollback) |

### Output Files

- Merge Report: `docs/merges/YYYY-MM-DD_<branch>.md`
- Last Deploy: `docs/agents/merge-feature/last-deploy.json`

### Recovery

Undo merge before push:
```powershell
git reset --hard HEAD~1
```

Undo merge after push (use rollback for verified recovery):
```powershell
/merge-feature rollback
```

Manual revert (if rollback unavailable):
```powershell
git revert -m 1 HEAD
git push origin main
```
