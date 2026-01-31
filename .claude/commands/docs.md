# Functional Documentation Command

You are now operating as the **Functional Documentation Agent**. Follow the comprehensive instructions in `docs/agents/functional-docs/spec.md`.

## Quick Reference

### Usage
```
/docs <mode> [target]
```

### Available Modes

| Mode | Command | Description |
|------|---------|-------------|
| **discover** | `/docs discover` | Scan codebase, identify features, show coverage dashboard |
| **document** | `/docs document <target>` | Generate documentation for a feature/journey |
| **update** | `/docs update [target]` | Incremental update based on code changes |
| **status** | `/docs status` | Show current documentation coverage |
| **inspect** | `/docs inspect <page>` | UI inspection only (screenshots + interactions) |

### Examples
```powershell
/docs discover                    # Full codebase scan, priority list
/docs document inventory          # Document inventory feature area
/docs document adding-inventory   # Document specific user journey
/docs document all                # Document everything (use with caution)
/docs update                      # Check all, update stale docs
/docs update ebay                 # Force update eBay documentation
/docs status                      # Show coverage dashboard
/docs inspect /inventory          # Capture UI for inventory page
```

## Standard Boot Sequence

**MANDATORY: Execute before any work.**

### 1. Check Lock
```powershell
# Check for concurrent run lock
cat docs/agents/functional-docs/run.lock
```
- If locked and fresh (< 1 hour) → ABORT
- If locked and stale (> 1 hour) → WARN, offer to clear
- If unlocked → Create lock, proceed

### 2. Read State
```powershell
cat docs/agents/functional-docs/state.json
```
- Load previous progress, coverage metrics, documented files
- If missing → First run flow
- If corrupted → Recovery flow

### 3. Check Recovery
```powershell
cat docs/agents/functional-docs/recovery.json
```
- If exists → Previous run crashed, offer to resume or start fresh

### 4. Detect Changes
- Compare source file timestamps vs last documentation run
- Identify stale documentation that needs updating

### 5. Check Prerequisites
- **For UI inspection modes:** Verify app running at localhost:3000
- **For all modes:** Verify write access to docs/functional/

### 6. Execute Mode
- Run the requested mode
- Process queue atomically (one item at a time)
- Update state after each unit of work

### 7. Clean Up (Always)
- Update state with final metrics
- Clear inProgress queue item
- Remove lock file
- Clear or update recovery.json

## Discovery Mode

Scans these locations:

| Location | What to Find |
|----------|--------------|
| `apps/web/app/(dashboard)/` | Dashboard pages and routes |
| `apps/web/app/api/` | API endpoints |
| `apps/web/lib/services/` | Business logic |
| `apps/web/lib/repositories/` | Data access layer |
| `apps/web/lib/adapters/` | External integrations |
| `apps/web/components/features/` | Feature-specific components |

### Discovery Output

1. **Priority-ranked feature list** with complexity scores
2. **Coverage dashboard** showing progress toward 100%
3. **User journey mapping** from routes and UI flows

**Waits for approval before proceeding to documentation.**

## Document Mode

For each feature area, generates:

| Output | Content |
|--------|---------|
| `overview.md` | Feature purpose, capabilities, journeys |
| `{journey}.md` | Step-by-step user flow with screenshots |
| `screenshots/{feature}/` | UI captures for each state |

### Documentation Process

1. **Analyse code** - Extract business logic, data flows
2. **Inspect UI** - Navigate pages, capture screenshots
3. **Generate docs** - Use templates, link to sources
4. **Update index** - Add to main documentation index
5. **Update state** - Mark as documented, update coverage

## UI Inspection

Requires:
- App running at `localhost:3000`
- Playwright MCP available

Captures:
- Full-page screenshots
- Interactive elements inventory
- State variations (empty, loaded, error)
- Form fields and validation

### Screenshot Naming
```
{feature}-{page-or-component}-{state}.png
```
Examples:
- `inventory-list-default.png`
- `inventory-add-form-validation-error.png`
- `ebay-auth-connected.png`

## Atomic Progress

**Critical:** Document ONE journey, update state, then next.

```
Document Journey A → Update state (A complete) → Document Journey B → Update state
```

Never:
```
Document A, B, C, D → Update state (all complete)  ❌ Risk of lost progress
```

## Output Locations

| Type | Location |
|------|----------|
| Feature docs | `docs/functional/{feature}/overview.md` |
| Journey docs | `docs/functional/{feature}/{journey}.md` |
| Screenshots | `docs/functional/screenshots/{feature}/` |
| Main index | `docs/functional/index.md` |
| Reference docs | `docs/functional/reference/` |
| Agent state | `docs/agents/functional-docs/state.json` |
| Templates | `docs/agents/functional-docs/templates/` |

## Error Handling

| Situation | Response |
|-----------|----------|
| App not running | Offer to skip UI inspection or abort |
| Playwright unavailable | Generate docs from code only, mark screenshots pending |
| Source file errors | Log warning, note in docs, continue |
| Screenshot failure | Mark as pending, suggest `/docs inspect` retry |
| Lock conflict | Show lock info, offer to clear if stale |
| State corrupted | Offer rebuild from existing docs or fresh start |

## Coverage Dashboard Format

```markdown
| Feature Area | Files | Documented | Coverage | Status |
|--------------|-------|------------|----------|--------|
| Inventory    | 47    | 47         | 100%     | 🟢     |
| eBay         | 23    | 12         | 52%      | 🟡     |
| Purchases    | 12    | 0          | 0%       | 🔴     |

Progress: ████████░░░░░░░░░░░░ 42%
```

## Hadley Bricks Feature Areas

Known feature areas to discover and document:

| Area | Key Files | Complexity |
|------|-----------|------------|
| Inventory Management | inventory/, stock levels, costs | High |
| eBay Integration | ebay/, OAuth, listings, orders | High |
| Purchase Parsing | purchases/, AI parsing | Medium |
| BrickLink Sync | bricklink/, OAuth 1.0a | Medium |
| Brick Owl Sync | brickowl/ | Medium |
| Reporting | reporting/, dashboard widgets | Medium |
| Google Sheets | sheets/, dual-write | Medium |
| Platform Stock | platform-stock/ | High |
| Authentication | auth/, Supabase | Low |
| Settings | settings/ | Low |

## Downstream Usage

| Consumer | How They Use Docs |
|----------|-------------------|
| **You (Developer)** | Understand forgotten business logic |
| **You (User)** | Remember what features exist |
| **Build Feature Agent** | Reference existing patterns |
| **Test Plan Agent** | Derive test scenarios |

## Next Steps After Documentation

```powershell
/docs status              # Verify coverage improved
/docs update              # Keep docs fresh after changes
git add docs/functional/  # Commit documentation
```

## Clean Campsite

Every run ends with consistent state:

**On success:**
- All queue items processed
- State updated with coverage
- Lock removed
- Index regenerated

**On failure:**
- Current item marked failed
- Remaining queue preserved
- Recovery file written
- Lock removed
- State remains consistent
