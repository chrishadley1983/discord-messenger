# Tech-Debt Agent

Systematically identify, classify, prioritise and remediate technical debt.

## Boot Sequence

1. Read `docs/agents/tech-debt/state.json` for last scan state
2. Read `docs/agents/tech-debt/tech-debt-registry.json` for current inventory
3. Get current git commit: `git rev-parse HEAD`
4. If lastScanCommit exists, check changed files: `git diff <lastScanCommit>..HEAD --stat`
5. Cross-reference changed files with registry items → mark as NEEDS_RESCAN
6. Report boot status

## Mode: $ARGUMENTS

Parse the mode from arguments:
- `scan` or empty → Full codebase scan
- `scan --scope=<path>` → Targeted scan
- `scan --category=<type>` → Single category (TS, DUP, CX, DC, DEP, etc.)
- `scan --quick` → Fast scan (complexity + types + dead code only)
- `report` → View current debt registry with trends
- `fix <DEBT-ID>` → Remediate specific item
- `fix --next` → Pick highest-priority unfixed item

---

## SCAN MODE

### Categories to Scan

| Category | Code | Detection Method |
|----------|------|------------------|
| Type Safety | `TS` | `grep -rn ": any" --include="*.ts" --include="*.tsx" src/` |
| Complexity | `CX` | Functions >50 lines, nesting >4 levels |
| Dead Code | `DC` | Unused exports, commented-out blocks |
| Duplication | `DUP` | Near-identical code blocks (manual analysis) |
| Dependencies | `DEP` | `npm outdated`, deprecated packages |
| Error Handling | `ERR` | Empty catch blocks, unhandled promises |
| Architecture | `ARCH` | Circular deps: `npx madge --circular src/` |

### Scan Process

For each category:
1. Run detection (grep, AST analysis, npm commands)
2. Filter out: node_modules, .next, generated files, test fixtures
3. For each finding:
   - Check if already in registry → update lastSeen
   - New finding → create registry item with scores
4. Items no longer detected → mark POTENTIALLY_RESOLVED

### Scoring

```
Priority = (Impact × 3) + (Spread × 2) + (Effort_Inverse × 1) / 6

Impact (1-5): How much this affects velocity/reliability
Spread (1-5): How many files/components affected
Effort_Inverse (1-5): How easy to fix (5=trivial, 1=major refactor)

Priority Labels:
  4.0-5.0 = CRITICAL (fix before next feature)
  3.0-3.9 = HIGH (fix this sprint)
  2.0-2.9 = MEDIUM (schedule for cleanup)
  1.0-1.9 = LOW (track, fix opportunistically)
```

### Registry Item Format

```json
{
  "id": "DEBT-001",
  "category": "TS",
  "title": "any type in [file]",
  "description": "Detailed description",
  "location": { "file": "path", "line": 45 },
  "affectedFiles": ["file1", "file2"],
  "scores": { "impact": 3, "spread": 2, "effortInverse": 4, "priority": 2.8 },
  "priorityLabel": "MEDIUM",
  "status": "DETECTED",
  "detectedCommit": "abc123",
  "detectedDate": "2026-02-01T10:00:00Z"
}
```

### Scan Output

1. Update `tech-debt-registry.json` with findings
2. Update `state.json` with scan metadata
3. Generate report: `docs/agents/tech-debt/reports/scan-YYYY-MM-DD.md`
4. Print summary to console

---

## FIX MODE

### Fix Process

1. Load the debt item from registry
2. Create remediation plan (show to user)
3. On approval:
   - Create branch: `fix/tech-debt-{ID}`
   - Make minimal changes
   - Verify: `npm run typecheck && npm run lint && npm run test`
4. If all pass:
   - Update registry: status=RESOLVED, resolvedCommit
   - Commit: `fix(tech-debt): resolve DEBT-{ID} - {summary}`
5. If fail:
   - Revert changes
   - Update registry: status=FIX_ATTEMPTED
   - Log failure reason

### Atomic Rules

- ONE debt item per commit
- NEVER change business logic, only structure/quality
- NEVER mark RESOLVED without passing ALL verification
- Smallest possible diff

---

## REPORT MODE

Generate dashboard showing:
- Total items by priority
- Trend vs last scan
- Critical/High items requiring attention
- Recently resolved items

---

## Anti-False-Positive Rules

1. NEVER flag framework conventions as debt (Next.js naming, etc.)
2. NEVER inflate severity - single `any` in utility is LOW, not CRITICAL
3. NEVER flag intentional patterns without evidence
4. ALWAYS provide file:line evidence
5. ALWAYS verify before classifying (is it really unused? really duplicated?)

---

## State Files

- `docs/agents/tech-debt/state.json` - Scan state, stats
- `docs/agents/tech-debt/tech-debt-registry.json` - Debt inventory
- `docs/agents/tech-debt/reports/` - Generated reports (commit to git)
