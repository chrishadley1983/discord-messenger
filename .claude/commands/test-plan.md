# Test Plan Command

You are now operating as the **Test Plan Agent**. Follow the comprehensive instructions in `docs/testing/test-plan-agent.md`.

## Quick Reference

### Usage
```
/test-plan <mode>
```

### Available Modes

| Mode | Description |
|------|-------------|
| `analyze` | Full gap analysis |
| `coverage` | Coverage report only |
| `feature:<n>` | Analyze specific feature |
| `generate-manifest <mode>` | Create test manifest |

### Examples
```powershell
/test-plan analyze          # Full analysis
/test-plan coverage         # Quick coverage check
/test-plan feature:orders   # Analyze orders feature
/test-plan generate-manifest regression
```

### Hadley Bricks Features

Core (CRITICAL): auth, inventory, purchases, orders
Platform (HIGH): bricklink, brickowl, bricqer, sheetsSync
Data (HIGH): repositories, dual-write, cache
Reporting (MEDIUM): financials, dashboard

### Output Files

- Coverage Report: `docs/testing/analysis/coverage-report-{date}.md`
- Test Manifest: `docs/testing/registry/test-manifest-{date}.json`
