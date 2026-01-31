# Test Execute Command

You are now operating as the **Test Execution Agent**. Follow the comprehensive instructions in `docs/testing/test-execution-agent.md`.

## Quick Reference

### Usage
```
/test-execute <mode>
```

### Available Modes

| Mode | Description | Duration |
|------|-------------|----------|
| `quick` | Critical unit tests only | ~1 min |
| `unit` | All unit tests | ~2 min |
| `api` | All API tests | ~3 min |
| `integration` | API + integration tests | ~5 min |
| `e2e` | All E2E browser tests | ~10 min |
| `regression` | Unit + API + integration | ~10 min |
| `complete` | All test types | ~15 min |
| `pre-merge` | Regression + critical E2E | ~10 min |
| `feature:<n>` | Tests for specific feature | Varies |

### Examples
```powershell
/test-execute quick         # Fast check
/test-execute regression    # Before merging
/test-execute pre-merge     # Full pre-merge validation
/test-execute feature:inventory
```

### Standard Workflow

1. **During development:** `/test-execute quick`
2. **Before committing:** `/test-execute unit`
3. **Before merging:** `/test-execute pre-merge`

### Output Files

- Test Report: `docs/testing/execution-history/test-run-{timestamp}.md`
- History: `docs/testing/execution-history/history.json`

### Coverage Targets

| Priority | Target |
|----------|--------|
| Critical | 85% |
| High | 75% |
| Medium | 70% |
| Overall | 80% |
