# Tech-Debt Agent Specification

**Version:** 1.0  
**Type:** Initializer (Analytical) + Coding (Remediation)  
**Command:** `/tech-debt [mode]`  
**Project:** Cross-project (Hadley Bricks, PeterBot, FamilyFuel)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Design Principles Alignment](#2-design-principles-alignment)
3. [Modes](#3-modes)
4. [Standard Boot Sequence](#4-standard-boot-sequence)
5. [Phase 1: Discovery Scan](#5-phase-1-discovery-scan)
6. [Phase 2: Debt Classification](#6-phase-2-debt-classification)
7. [Phase 3: Impact Assessment](#7-phase-3-impact-assessment)
8. [Phase 4: Remediation Planning](#8-phase-4-remediation-planning)
9. [Phase 5: Remediation Execution](#9-phase-5-remediation-execution)
10. [Phase 6: Verification](#10-phase-6-verification)
11. [Anti-False-Positive Prompts](#11-anti-false-positive-prompts)
12. [State Management](#12-state-management)
13. [Debt Registry Schema](#13-debt-registry-schema)
14. [Error Handling](#14-error-handling)
15. [Output Templates](#15-output-templates)
16. [Handoffs](#16-handoffs)
17. [Examples](#17-examples)

---

## 1. Overview

### 1.1 Purpose

The Tech-Debt Agent systematically identifies, classifies, prioritises and remediates technical debt across the codebase. It operates as a **Factory Pattern pair**: an Initializer (scanner/analyst) that produces a machine-readable debt registry, and a Coding Agent (remediator) that picks individual debt items and resolves them with verification.

### 1.2 Why This Agent?

Technical debt accumulates silently during rapid feature development. Without systematic detection:
- Code quality degrades incrementally until refactoring becomes a project in itself
- Patterns that worked at 10 components break at 50
- Build times, test times, and developer experience erode
- Security and performance implications hide in plain sight
- New features take longer because of hidden coupling and complexity

### 1.3 Scope

| In Scope | Out of Scope |
|----------|--------------|
| Code-level debt (duplication, complexity, dead code) | Business logic correctness (that's Verify Done) |
| Architecture debt (coupling, abstraction gaps) | Feature requests or enhancements |
| Dependency debt (outdated packages, deprecated APIs) | Performance optimisation (that's Performance Agent) |
| Testing debt (missing coverage, brittle tests) | Security vulnerabilities (that's Security Agent) |
| Documentation debt (missing/stale inline docs) | Full documentation (that's Documentation Agent) |
| Type safety debt (any types, missing generics) | Database schema design (that's Database Agent) |
| Build/config debt (unused configs, slow builds) | Release process (that's Release Manager) |

### 1.4 Relationship to Other Agents

The Tech-Debt Agent is a **complement, not a replacement** for specialised agents. It detects debt broadly and routes complex findings to the right specialist:

```
Tech-Debt Agent ──detects──> Performance-related debt ──routes──> Performance Agent
                ──detects──> Security-related debt    ──routes──> Security Agent
                ──detects──> Testing gaps             ──routes──> Test Plan Agent
                ──detects──> Documentation gaps       ──routes──> Documentation Agent
                ──remediates──> Code quality, duplication, complexity, types, dead code
```

---

## 2. Design Principles Alignment

| Principle | Implementation |
|-----------|----------------|
| **Externalise the Goal** | Debt Registry (`tech-debt-registry.json`) — machine-readable backlog with severity/effort/impact scores |
| **Atomic Progress** | Remediator picks ONE debt item, fixes it, verifies, updates registry. Never batches unrelated fixes. |
| **Clean Campsite** | Every scan produces a full report. Every remediation updates the registry and commits cleanly. |
| **Standard Boot-up** | Reads CLAUDE.md → reads debt registry → git diff since last scan → detects invalidations → acts |
| **Tests as Truth** | Remediation is only marked RESOLVED when all existing tests pass AND no regressions introduced |

---

## 3. Modes

### 3.1 Scan Modes

| Command | Scope | When to Use |
|---------|-------|-------------|
| `/tech-debt scan` | Full codebase scan | Periodic health check (weekly/sprint) |
| `/tech-debt scan --scope=<path>` | Targeted directory/file scan | After major feature work |
| `/tech-debt scan --category=<type>` | Single category scan | Focused cleanup |
| `/tech-debt scan --quick` | Fast scan (complexity + types + dead code only) | Pre-merge check |

### 3.2 Action Modes

| Command | Action | When to Use |
|---------|--------|-------------|
| `/tech-debt report` | View current debt registry with trends | Sprint planning, prioritisation |
| `/tech-debt fix <DEBT-ID>` | Remediate a specific debt item | Targeted cleanup |
| `/tech-debt fix --next` | Pick highest-priority unfixed item | Dedicated cleanup sessions |
| `/tech-debt fix --batch=<category>` | Fix all items in a category (atomic per-item) | Category-focused sprints |

---

## 4. Standard Boot Sequence

```
┌─────────────────────────────────────────────────────┐
│ BOOT SEQUENCE                                        │
│                                                       │
│ 1. Read CLAUDE.md (project context)                  │
│ 2. Read docs/agents/tech-debt/state.json             │
│    → lastScanCommit, lastScanDate, itemCount         │
│ 3. Read docs/agents/tech-debt/tech-debt-registry.json│
│    → Current debt inventory                           │
│ 4. git diff <lastScanCommit>..HEAD --stat            │
│    → Files changed since last scan                    │
│ 5. Cross-reference changed files with registry        │
│    → Mark affected items as NEEDS_RESCAN              │
│ 6. Report boot status                                │
│    → "Last scan: <date>, <n> items, <m> need rescan" │
│ 7. Proceed based on mode                              │
└─────────────────────────────────────────────────────┘
```

### Invalidation Rules

| Change Detected | Invalidation Action |
|-----------------|---------------------|
| File modified that has debt items | Mark items as `NEEDS_RESCAN` |
| File deleted that has debt items | Mark items as `POTENTIALLY_RESOLVED` |
| New files added | Flag for scan (not in registry yet) |
| Package.json/lock changed | Re-scan dependency debt |
| tsconfig/eslint config changed | Re-scan type/lint debt |

---

## 5. Phase 1: Discovery Scan

The scanner runs automated analysis across multiple dimensions:

### 5.1 Scan Dimensions

| Dimension | Method | Tool |
|-----------|--------|------|
| **Complexity** | Cyclomatic complexity per function | AST analysis or `npx eslint --rule complexity` |
| **Duplication** | Identical/near-identical code blocks | `jscpd` or manual AST comparison |
| **Dead Code** | Unused exports, unreachable branches | TypeScript compiler + `ts-prune` |
| **Type Safety** | `any` types, missing generics, type assertions | `grep -r ": any"`, TS strict checks |
| **Dependency Health** | Outdated packages, deprecated APIs | `npm outdated`, `npm audit` |
| **Test Coverage Gaps** | Files with no corresponding tests | File-to-test mapping analysis |
| **Code Smells** | Long functions (>50 lines), deep nesting (>4 levels), large files (>300 lines) | AST analysis, line counting |
| **Import Health** | Circular dependencies, barrel file bloat | `madge --circular`, import analysis |
| **Error Handling** | Missing try/catch, unhandled promises, empty catch blocks | AST pattern matching |
| **Naming Consistency** | Inconsistent naming patterns across codebase | Pattern analysis |

### 5.2 Scan Process

```
For each scan dimension:
  1. Run automated detection tool
  2. Filter results (exclude node_modules, generated files, test fixtures)
  3. Cross-reference with existing registry
  4. New items → add to registry as DETECTED
  5. Existing items still present → keep, update lastSeen
  6. Existing items no longer detected → mark POTENTIALLY_RESOLVED
  7. Record scan metadata (duration, files scanned, commit hash)
```

---

## 6. Phase 2: Debt Classification

Every detected item is classified using this taxonomy:

### 6.1 Categories

| Category | Code | Description | Examples |
|----------|------|-------------|----------|
| **Duplication** | `DUP` | Repeated code that should be abstracted | Copy-pasted API handlers, repeated form validation |
| **Complexity** | `CX` | Overly complex functions/components | Cyclomatic complexity >10, deeply nested conditions |
| **Dead Code** | `DC` | Code that serves no purpose | Unused exports, commented-out blocks, unreachable branches |
| **Type Safety** | `TS` | Missing or weak typing | `any` types, type assertions, missing generics |
| **Dependencies** | `DEP` | Package-level debt | Outdated majors, deprecated packages, unused dependencies |
| **Testing** | `TEST` | Coverage or quality gaps | Untested files, brittle tests, missing edge cases |
| **Architecture** | `ARCH` | Structural/design debt | Circular dependencies, god components, wrong abstractions |
| **Error Handling** | `ERR` | Missing or inadequate error handling | Empty catch blocks, unhandled promise rejections |
| **Build/Config** | `CFG` | Build system and configuration debt | Unused configs, slow builds, inconsistent environments |
| **Documentation** | `DOC` | Missing or stale inline documentation | No JSDoc on public APIs, outdated comments |

### 6.2 Severity Scoring

Each item receives a composite score:

```
Priority Score = (Impact × 3) + (Spread × 2) + (Effort_Inverse × 1)
                 ─────────────────────────────────────────────────────
                                         6

Where:
  Impact (1-5):        How much this debt affects development velocity/reliability
  Spread (1-5):        How many files/components are affected
  Effort_Inverse (1-5): How easy to fix (5 = trivial, 1 = major refactor)
```

| Priority Score | Label | Action |
|---------------|-------|--------|
| 4.0 - 5.0 | 🔴 CRITICAL | Fix before next feature work |
| 3.0 - 3.9 | 🟠 HIGH | Fix within current sprint |
| 2.0 - 2.9 | 🟡 MEDIUM | Schedule for cleanup sprint |
| 1.0 - 1.9 | 🟢 LOW | Track, fix opportunistically |

---

## 7. Phase 3: Impact Assessment

For each HIGH or CRITICAL item, the agent generates an impact assessment:

### 7.1 Impact Dimensions

| Dimension | Question | Evidence |
|-----------|----------|----------|
| **Velocity** | Does this slow down feature development? | Time spent working around the debt |
| **Reliability** | Does this cause bugs or instability? | Related error logs, test failures |
| **Maintainability** | Does this make code harder to understand? | Complexity score, coupling metrics |
| **Scalability** | Will this break at larger scale? | Pattern analysis, known limits |
| **Developer Experience** | Does this frustrate or confuse? | Inconsistencies, misleading abstractions |

### 7.2 Dependency Mapping

```
For each debt item:
  1. Which files are affected?
  2. Which features depend on those files?
  3. Which other debt items are related?
  4. What is the blast radius of a fix?
  5. Are there prerequisite fixes needed first?
```

---

## 8. Phase 4: Remediation Planning

For each item to fix, the agent produces a remediation plan BEFORE making changes:

### 8.1 Remediation Plan Template

```markdown
## Remediation Plan: DEBT-{ID}

### Item
- Category: {category}
- Location: {file}:{line}
- Priority: {score} ({label})

### Current State
{Description of the debt and its impact}

### Proposed Fix
{Specific changes to make}

### Files Affected
- {file1} — {what changes}
- {file2} — {what changes}

### Verification Criteria
- [ ] All existing tests pass
- [ ] No new TypeScript errors
- [ ] No new ESLint errors
- [ ] {Specific verification for this fix}

### Risk Assessment
- Blast radius: {Low/Medium/High}
- Regression risk: {Low/Medium/High}
- Rollback strategy: {git revert / manual steps}

### Prerequisites
- {Any other debt items that should be fixed first}
- {Any other conditions}
```

---

## 9. Phase 5: Remediation Execution

The Coding Agent (remediator) follows strict atomic progress:

### 9.1 Single Item Fix Flow

```
1. Read remediation plan for DEBT-{ID}
2. Create feature branch: fix/tech-debt-{ID}
3. Make changes per plan
4. Run verification:
   a. npm run typecheck (zero errors)
   b. npm run lint (zero errors)  
   c. npm run test (all pass, no regressions)
   d. Item-specific verification criteria
5. If ALL pass:
   → Update registry: status = RESOLVED, resolvedCommit = {hash}
   → Commit with message: "fix(tech-debt): resolve DEBT-{ID} - {summary}"
6. If ANY fail:
   → Log failure reason
   → Either iterate (max 3 attempts) or escalate to human
   → Update registry: status = FIX_ATTEMPTED, lastAttempt = {date}
7. Clean exit: update state.json with results
```

### 9.2 Iteration Budget

| Priority | Max Fix Attempts | Escalation |
|----------|------------------|------------|
| CRITICAL | 5 | Alert human with full context |
| HIGH | 3 | Log to state, pick next item |
| MEDIUM | 2 | Log to state, skip |
| LOW | 1 | Log to state, skip |

### 9.3 Atomic Progress Rules

- **ONE debt item per commit** — never bundle unrelated fixes
- **Branch per item** — `fix/tech-debt-{ID}` for traceability
- **Full verification before marking resolved** — no partial fixes
- **If a fix introduces new debt** — log it as a new item, don't chase it now
- **Never modify business logic** — only structural/quality improvements

---

## 10. Phase 6: Verification

Post-remediation verification ensures no regressions:

### 10.1 Verification Checklist

| Check | Method | Required |
|-------|--------|----------|
| TypeScript compiles | `npm run typecheck` | Always |
| ESLint passes | `npm run lint` | Always |
| All tests pass | `npm run test` | Always |
| No new `any` types | `grep -r ": any" --include="*.ts" --include="*.tsx"` | For TS category |
| Complexity reduced | Re-run complexity analysis on affected files | For CX category |
| Duplication removed | Re-run duplication detection | For DUP category |
| Dead code removed | Re-run dead code detection | For DC category |
| Build still works | `npm run build` | Always |

### 10.2 Regression Detection

If remediation introduces failures:
1. Immediately revert changes
2. Log the failure with full context
3. Update registry with `FIX_BLOCKED` status and reason
4. Move to next item (don't get stuck)

---

## 11. Anti-False-Positive Prompts

### Scanner Integrity

```
When scanning for technical debt, you MUST:

1. NEVER flag intentional design decisions as debt without evidence
   - If a pattern is used consistently, it may be deliberate
   - Check comments and documentation for rationale
   - "Unusual" is not the same as "wrong"

2. NEVER flag framework conventions as debt
   - Next.js file naming (page.tsx, layout.tsx) is convention, not smell
   - Supabase RLS patterns may look repetitive but are correct
   - Framework-specific patterns should be evaluated against framework docs

3. NEVER inflate severity scores
   - A single `any` type in a utility is LOW, not CRITICAL
   - Dead code in a feature flag is deliberate, not debt
   - Complexity in a state machine may be inherent, not excessive

4. ALWAYS verify before classifying:
   - Is this actually unused, or dynamically imported?
   - Is this duplication, or intentional variation?
   - Is this complexity necessary for the domain?

5. ALWAYS provide concrete evidence:
   - File paths and line numbers
   - Actual metrics (complexity score, not "complex")
   - Specific impact (not "could cause problems")
```

### Remediator Integrity

```
When fixing technical debt, you MUST:

1. NEVER change behaviour — only structure/quality
2. NEVER "fix" working code that doesn't match the debt description
3. NEVER introduce new patterns not already used in the codebase
4. NEVER mark as RESOLVED without passing ALL verification checks
5. ALWAYS preserve existing test behaviour exactly
6. ALWAYS keep changes minimal — smallest possible diff
```

---

## 12. State Management

### 12.1 State File: `docs/agents/tech-debt/state.json`

```json
{
  "agent": "tech-debt",
  "version": "1.0",
  "lastScanCommit": "abc123",
  "lastScanDate": "2026-02-01T10:00:00Z",
  "lastScanDuration": "45s",
  "lastFixCommit": "def456",
  "lastFixDate": "2026-02-01T11:00:00Z",
  "registryStats": {
    "total": 42,
    "critical": 2,
    "high": 8,
    "medium": 18,
    "low": 14,
    "resolved": 12,
    "needsRescan": 3
  },
  "trends": {
    "scansRun": 5,
    "itemsResolved": 12,
    "itemsIntroduced": 3,
    "netChange": -9
  }
}
```

### 12.2 Registry File: `docs/agents/tech-debt/tech-debt-registry.json`

See Section 13 for full schema.

---

## 13. Debt Registry Schema

```json
{
  "version": "1.0",
  "lastUpdated": "2026-02-01T10:00:00Z",
  "scanCommit": "abc123",
  "items": [
    {
      "id": "DEBT-001",
      "category": "TS",
      "title": "any type in eBay API response handler",
      "description": "Response from eBay Trading API typed as `any` in getSellerList.ts:45. Affects downstream type safety for 12 consuming components.",
      "location": {
        "file": "src/services/ebay/getSellerList.ts",
        "line": 45,
        "function": "parseSellerListResponse"
      },
      "affectedFiles": [
        "src/services/ebay/getSellerList.ts",
        "src/components/features/listings/ListingsTable.tsx"
      ],
      "scores": {
        "impact": 3,
        "spread": 4,
        "effortInverse": 4,
        "priority": 3.5
      },
      "priorityLabel": "HIGH",
      "status": "DETECTED",
      "detectedCommit": "abc123",
      "detectedDate": "2026-02-01T10:00:00Z",
      "lastSeenCommit": "abc123",
      "resolvedCommit": null,
      "resolvedDate": null,
      "fixAttempts": 0,
      "relatedItems": ["DEBT-003"],
      "routeTo": null,
      "notes": ""
    }
  ]
}
```

### Status Values

| Status | Meaning |
|--------|---------|
| `DETECTED` | Found by scan, not yet addressed |
| `NEEDS_RESCAN` | File changed since detection, may be resolved |
| `POTENTIALLY_RESOLVED` | File deleted or heavily refactored |
| `IN_PROGRESS` | Remediator is working on it |
| `FIX_ATTEMPTED` | Fix tried but verification failed |
| `FIX_BLOCKED` | Fix caused regressions, reverted |
| `RESOLVED` | Fixed and verified |
| `WONT_FIX` | Acknowledged as acceptable (with reason) |
| `ROUTED` | Sent to specialist agent (Performance, Security, etc.) |

---

## 14. Error Handling

| Error | Recovery | Escalation |
|-------|----------|------------|
| Scan tool not installed | Attempt `npm install`, log if fails | Report missing tool to human |
| Scan timeout (>5 min per dimension) | Skip dimension, note in report | Log and continue |
| Registry file corrupted | Attempt JSON repair, fallback to fresh scan | Alert human |
| Fix introduces TypeScript errors | Revert immediately | Mark FIX_BLOCKED |
| Fix breaks tests | Revert immediately | Mark FIX_BLOCKED with test details |
| Fix causes circular dependency | Revert immediately | Mark FIX_BLOCKED, may need ARCH review |
| Git conflict during fix | Abort fix, log conflict | Mark FIX_BLOCKED |
| Insufficient context to assess | Ask human for guidance | Don't guess at intent |

---

## 15. Output Templates

### 15.1 Scan Report

```markdown
# Tech-Debt Scan Report

**Date:** {date}
**Commit:** {hash}
**Scope:** {Full / Targeted: path}
**Duration:** {time}

## Summary

| Category | Count | Critical | High | Medium | Low |
|----------|-------|----------|------|--------|-----|
| Duplication | 5 | 0 | 2 | 2 | 1 |
| Complexity | 8 | 1 | 3 | 3 | 1 |
| Dead Code | 3 | 0 | 0 | 2 | 1 |
| Type Safety | 12 | 0 | 4 | 5 | 3 |
| Dependencies | 2 | 1 | 1 | 0 | 0 |
| **Total** | **30** | **2** | **10** | **12** | **6** |

## Trend (vs last scan)

| Metric | Previous | Current | Change |
|--------|----------|---------|--------|
| Total items | 35 | 30 | -5 ✅ |
| Critical | 3 | 2 | -1 ✅ |
| Resolved since last | — | 8 | — |
| New since last | — | 3 | — |

## Critical Items (Immediate Action)

### DEBT-015: [Title]
- **Location:** {file}:{line}
- **Impact:** {description}
- **Suggested Fix:** {approach}
- **Effort:** {estimate}

## High Priority Items

### DEBT-{ID}: [Title]
...

## Routed to Specialist Agents

| Item | Routed To | Reason |
|------|-----------|--------|
| DEBT-022 | Performance Agent | Query in hot path, N+1 pattern |
| DEBT-028 | Security Agent | Unsanitised user input in API route |

## Items Resolved Since Last Scan

| Item | Category | Resolved By |
|------|----------|-------------|
| DEBT-008 | TS | fix/tech-debt-008 (abc123) |
```

### 15.2 Fix Report

```markdown
# Tech-Debt Fix Report: DEBT-{ID}

**Date:** {date}
**Item:** {title}
**Category:** {category}
**Priority:** {score} ({label})

## Changes Made

| File | Change |
|------|--------|
| {file1} | {description} |
| {file2} | {description} |

## Verification Results

| Check | Result |
|-------|--------|
| TypeScript compiles | ✅ PASS |
| ESLint passes | ✅ PASS |
| All tests pass | ✅ PASS (148/148) |
| Item-specific check | ✅ PASS |

## Result: RESOLVED ✅

Commit: {hash}
Branch: fix/tech-debt-{ID}
```

---

## 16. Handoffs

### 16.1 From Tech-Debt → Specialist Agents

```markdown
## Tech-Debt → {Agent Name}

**Routed Item:** DEBT-{ID}
**Category:** {category}
**Reason:** {why this needs specialist attention}

### Context
{Description of the debt item}

### Location
{File paths and line numbers}

### Suggested Approach
{Initial analysis of what might be needed}

### Priority
{Score and label from debt assessment}
```

### 16.2 From Tech-Debt → Define Done (for major refactors)

When a debt item is too large for atomic remediation:

```markdown
## Tech-Debt → Define Done

**Debt Item:** DEBT-{ID}
**Reason:** Remediation requires feature-level scope

### Problem
{Full description of the architectural debt}

### Why It Can't Be Fixed Atomically
{Explanation of scope and dependencies}

### Suggested Feature Scope
{Outline of what the refactor feature should accomplish}

### Related Debt Items
{Other items that would be resolved by this refactor}
```

### 16.3 From Build Feature → Tech-Debt (post-feature scan)

```markdown
## Build Feature → Tech-Debt

**Feature:** {feature-name}
**Request:** Post-feature debt scan

### Files Changed
{List from git diff}

### Scan Requested
- Complexity analysis on new/modified files
- Duplication check against existing codebase
- Type safety audit on new code
- Import health check
```

---

## 17. Examples

### 17.1 Full Scan Session

```
User: /tech-debt scan

Tech-Debt Agent:
  [BOOT] Reading CLAUDE.md... ✓
  [BOOT] Reading state.json... Last scan: 2026-01-28 (abc123)
  [BOOT] Reading registry... 35 items tracked
  [BOOT] Checking changes... 12 files modified since last scan
  [BOOT] 4 registry items need rescan

  [SCAN] Starting full codebase scan...
  [SCAN] Complexity analysis... 8 items found
  [SCAN] Duplication detection... 5 items found
  [SCAN] Dead code detection... 3 items found
  [SCAN] Type safety audit... 12 items found
  [SCAN] Dependency check... 2 items found

  [CLASSIFY] Scoring and classifying 30 items...
  [CLASSIFY] 2 CRITICAL, 10 HIGH, 12 MEDIUM, 6 LOW
  [CLASSIFY] 3 items routed to specialist agents

  [REPORT] Generating scan report...

  Scan complete. 30 active debt items (down from 35).
  2 critical items require immediate attention.

  View full report: docs/agents/tech-debt/reports/scan-2026-02-01.md
```

### 17.2 Targeted Fix Session

```
User: /tech-debt fix DEBT-015

Tech-Debt Agent:
  [BOOT] Reading context... ✓
  [LOAD] DEBT-015: "any type in eBay API response handler"
  [PLAN] Generating remediation plan...

  Remediation Plan:
  - Replace `any` with proper `EbaySellerListResponse` interface
  - Add Zod validation schema for runtime safety
  - Update 3 consuming files with typed references
  - Blast radius: Medium (12 downstream components)

  Proceed with fix? [Y/n]

  [FIX] Creating branch: fix/tech-debt-015
  [FIX] Adding interface to src/types/ebay.ts
  [FIX] Updating getSellerList.ts with typed response
  [FIX] Updating 3 consuming components
  [VERIFY] npm run typecheck... ✅ (0 errors)
  [VERIFY] npm run lint... ✅ (0 errors)
  [VERIFY] npm run test... ✅ (148/148 pass)
  [VERIFY] any count check... ✅ (reduced by 4)

  DEBT-015: RESOLVED ✅
  Commit: def789
  Registry updated.
```

---

## Appendix A: Recommended Scan Tools

| Tool | Purpose | Install |
|------|---------|---------|
| `jscpd` | Code duplication detection | `npx jscpd` |
| `ts-prune` | Dead export detection | `npx ts-prune` |
| `madge` | Circular dependency detection | `npx madge --circular` |
| `eslint` | Complexity, code smells | Already in project |
| `npm outdated` | Dependency freshness | Built-in |
| `npm audit` | Dependency vulnerabilities | Built-in |

## Appendix B: Integration with CI/CD

When Release Manager agent is specified, Tech-Debt scan can be wired as a pre-release gate:

```
Release Manager → /tech-debt scan --quick
  IF critical items > 0 → BLOCK release
  IF high items increased → WARN
  ELSE → PASS
```

---

**End of Tech-Debt Agent Specification**
