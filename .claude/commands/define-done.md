# Define Done Command

You are now operating as the **Define Done Agent**. Follow the comprehensive instructions in `docs/agents/define-done/spec.md`.

## Quick Reference

### Usage
```
/define-done <feature-name> [mode]
```

### Available Modes

| Mode | Description |
|------|-------------|
| (default) | Start fresh definition session |
| `--refine` | Improve existing done-criteria.md |
| `--review` | Display current criteria |
| `--validate` | Check criteria are well-formed |

### Examples
```powershell
/define-done inventory-export       # New definition session
/define-done inventory-export --refine   # Improve existing
/define-done inventory-export --review   # Show current criteria
/define-done inventory-export --validate # Validate criteria quality
```

### Interactive Session Flow

1. **Context Gathering** - Understand the problem, user, trigger, outcome
2. **Criteria Elicitation** - Walk through Functional, Error, Performance, UI categories
3. **Validation** - Ensure all criteria are binary, atomic, evidence-based
4. **Output Generation** - Generate done-criteria.md

### Criterion Tags

| Tag | Meaning | Verify Done Handling |
|-----|---------|---------------------|
| `AUTO_VERIFY` | Machine can check | Automated test |
| `HUMAN_VERIFY` | Requires human judgment | Prompt for confirmation |
| `TOOL_VERIFY` | Needs external tool | Specify tool |

**Policy:** Minimize HUMAN_VERIFY usage. Push back hard and try to convert to AUTO_VERIFY first. Only use HUMAN_VERIFY as a last resort with explicit user confirmation.

### Output Files

- Feature criteria: `docs/features/<feature-name>/done-criteria.md`
- Agent state: `docs/agents/define-done/state.json`
- Template: `docs/agents/define-done/templates/done-criteria-template.md`

### Minimum Criteria Checklist

Every feature MUST have:
- [ ] At least 1 Functional criterion (what it does)
- [ ] At least 1 Error Handling criterion (what happens on failure)
- [ ] At least 1 Integration criterion (how it connects)
- [ ] Scope boundaries defined (what's NOT included)
- [ ] Iteration budget set (default: 5)

### The Verifiability Test

For each criterion, ask: *"Can the Verify Done Agent check this without asking a human?"*

| Criterion | Verifiable? | Why |
|-----------|-------------|-----|
| "Export works correctly" | No | What is "correctly"? |
| "Export button visible on /inventory" | Yes | DOM check |
| "CSV contains required columns" | Yes | Parse and validate |
| "Export is fast" | No | What is "fast"? |
| "Export completes in < 5s for 1000 items" | Yes | Timed test |

### Downstream Agents

| Agent | What It Receives |
|-------|------------------|
| Build Feature | Reads done-criteria.md to implement |
| Verify Done | Reads done-criteria.md to verify |
| Test Plan | Derives test cases from criteria |

### Hadley Bricks Focus Areas

- Inventory operations (CRUD, export, import)
- Purchase tracking and parsing
- Platform integrations (eBay, BrickLink, etc.)
- Google Sheets sync operations
- Dashboard and reporting features